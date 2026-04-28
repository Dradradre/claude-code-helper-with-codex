import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(name="cchwc", help="Claude Code + Codex CLI 세션 통합 관리 도구")
console = Console()

# ──────────────────────────────────────────
# serve
# ──────────────────────────────────────────

_PID_FILE = Path.home() / ".cchwc" / "cchwc.pid"


def _server_url() -> str:
    from cchwc.config import Settings

    settings = Settings()
    return f"http://{settings.host}:{settings.port}"


def _server_health_ok(timeout: float = 1.0) -> bool:
    import json
    import urllib.request

    try:
        with urllib.request.urlopen(f"{_server_url()}/health", timeout=timeout) as response:
            if response.status != 200:
                return False
            return json.loads(response.read().decode("utf-8")).get("status") == "ok"
    except Exception:
        return False


def _pid_exists(pid: int) -> bool:
    import ctypes
    import os
    import platform

    if platform.system() == "Windows":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_query = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
        still_active = 259
        handle = kernel32.OpenProcess(process_query, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied means the PID exists.
        try:
            exit_code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return True
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, 0)
        return True
    except (OSError, SystemError):
        return False


def _terminate_pid(pid: int) -> bool:
    import ctypes
    import os
    import platform
    import signal

    if platform.system() == "Windows":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        process_terminate = 0x0001
        handle = kernel32.OpenProcess(process_terminate, False, pid)
        if not handle:
            return not _pid_exists(pid)
        try:
            return bool(kernel32.TerminateProcess(handle, 0))
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(pid, signal.SIGTERM)
        return True
    except (OSError, SystemError):
        return False


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="서버 호스트"),
    port: int = typer.Option(7878, help="서버 포트"),
    open_browser: bool = typer.Option(False, "--open", help="시작 후 브라우저 자동 열기"),
) -> None:
    """웹 서버 + watchdog을 포그라운드로 실행합니다. (Ctrl+C로 종료)"""
    from cchwc.server_runner import serve_all
    asyncio.run(serve_all(open_browser=open_browser, host=host, port=port))


@app.command()
def start(
    open_browser: bool = typer.Option(False, "--open", help="시작 후 브라우저 열기"),
) -> None:
    """백그라운드에서 서버를 시작합니다."""
    import subprocess
    import sys

    if _PID_FILE.exists():
        pid = int(_PID_FILE.read_text().strip())
        if _pid_exists(pid) and _server_health_ok():
            console.print(f"  [yellow]이미 실행 중[/yellow] (PID {pid})  →  {_server_url()}")
            if open_browser:
                _do_open()
            return
        _PID_FILE.unlink(missing_ok=True)

    exe = sys.executable
    log_dir = Path.home() / ".cchwc"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "cchwc.log"

    log_file = open(log_path, "a")  # noqa: SIM115
    proc = subprocess.Popen(
        [exe, "-m", "cchwc._bg_serve"],
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(proc.pid))
    console.print(f"  [green]✓[/green]  cchwc started (PID {proc.pid})  →  {_server_url()}")
    console.print(f"  [dim]log: {log_path}[/dim]")
    if open_browser:
        import time
        time.sleep(1.5)
        _do_open()


@app.command()
def stop() -> None:
    """실행 중인 백그라운드 서버를 종료합니다."""
    if not _PID_FILE.exists():
        console.print("  [dim]실행 중인 서버가 없습니다.[/dim]")
        return
    pid = int(_PID_FILE.read_text().strip())
    if not _server_health_ok():
        _PID_FILE.unlink(missing_ok=True)
        console.print("  [dim]프로세스가 이미 종료되어 있었습니다.[/dim]")
        return
    if _terminate_pid(pid):
        _PID_FILE.unlink(missing_ok=True)
        console.print(f"  [green]✓[/green]  cchwc stopped (PID {pid})")
    else:
        _PID_FILE.unlink(missing_ok=True)
        console.print(f"  [red]✗[/red]  cchwc stop failed; stale PID removed ({pid})")


@app.command()
def status() -> None:
    """서버 실행 상태를 확인합니다."""
    if not _PID_FILE.exists():
        console.print("  [dim]●[/dim]  cchwc  [dim]stopped[/dim]")
        return
    pid = int(_PID_FILE.read_text().strip())
    if _pid_exists(pid) and _server_health_ok():
        console.print(f"  [green]●[/green]  cchwc  [green]running[/green]  (PID {pid})  →  {_server_url()}")
    else:
        _PID_FILE.unlink(missing_ok=True)
        console.print("  [red]●[/red]  cchwc  [dim]crashed (PID file stale)[/dim]")


@app.command("open")
def open_cmd() -> None:
    """브라우저에서 대시보드를 엽니다."""
    _do_open()


@app.command()
def uninstall(
    keep_data: bool = typer.Option(False, "--keep-data", help="DB와 설정 파일은 유지"),
    yes: bool = typer.Option(False, "--yes", "-y", help="확인 없이 바로 실행"),
) -> None:
    """cchwc를 제거합니다 (autostart 해제 + 데이터 삭제)."""
    import shutil as _shutil

    if not yes:
        console.print("[bold red]이 작업은 되돌릴 수 없습니다.[/bold red]")
        confirm = typer.confirm("계속하시겠습니까?", default=False)
        if not confirm:
            console.print("[dim]취소했습니다.[/dim]")
            return

    # ── 1. 서버 종료 ──────────────────────────────────────────────
    if _PID_FILE.exists():
        try:
            pid = int(_PID_FILE.read_text().strip())
            if _terminate_pid(pid):
                console.print(f"  [green]✓[/green]  서버 종료 (PID {pid})")
        except (OSError, ValueError):
            pass
        _PID_FILE.unlink(missing_ok=True)

    # ── 2. autostart 제거 ─────────────────────────────────────────
    from cchwc.server_runner import remove_autostart
    if remove_autostart():
        console.print("  [green]✓[/green]  자동 시작 해제")
    else:
        console.print("  [dim]→  자동 시작 등록 없음 (건너뜀)[/dim]")

    # ── 3. Claude Code 슬래시 커맨드 / MCP 제거 ──────────────────
    for cmd_name in ["cchwc-compare", "cchwc-review", "cchwc-debate",
                     "cchwc-start", "cchwc-stop", "cchwc-open"]:
        for base in [Path.home() / ".claude" / "commands"]:
            f = base / f"{cmd_name}.md"
            if f.exists():
                f.unlink()
    console.print("  [green]✓[/green]  슬래시 커맨드 제거")

    mcp_json = Path.home() / ".claude" / "mcp.json"
    if mcp_json.exists():
        import json
        try:
            with open(mcp_json, encoding="utf-8") as f:
                data = json.load(f)
            data.get("mcpServers", {}).pop("cchwc", None)
            with open(mcp_json, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            console.print("  [green]✓[/green]  MCP 서버 등록 해제")
        except Exception:
            pass

    # ── 4. DB / 설정 삭제 ────────────────────────────────────────
    if not keep_data:
        cchwc_dir = Path.home() / ".cchwc"
        if cchwc_dir.exists():
            _shutil.rmtree(cchwc_dir)
            console.print("  [green]✓[/green]  데이터 삭제 (~/.cchwc/)")
    else:
        console.print("  [dim]→  데이터 유지 (--keep-data)[/dim]")

    console.print("\n  [bold]cchwc가 제거되었습니다.[/bold]")
    console.print("  [dim]소스 코드는 클론한 디렉토리를 직접 삭제하세요.[/dim]")


def _do_open() -> None:
    import webbrowser

    from cchwc.config import Settings
    s = Settings()
    url = f"http://{s.host}:{s.port}"
    webbrowser.open(url)
    console.print(f"  [cyan]{url}[/cyan]")


# ──────────────────────────────────────────
# scan
# ──────────────────────────────────────────

@app.command()
def scan(
    glob: bool = typer.Option(False, "--global", "-g", help="전체 세션 스캔 (기본값: 현재 디렉토리 프로젝트만)"),
    cwd: list[str] = typer.Option([], "--cwd", "-c", help="스캔할 프로젝트 경로 (여러 번 사용 가능)"),
    no_claude: bool = typer.Option(False, "--no-claude", help="Claude 세션 제외"),
    no_codex: bool = typer.Option(False, "--no-codex", help="Codex 세션 제외"),
) -> None:
    """세션을 인덱싱합니다.

    기본: 현재 디렉토리 프로젝트 세션만 스캔.
    --global: 전체 ~/.claude/projects 스캔.
    --cwd PATH: 특정 경로 지정 (여러 번 사용 가능).
    """
    from cchwc.config import Settings
    settings = Settings()

    if glob:
        scan_roots = None  # global
        console.print("[dim]모드: 전체 (global)[/dim]")
    elif cwd:
        scan_roots = list(cwd)
        console.print(f"[dim]모드: 지정 경로 {scan_roots}[/dim]")
    elif settings.scan_mode == "global":
        scan_roots = None
        console.print("[dim]모드: 전체 (설정 기반)[/dim]")
    elif settings.scan_roots:
        scan_roots = settings.scan_roots
        console.print(f"[dim]모드: 설정된 프로젝트 {scan_roots}[/dim]")
    else:
        scan_roots = [str(Path.cwd())]
        console.print(f"[dim]모드: 현재 디렉토리 ({scan_roots[0]})[/dim]")

    asyncio.run(_scan(
        scan_roots=scan_roots,
        do_claude=not no_claude,
        do_codex=not no_codex,
        settings=settings,
    ))


async def _scan(scan_roots, do_claude, do_codex, settings=None) -> None:
    from cchwc.adapters.claude_adapter import ClaudeAdapter
    from cchwc.adapters.codex_adapter import CodexAdapter
    from cchwc.config import Settings
    from cchwc.core.db import get_engine, get_session_factory
    from cchwc.core.models import Base
    from cchwc.indexer.scanner import initial_scan

    if settings is None:
        settings = Settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory(settings)
    adapters = []
    if do_claude:
        adapters.append(ClaudeAdapter(settings.claude_root, scan_roots=scan_roots))
    if do_codex:
        # Codex는 날짜 기반 디렉토리 구조라 project filter 미지원 → global만
        adapters.append(CodexAdapter(settings.codex_root))

    async with session_factory() as db:
        for adapter in adapters:
            report = await initial_scan(adapter, db, settings.scan_concurrency)
            console.print(
                f"[bold]{adapter.agent_type}[/bold]: "
                f"{report.total_files} files, {report.parsed} parsed, "
                f"{report.skipped} skipped, {report.errors} errors"
            )
            for err in report.error_details[:5]:
                console.print(f"  [red]{err}[/red]")


# ──────────────────────────────────────────
# config
# ──────────────────────────────────────────

config_app = typer.Typer(help="스캔 범위 설정")
app.add_typer(config_app, name="config")


@config_app.command("show")
def config_show() -> None:
    """현재 설정을 출력합니다."""
    from cchwc.config import Settings, get_config_path
    s = Settings()
    console.print(f"config     : {get_config_path()}")
    console.print(f"scan_mode  : [bold]{s.scan_mode}[/bold]")
    console.print(f"scan_roots : {s.scan_roots or '(none)'}")
    console.print(f"db_path    : {s.db_path}")
    console.print(f"port       : {s.port}")


@config_app.command("add-project")
def config_add_project(
    path: str = typer.Argument(default=".", help="추가할 프로젝트 경로 (기본: 현재 디렉토리)"),
) -> None:
    """스캔할 프로젝트 경로를 추가합니다."""
    _write_config("add", str(Path(path).resolve()))


@config_app.command("remove-project")
def config_remove_project(
    path: str = typer.Argument(help="제거할 프로젝트 경로"),
) -> None:
    """스캔 목록에서 프로젝트 경로를 제거합니다."""
    _write_config("remove", str(Path(path).resolve()))


@config_app.command("set-global")
def config_set_global() -> None:
    """스캔 모드를 전체(global)로 설정합니다."""
    _write_config("mode", "global")
    console.print("[green]scan_mode = global[/green]")


@config_app.command("set-project")
def config_set_project() -> None:
    """스캔 모드를 프로젝트 지정 모드로 설정합니다."""
    _write_config("mode", "project")
    console.print("[green]scan_mode = project[/green]")


def _write_config(action: str, value: str) -> None:
    from cchwc.config import read_user_config, write_user_config

    data = read_user_config()
    scan = data.setdefault("scan", {})

    if action == "mode":
        scan["mode"] = value
    elif action == "add":
        scan["mode"] = "project"
        roots = scan.setdefault("roots", [])
        if value not in roots:
            roots.append(value)
            console.print(f"[green]추가됨: {value}[/green]")
        else:
            console.print(f"[yellow]이미 존재: {value}[/yellow]")
    elif action == "remove":
        roots = scan.get("roots", [])
        if value in roots:
            roots.remove(value)
            console.print(f"[green]제거됨: {value}[/green]")
        else:
            console.print(f"[yellow]목록에 없음: {value}[/yellow]")

    write_user_config(data)


# ──────────────────────────────────────────
# daemon
# ──────────────────────────────────────────

@app.command()
def daemon(
    foreground: bool = typer.Option(False, help="포그라운드에서 실행"),
) -> None:
    """백그라운드 watcher 데몬을 실행합니다."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from cchwc.daemon.runner import run_daemon
    asyncio.run(run_daemon(foreground=foreground))


# ──────────────────────────────────────────
# doctor
# ──────────────────────────────────────────

@app.command()
def doctor() -> None:
    """환경 점검을 수행합니다."""
    import shutil

    from cchwc.config import Settings, get_config_path
    settings = Settings()

    console.print("[bold]cchwc doctor[/bold]\n")

    claude_path = shutil.which(settings.claude_bin)
    codex_path = shutil.which(settings.codex_bin)
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")
    uv_path = shutil.which("uv")

    def ok(label, path):
        if path:
            console.print(f"  [green]✓[/green] {label}: {path}")
        else:
            console.print(f"  [red]✗[/red] {label}: 설치 안 됨")

    ok("claude CLI", claude_path)
    ok("codex CLI",  codex_path)
    ok("node",       node_path)
    ok("npm",        npm_path)
    ok("uv",         uv_path)

    console.print()
    console.print(f"  config     : {get_config_path()} ({'exists' if get_config_path().exists() else 'not yet'})")
    console.print(f"  DB path    : {settings.db_path} ({'exists' if settings.db_path.exists() else 'not yet'})")
    console.print(f"  Claude root: {settings.claude_root} ({'✓' if settings.claude_root.exists() else '✗'})")
    console.print(f"  Codex root : {settings.codex_root} ({'✓' if settings.codex_root.exists() else '✗'})")
    console.print(f"  scan_mode  : {settings.scan_mode}")

    if not claude_path:
        console.print("\n  [yellow]→ Claude CLI 설치:[/yellow] npm install -g @anthropic-ai/claude-code")
        console.print("  [yellow]→ 로그인:[/yellow] claude login")
    if not codex_path:
        console.print("\n  [yellow]→ Codex CLI 설치:[/yellow] npm install -g @openai/codex")
        console.print("  [yellow]→ 로그인:[/yellow] codex login")


# ──────────────────────────────────────────
# orchestrate shortcuts
# ──────────────────────────────────────────

@app.command()
def compare(
    prompt: str = typer.Argument(help="비교할 프롬프트"),
    cwd: str = typer.Option(".", help="작업 디렉토리"),
) -> None:
    """Compare 모드: 같은 프롬프트를 양쪽에 보내고 비교합니다."""
    asyncio.run(_run_mode("compare", prompt, cwd))


@app.command()
def review(
    prompt: str = typer.Argument(help="리뷰할 프롬프트"),
    implementer: str = typer.Option("claude", help="구현 에이전트"),
    reviewer_agent: str = typer.Option("codex", "--reviewer", help="리뷰 에이전트"),
    cwd: str = typer.Option(".", help="작업 디렉토리"),
) -> None:
    """Review 모드: 한쪽이 구현, 다른 쪽이 리뷰합니다."""
    asyncio.run(_run_mode("review", prompt, cwd, config={"implementer": implementer, "reviewer": reviewer_agent}))


@app.command()
def debate(
    prompt: str = typer.Argument(help="토론 주제"),
    max_rounds: int = typer.Option(3, help="최대 라운드"),
    cwd: str = typer.Option(".", help="작업 디렉토리"),
) -> None:
    """Debate 모드: 양쪽이 토론하고 judge가 판정합니다."""
    asyncio.run(_run_mode("debate", prompt, cwd, config={"max_rounds": max_rounds}))


async def _run_mode(mode: str, prompt: str, cwd: str, config: dict | None = None) -> None:
    import json

    from cchwc.orchestrator.modes.compare import CompareMode
    from cchwc.orchestrator.modes.debate import DebateMode
    from cchwc.orchestrator.modes.review import ReviewMode

    modes = {"compare": CompareMode, "review": ReviewMode, "debate": DebateMode}
    mode_cls = modes[mode]()

    async def emit(event_data: str):
        data = json.loads(event_data)
        if data.get("type") == "status":
            console.print(f"[dim]{data['text']}[/dim]")
        elif data.get("type") == "result":
            console.print(f"\n[bold cyan]{data.get('agent', '')}[/bold cyan] [dim]({data.get('role', '')})[/dim]:")
            console.print(data.get("text", ""))
        elif data.get("type") == "error":
            console.print(f"[red]Error ({data.get('agent', '')}): {data.get('text', '')}[/red]")

    result = await mode_cls.execute(prompt=prompt, cwd=cwd, config=config or {}, run_id=0, emit=emit)
    console.print(f"\n[bold green]완료![/bold green] 토큰: {result.get('total_tokens', 0):,}")


# ──────────────────────────────────────────
# setup wizard
# ──────────────────────────────────────────

@app.command()
def setup(
    skip_deps: bool = typer.Option(False, "--skip-deps", help="이미 uv sync를 실행한 경우 의존성 동기화 생략"),
    yes: bool = typer.Option(False, "--yes", "-y", envvar="CCHWC_SETUP_NONINTERACTIVE", help="비대화형 기본 설정 사용"),
    lang: str = typer.Option("en", "--lang", envvar="CCHWC_SETUP_LANG", help="'en' 또는 'ko'"),
    scope: str = typer.Option("global", "--scope", envvar="CCHWC_SETUP_SCOPE", help="'global', 'current', 'project'"),
    cwd: list[str] = typer.Option([], "--cwd", "-c", help="비대화형 project scope에서 저장할 경로"),
    install_agent_clis: bool = typer.Option(
        False,
        "--install-agent-clis/--no-agent-clis",
        envvar="CCHWC_SETUP_INSTALL_AGENT_CLIS",
        help="비대화형 모드에서 Claude/Codex CLI 자동 설치",
    ),
    autostart: bool = typer.Option(
        False,
        "--autostart/--no-autostart",
        envvar="CCHWC_SETUP_AUTOSTART",
        help="비대화형 모드에서 자동 시작 등록",
    ),
    slash: bool = typer.Option(
        True,
        "--slash/--no-slash",
        envvar="CCHWC_SETUP_SLASH",
        help="비대화형 모드에서 Claude Code 슬래시 커맨드 설치",
    ),
    mcp: bool = typer.Option(
        True,
        "--mcp/--no-mcp",
        envvar="CCHWC_SETUP_MCP",
        help="비대화형 모드에서 MCP 등록",
    ),
    scan: bool = typer.Option(
        True,
        "--scan/--no-scan",
        envvar="CCHWC_SETUP_SCAN",
        help="비대화형 모드에서 초기 스캔 실행",
    ),
) -> None:
    """대화형 설치 마법사를 실행합니다."""
    from cchwc.setup_wizard import run_wizard
    run_wizard(
        skip_deps=skip_deps,
        non_interactive=yes,
        lang=lang,
        scope=scope,
        roots=cwd,
        install_agent_clis=install_agent_clis,
        autostart=autostart,
        slash=slash,
        mcp=mcp,
        scan=scan,
    )


# ──────────────────────────────────────────
# MCP server
# ──────────────────────────────────────────

@app.command("mcp-server")
def mcp_server() -> None:
    """MCP 서버를 실행합니다 (Claude Code 연동용 — stdio transport)."""
    from cchwc.mcp_server import run
    run()


# ──────────────────────────────────────────
# install-commands  (슬래시 커맨드 + MCP 등록)
# ──────────────────────────────────────────

INSTALL_DIR = Path(__file__).parent.parent.parent.resolve()

_SLASH_TEMPLATES: dict[str, str] = {
    "cchwc-compare": """\
두 에이전트(Claude Code + Codex)에 같은 프롬프트를 동시에 보내고 결과를 비교합니다.

Bash 도구를 사용해 아래 명령을 실행하고 결과를 보여주세요:

```bash
cchwc compare "$ARGUMENTS"
```

두 응답을 나란히 표시하고 핵심 차이점을 요약해 주세요.
""",
    "cchwc-review": """\
한 에이전트가 구현하고 다른 에이전트가 코드 리뷰를 수행합니다.

Bash 도구를 사용해 아래 명령을 실행하고 결과를 보여주세요:

```bash
cchwc review "$ARGUMENTS"
```

구현 결과와 리뷰 피드백, 수정 사항을 순서대로 정리해 주세요.
""",
    "cchwc-debate": """\
두 에이전트가 주제를 놓고 토론하고 judge가 수렴 여부를 판정합니다.

Bash 도구를 사용해 아래 명령을 실행하고 결과를 보여주세요:

```bash
cchwc debate "$ARGUMENTS"
```

각 라운드의 논점과 최종 판정을 정리해 주세요.
""",
    "cchwc-start": """\
cchwc 대시보드 서버를 백그라운드에서 시작합니다.

Bash 도구로 아래 명령을 실행하세요:

```bash
cchwc start --open
```

서버가 시작되면 브라우저에서 http://127.0.0.1:7878 이 열립니다.
""",
    "cchwc-stop": """\
실행 중인 cchwc 서버를 종료합니다.

Bash 도구로 아래 명령을 실행하세요:

```bash
cchwc stop
```
""",
    "cchwc-open": """\
브라우저에서 cchwc 대시보드를 엽니다.

Bash 도구로 아래 명령을 실행하세요:

```bash
cchwc open
```
""",
}


@app.command("install-commands")
def install_commands(
    scope: str = typer.Option("global", help="'global' (~/.claude) 또는 'project' (.claude)"),
    mcp: bool = typer.Option(True, help="MCP 서버도 ~/.claude/mcp.json에 등록"),
) -> None:
    """Claude Code 슬래시 커맨드와 MCP 서버를 설치합니다.

    설치 후 Claude Code에서 /cchwc-compare, /cchwc-review, /cchwc-debate 사용 가능.
    """
    import shutil

    install_dir = INSTALL_DIR

    base = Path.home() / ".claude" if scope == "global" else Path.cwd() / ".claude"

    # ── 슬래시 커맨드 ──────────────────────────────────────────────────────
    commands_dir = base / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)

    for name, content in _SLASH_TEMPLATES.items():
        path = commands_dir / f"{name}.md"
        path.write_text(content, encoding="utf-8")
        console.print(f"  [green]✓[/green] {path}")

    console.print(f"\n  슬래시 커맨드 설치 완료 ({scope})")
    console.print("  Claude Code에서: /cchwc-compare, /cchwc-review, /cchwc-debate")

    # ── MCP 서버 등록 ──────────────────────────────────────────────────────
    if not mcp:
        return

    mcp_json_path = base / "mcp.json"

    existing: dict = {}
    if mcp_json_path.exists():
        import json
        with open(mcp_json_path, encoding="utf-8") as f:
            existing = json.load(f)

    uv_path = shutil.which("uv") or "uv"
    existing.setdefault("mcpServers", {})["cchwc"] = {
        "command": uv_path,
        "args": ["run", "--no-dev", "--project", str(install_dir), "cchwc", "mcp-server"],
        "env": {"UV_CACHE_DIR": str(install_dir / ".uv-cache")},
        "description": "cchwc — Claude+Codex 오케스트레이션 (compare/review/debate)",
    }

    import json
    mcp_json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(mcp_json_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)

    console.print(f"\n  [green]✓[/green] MCP 서버 등록: {mcp_json_path}")
    console.print("  Claude Code 재시작 후 compare/review/debate 도구 사용 가능")


if __name__ == "__main__":
    app()
