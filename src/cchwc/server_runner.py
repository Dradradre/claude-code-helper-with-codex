"""daemon + web server를 단일 asyncio 루프에서 실행."""

from __future__ import annotations

import asyncio
import logging
import platform
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

INSTALL_DIR = Path(__file__).parent.parent.parent.resolve()


async def serve_all(open_browser: bool = False, host: str | None = None, port: int | None = None) -> None:
    """DB 초기화 → 자동 스캔(필요 시) → watcher → 웹 서버를 단일 프로세스로 실행."""
    import uvicorn
    from sqlalchemy import func, select

    from cchwc.config import Settings
    from cchwc.core.db import get_engine, get_session_factory
    from cchwc.core.models import Base, Session
    from cchwc.indexer.scanner import initial_scan
    from cchwc.indexer.watcher import SessionWatcher
    from cchwc.server.app import create_app

    settings = Settings()
    if host is not None:
        settings.host = host
    if port is not None:
        settings.port = port

    # ── 1. DB init ──────────────────────────────────────────────
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory(settings)

    # ── 2. Auto scan if DB is empty ────────────────────────────
    async with session_factory() as db:
        count = (await db.execute(select(func.count(Session.id)))).scalar() or 0

    if count == 0:
        logger.info("Empty DB — running initial scan…")
        adapters = _make_adapters(settings)
        async with session_factory() as db:
            for adapter in adapters:
                report = await initial_scan(adapter, db, settings.scan_concurrency)
                logger.info("%s: %d sessions", adapter.agent_type, report.parsed)

    # ── 3. Start watcher as background asyncio task ────────────
    adapters = _make_adapters(settings)
    watcher = SessionWatcher(adapters, settings.watch_debounce_ms)
    watcher.start()
    watcher_task = asyncio.create_task(watcher.consume_loop(session_factory))

    # ── 4. Open browser (optional) ─────────────────────────────
    if open_browser:
        _open_browser(f"http://{settings.host}:{settings.port}")

    # ── 5. Start web server ─────────────────────────────────────
    app = create_app()
    config = uvicorn.Config(
        app,
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )
    server = uvicorn.Server(config)

    print(f"\n  cchwc  →  http://{settings.host}:{settings.port}\n")

    try:
        await server.serve()
    finally:
        watcher_task.cancel()
        watcher.stop()


def _make_adapters(settings):
    from cchwc.adapters.claude_adapter import ClaudeAdapter
    from cchwc.adapters.codex_adapter import CodexAdapter

    scan_roots = settings.scan_roots if settings.scan_mode == "project" and settings.scan_roots else None
    return [
        ClaudeAdapter(settings.claude_root, scan_roots=scan_roots),
        CodexAdapter(settings.codex_root),
    ]


def _open_browser(url: str) -> None:
    import contextlib
    import webbrowser
    with contextlib.suppress(Exception):
        webbrowser.open(url)


# ── Auto-start registration ────────────────────────────────────────────────

def install_autostart(uv_path: str | None = None, install_dir: Path | None = None) -> bool:
    """OS별 자동 시작을 등록합니다. 성공하면 True."""
    uv = uv_path or shutil.which("uv") or "uv"
    base = install_dir or INSTALL_DIR

    system = platform.system()
    try:
        if system == "Darwin":
            return _autostart_macos(uv, base)
        if system == "Windows":
            return _autostart_windows(uv, base)
        return _autostart_linux(uv, base)
    except Exception as e:
        logger.warning("autostart failed: %s", e)
        return False


def remove_autostart() -> bool:
    """자동 시작 등록을 제거합니다."""
    system = platform.system()
    try:
        if system == "Darwin":
            import os
            plist = Path.home() / "Library" / "LaunchAgents" / "com.cchwc.agent.plist"
            if plist.exists():
                uid = os.getuid()
                r = subprocess.run(
                    ["launchctl", "bootout", f"gui/{uid}", str(plist)],
                    check=False, capture_output=True,
                )
                if r.returncode != 0:
                    subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
                plist.unlink()
            return True
        if system == "Windows":
            bat = _win_startup_dir() / "cchwc.bat"
            if bat.exists():
                bat.unlink()
            return True
        service = Path.home() / ".config" / "systemd" / "user" / "cchwc.service"
        if service.exists():
            subprocess.run(["systemctl", "--user", "disable", "--now", "cchwc"], check=False)
            service.unlink()
        return True
    except Exception:
        return False


def _xml_esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _autostart_macos(uv: str, base: Path) -> bool:
    import os

    label = "com.cchwc.agent"
    log_dir = Path.home() / ".cchwc"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_dir = Path.home() / "Library" / "LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist = plist_dir / f"{label}.plist"
    uv_cache = base / ".uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)

    # LaunchAgent는 셸 PATH를 상속하지 않으므로 명시적으로 설정
    uv_dir = str(Path(uv).parent)
    path_val = f"/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin:{_xml_esc(uv_dir)}"

    plist.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{_xml_esc(uv)}</string>
    <string>run</string>
    <string>--no-dev</string>
    <string>--project</string>
    <string>{_xml_esc(str(base))}</string>
    <string>cchwc</string>
    <string>serve</string>
  </array>
  <key>WorkingDirectory</key><string>{_xml_esc(str(base))}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>{path_val}</string>
    <key>UV_CACHE_DIR</key><string>{_xml_esc(str(uv_cache))}</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key>
  <dict>
    <key>SuccessfulExit</key><false/>
  </dict>
  <key>ThrottleInterval</key><integer>10</integer>
  <key>StandardOutPath</key><string>{_xml_esc(str(log_dir))}/cchwc.log</string>
  <key>StandardErrorPath</key><string>{_xml_esc(str(log_dir))}/cchwc.err</string>
</dict></plist>
""", encoding="utf-8")

    uid = os.getuid()
    # macOS 13+ (Ventura): bootstrap/bootout 사용, 구버전은 load/unload로 fallback
    subprocess.run(
        ["launchctl", "bootout", f"gui/{uid}", str(plist)],
        check=False, capture_output=True,
    )
    result = subprocess.run(
        ["launchctl", "bootstrap", f"gui/{uid}", str(plist)],
        capture_output=True,
    )
    if result.returncode != 0:
        subprocess.run(["launchctl", "unload", str(plist)], check=False, capture_output=True)
        result = subprocess.run(["launchctl", "load", str(plist)], capture_output=True)
    return result.returncode == 0


def _win_startup_dir() -> Path:
    import os
    appdata = Path(os.environ.get("APPDATA", str(Path.home())))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _autostart_windows(uv: str, base: Path) -> bool:
    startup = _win_startup_dir()
    startup.mkdir(parents=True, exist_ok=True)
    bat = startup / "cchwc.bat"
    uv_cache = base / ".uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    content = (
        "@echo off\n"
        f'set "UV_CACHE_DIR={uv_cache}"\n'
        f'cd /d "{base}"\n'
        f'start /min "" "{uv}" run --no-dev --project "{base}" cchwc serve\n'
    )
    bat.write_text(
        content,
        encoding="utf-8",
    )
    return True


def _autostart_linux(uv: str, base: Path) -> bool:
    svc_dir = Path.home() / ".config" / "systemd" / "user"
    svc_dir.mkdir(parents=True, exist_ok=True)
    svc = svc_dir / "cchwc.service"
    uv_cache = base / ".uv-cache"
    uv_cache.mkdir(parents=True, exist_ok=True)
    svc.write_text(f"""[Unit]
Description=cchwc — Claude Code + Codex Session Hub
After=network.target

[Service]
WorkingDirectory="{base}"
Environment="UV_CACHE_DIR={uv_cache}"
ExecStart="{uv}" run --no-dev --project "{base}" cchwc serve
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
""", encoding="utf-8")

    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False, capture_output=True)
    result = subprocess.run(["systemctl", "--user", "enable", "--now", "cchwc"], capture_output=True)
    return result.returncode == 0
