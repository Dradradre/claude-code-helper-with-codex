import asyncio
import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cchwc.config import Settings
from cchwc.orchestrator.runner import run_agent

_CODEX_CACHE_TTL_SEC = 30
_CLAUDE_CACHE_TTL_SEC = 10 * 60
_CODEX_MAX_FILES = 24
_CODEX_TAIL_BYTES = 1024 * 1024

_codex_cache: dict[str, Any] = {"expires_at": 0.0, "data": None}
_claude_cache: dict[str, Any] = {"expires_at": 0.0, "data": None}
_codex_lock = asyncio.Lock()
_claude_lock = asyncio.Lock()


async def get_cli_limit_status(force_refresh: bool = False) -> dict[str, Any]:
    settings = Settings()
    codex_task = _cached_codex_status(settings, force_refresh=force_refresh)
    claude_task = _cached_claude_status(settings, force_refresh=force_refresh)
    codex, claude = await asyncio.gather(codex_task, claude_task)
    return {
        "as_of": datetime.now().astimezone().isoformat(),
        "codex": codex,
        "claude": claude,
        "cache_ttl_seconds": {
            "codex": _CODEX_CACHE_TTL_SEC,
            "claude": _CLAUDE_CACHE_TTL_SEC,
        },
    }


async def _cached_codex_status(settings: Settings, force_refresh: bool) -> dict[str, Any]:
    now = time.monotonic()
    async with _codex_lock:
        if not force_refresh and _codex_cache["data"] is not None and now < _codex_cache["expires_at"]:
            return _codex_cache["data"]

        data = await asyncio.to_thread(read_codex_limit_status, settings.codex_root)
        _codex_cache.update({"data": data, "expires_at": now + _CODEX_CACHE_TTL_SEC})
        return data


async def _cached_claude_status(settings: Settings, force_refresh: bool) -> dict[str, Any]:
    now = time.monotonic()
    async with _claude_lock:
        if not force_refresh and _claude_cache["data"] is not None and now < _claude_cache["expires_at"]:
            return _claude_cache["data"]

        data = await fetch_claude_limit_status(settings)
        _claude_cache.update({"data": data, "expires_at": now + _CLAUDE_CACHE_TTL_SEC})
        return data


def read_codex_limit_status(root: Path) -> dict[str, Any]:
    root = root.expanduser()
    if not root.exists():
        return _unavailable("codex_session_log", f"Codex sessions directory not found: {root}")

    try:
        files = sorted(
            (path for path in root.rglob("*.jsonl") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
    except OSError as exc:
        return _unavailable("codex_session_log", str(exc))

    for path in files[:_CODEX_MAX_FILES]:
        status = _read_codex_limit_from_file(path)
        if status is not None:
            return status

    return _unavailable("codex_session_log", "No Codex rate_limits event found in recent session logs")


def _read_codex_limit_from_file(path: Path) -> dict[str, Any] | None:
    try:
        lines = _read_tail_lines(path, _CODEX_TAIL_BYTES)
        mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat()
    except OSError:
        return None

    for line in reversed(lines):
        parsed = parse_codex_rate_limit_line(line, file_path=str(path), file_mtime=mtime)
        if parsed is not None:
            return parsed
    return None


def _read_tail_lines(path: Path, max_bytes: int) -> list[str]:
    size = path.stat().st_size
    with open(path, "rb") as f:
        if size > max_bytes:
            f.seek(-max_bytes, os.SEEK_END)
            f.readline()
        data = f.read()
    return data.decode("utf-8", errors="replace").splitlines()


def parse_codex_rate_limit_line(
    line: str,
    *,
    file_path: str | None = None,
    file_mtime: str | None = None,
) -> dict[str, Any] | None:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        return None

    if not isinstance(event, dict):
        return None
    rate_limits = event.get("rate_limits")
    if not isinstance(rate_limits, dict):
        payload = event.get("payload")
        if isinstance(payload, dict):
            rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None

    parsed = _normalize_codex_rate_limits(rate_limits)
    parsed["source"] = "codex_session_log"
    parsed["available"] = True
    parsed["updated_at"] = event.get("timestamp") or file_mtime
    parsed["file"] = file_path
    parsed["stale"] = _is_stale(parsed)
    return parsed


def _normalize_codex_rate_limits(rate_limits: dict[str, Any]) -> dict[str, Any]:
    return {
        "limit_id": rate_limits.get("limit_id"),
        "limit_name": rate_limits.get("limit_name"),
        "plan_type": rate_limits.get("plan_type"),
        "rate_limit_reached_type": rate_limits.get("rate_limit_reached_type"),
        "primary": _normalize_window("primary", rate_limits.get("primary")),
        "secondary": _normalize_window("secondary", rate_limits.get("secondary")),
        "credits": rate_limits.get("credits"),
    }


def _normalize_window(name: str, raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    used = _number(raw.get("used_percent", raw.get("used_percentage")))
    remaining = None if used is None else max(0.0, min(100.0, 100.0 - used))
    minutes = _number(raw.get("window_minutes"))
    resets_at_unix = _number(raw.get("resets_at"))
    return {
        "name": name,
        "label": _window_label(minutes, name),
        "used_percent": used,
        "remaining_percent": remaining,
        "window_minutes": minutes,
        "resets_at": _unix_to_iso(resets_at_unix),
        "resets_at_unix": resets_at_unix,
    }


async def fetch_claude_limit_status(settings: Settings) -> dict[str, Any]:
    auth = await _fetch_claude_auth(settings)
    cmd = [
        settings.claude_bin,
        "-p",
        "Return exactly: status-probe",
        "--output-format",
        "stream-json",
        "--verbose",
        "--include-partial-messages",
    ]
    result = await run_agent(cmd, timeout_sec=60)
    if result.exit_code != 0 or result.error:
        return {
            **_unavailable("claude_rate_limit_event", result.error or result.stderr or "Claude status probe failed"),
            "auth": auth,
        }

    parsed = parse_claude_rate_limit_output(result.stdout)
    if parsed is None:
        return {
            **_unavailable("claude_rate_limit_event", "No rate_limit_event found in Claude CLI output"),
            "auth": auth,
        }

    parsed["auth"] = auth
    parsed["updated_at"] = datetime.now().astimezone().isoformat()
    return parsed


async def _fetch_claude_auth(settings: Settings) -> dict[str, Any] | None:
    result = await run_agent([settings.claude_bin, "auth", "status", "--json"], timeout_sec=15)
    if result.exit_code != 0 or not result.stdout.strip():
        return None

    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None

    return {
        "logged_in": raw.get("loggedIn"),
        "auth_method": raw.get("authMethod"),
        "api_provider": raw.get("apiProvider"),
        "subscription_type": raw.get("subscriptionType"),
    }


def parse_claude_rate_limit_output(output: str) -> dict[str, Any] | None:
    for line in output.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue

        if not isinstance(event, dict) or event.get("type") != "rate_limit_event":
            continue
        info = event.get("rate_limit_info")
        if not isinstance(info, dict):
            continue
        return _normalize_claude_rate_limit_info(info)
    return None


def _normalize_claude_rate_limit_info(info: dict[str, Any]) -> dict[str, Any]:
    resets_at_unix = _number(info.get("resetsAt"))
    overage_resets_at_unix = _number(info.get("overageResetsAt"))
    return {
        "source": "claude_rate_limit_event",
        "available": True,
        "status": info.get("status"),
        "rate_limit_type": info.get("rateLimitType"),
        "resets_at": _unix_to_iso(resets_at_unix),
        "resets_at_unix": resets_at_unix,
        "overage_status": info.get("overageStatus"),
        "overage_resets_at": _unix_to_iso(overage_resets_at_unix),
        "overage_resets_at_unix": overage_resets_at_unix,
        "is_using_overage": info.get("isUsingOverage"),
    }


def _unavailable(source: str, error: str) -> dict[str, Any]:
    return {
        "source": source,
        "available": False,
        "error": error,
        "updated_at": datetime.now().astimezone().isoformat(),
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _unix_to_iso(value: float | None) -> str | None:
    if value is None:
        return None
    ts = value / 1000 if value > 100_000_000_000 else value
    try:
        return datetime.fromtimestamp(ts, tz=UTC).astimezone().isoformat()
    except (OSError, OverflowError, ValueError):
        return None


def _window_label(minutes: float | None, fallback: str) -> str:
    if minutes == 300:
        return "5h"
    if minutes == 10080:
        return "7d"
    if minutes and minutes >= 60 and minutes % 60 == 0:
        hours = int(minutes // 60)
        return f"{hours}h"
    if minutes:
        return f"{int(minutes)}m"
    return fallback


def _is_stale(status: dict[str, Any]) -> bool:
    reset_times = [
        window.get("resets_at_unix")
        for window in (status.get("primary"), status.get("secondary"))
        if isinstance(window, dict)
    ]
    reset_times = [ts for ts in reset_times if ts is not None]
    return bool(reset_times and max(reset_times) < time.time())
