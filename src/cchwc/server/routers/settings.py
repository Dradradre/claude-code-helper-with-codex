from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from cchwc.config import Settings, get_config_path, read_user_config, write_user_config

router = APIRouter()

_SCAN_MODES = {"global", "project"}
_LOG_LEVELS = {"TRACE", "DEBUG", "INFO", "WARN", "WARNING", "ERROR", "CRITICAL", "OFF"}
_EFFORT_LEVELS = {"", "low", "medium", "high", "xhigh", "max"}
_RESTART_KEYS = {
    "paths.db_path",
    "server.host",
    "server.port",
    "logging.file",
}


class SettingsPayload(BaseModel):
    paths: dict[str, Any] = {}
    scan: dict[str, Any] = {}
    server: dict[str, Any] = {}
    watch: dict[str, Any] = {}
    orchestrator: dict[str, Any] = {}
    agents: dict[str, Any] = {}
    logging: dict[str, Any] = {}


@router.get("")
async def get_settings():
    return _settings_response(changed_keys=set())


@router.post("")
async def update_settings(payload: SettingsPayload):
    data = read_user_config()
    changed_keys: set[str] = set()

    _set_paths(data, payload.paths, changed_keys)
    _set_scan(data, payload.scan, changed_keys)
    _set_server(data, payload.server, changed_keys)
    _set_watch(data, payload.watch, changed_keys)
    _set_orchestrator(data, payload.orchestrator, changed_keys)
    _set_agents(data, payload.agents, changed_keys)
    _set_logging(data, payload.logging, changed_keys)

    path = write_user_config(data)
    response = _settings_response(changed_keys=changed_keys)
    response["config_path"] = str(path)
    response["saved"] = True
    return response


def _settings_response(changed_keys: set[str]) -> dict:
    settings = Settings()
    restart_required = sorted(key for key in changed_keys if key in _RESTART_KEYS)
    return {
        "config_path": str(get_config_path()),
        "effective": settings.model_dump(mode="json"),
        "user_config": read_user_config(),
        "restart_required": restart_required,
        "saved": False,
    }


def _set_paths(data: dict, values: dict, changed: set[str]) -> None:
    mapping = {
        "db_path": "db_path",
        "claude_root": "claude_root",
        "codex_root": "codex_root",
    }
    _set_string_section(data, "paths", values, mapping, changed, path_like=True)


def _set_scan(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    section = data.setdefault("scan", {})
    if "mode" in values:
        mode = str(values.get("mode") or "global")
        if mode not in _SCAN_MODES:
            raise HTTPException(status_code=400, detail="scan.mode must be 'global' or 'project'")
        _assign(section, "mode", mode, "scan.mode", changed)
    if "roots" in values:
        roots = values.get("roots") or []
        if isinstance(roots, str):
            roots = [line.strip() for line in roots.splitlines() if line.strip()]
        if not isinstance(roots, list):
            raise HTTPException(status_code=400, detail="scan.roots must be a list")
        _assign(section, "roots", [str(Path(str(root)).expanduser()) for root in roots], "scan.roots", changed)
    if "concurrency" in values:
        _assign(
            section,
            "concurrency",
            _positive_int(values["concurrency"], "scan.concurrency"),
            "scan.concurrency",
            changed,
        )


def _set_server(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    section = data.setdefault("server", {})
    if "host" in values:
        _assign(section, "host", str(values.get("host") or "127.0.0.1"), "server.host", changed)
    if "port" in values:
        port = _positive_int(values["port"], "server.port")
        if port > 65535:
            raise HTTPException(status_code=400, detail="server.port must be <= 65535")
        _assign(section, "port", port, "server.port", changed)


def _set_watch(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    section = data.setdefault("watch", {})
    if "debounce_ms" in values:
        _assign(
            section,
            "debounce_ms",
            _non_negative_int(values["debounce_ms"], "watch.debounce_ms"),
            "watch.debounce_ms",
            changed,
        )


def _set_orchestrator(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    section = data.setdefault("orchestrator", {})
    if "default_max_rounds" in values:
        _assign(
            section,
            "default_max_rounds",
            _positive_int(values["default_max_rounds"], "orchestrator.default_max_rounds"),
            "orchestrator.default_max_rounds",
            changed,
        )
    if "default_max_tokens" in values:
        _assign(
            section,
            "default_max_tokens",
            _positive_int(values["default_max_tokens"], "orchestrator.default_max_tokens"),
            "orchestrator.default_max_tokens",
            changed,
        )
    if "default_max_cost_usd" in values:
        _assign(
            section,
            "default_max_cost_usd",
            _non_negative_float(values["default_max_cost_usd"], "orchestrator.default_max_cost_usd"),
            "orchestrator.default_max_cost_usd",
            changed,
        )


def _set_agents(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    mapping = {
        "claude_bin": "claude_bin",
        "codex_bin": "codex_bin",
        "claude_model": "claude_model",
        "codex_model": "codex_model",
    }
    _set_string_section(data, "agents", values, mapping, changed)
    section = data.setdefault("agents", {})
    if "claude_effort" in values:
        _assign(
            section,
            "claude_effort",
            _effort_level(values.get("claude_effort"), "agents.claude_effort"),
            "agents.claude_effort",
            changed,
        )
    if "codex_reasoning_effort" in values:
        _assign(
            section,
            "codex_reasoning_effort",
            _effort_level(values.get("codex_reasoning_effort"), "agents.codex_reasoning_effort"),
            "agents.codex_reasoning_effort",
            changed,
        )


def _set_logging(data: dict, values: dict, changed: set[str]) -> None:
    if not values:
        return
    section = data.setdefault("logging", {})
    if "level" in values:
        level = str(values.get("level") or "INFO").upper()
        if level not in _LOG_LEVELS:
            raise HTTPException(status_code=400, detail="logging.level is invalid")
        _assign(section, "level", level, "logging.level", changed)
    if "file" in values:
        value = str(values.get("file") or "").strip()
        if value:
            _assign(section, "file", str(Path(value).expanduser()), "logging.file", changed)
        elif section.pop("file", None) is not None:
            changed.add("logging.file")


def _set_string_section(
    data: dict,
    section_name: str,
    values: dict,
    mapping: dict[str, str],
    changed: set[str],
    *,
    path_like: bool = False,
) -> None:
    if not values:
        return
    section = data.setdefault(section_name, {})
    for payload_key, config_key in mapping.items():
        if payload_key not in values:
            continue
        value = str(values.get(payload_key) or "").strip()
        if path_like and value:
            value = str(Path(value).expanduser())
        _assign(section, config_key, value, f"{section_name}.{config_key}", changed)


def _assign(section: dict, key: str, value: Any, dotted_key: str, changed: set[str]) -> None:
    if section.get(key) != value:
        section[key] = value
        changed.add(dotted_key)


def _positive_int(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from e
    if result <= 0:
        raise HTTPException(status_code=400, detail=f"{field} must be positive")
    return result


def _non_negative_int(value: Any, field: str) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"{field} must be an integer") from e
    if result < 0:
        raise HTTPException(status_code=400, detail=f"{field} must be non-negative")
    return result


def _non_negative_float(value: Any, field: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"{field} must be a number") from e
    if result < 0:
        raise HTTPException(status_code=400, detail=f"{field} must be non-negative")
    return result


def _effort_level(value: Any, field: str) -> str:
    level = str(value or "").strip().lower()
    if level not in _EFFORT_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be one of: low, medium, high, xhigh, max",
        )
    return level
