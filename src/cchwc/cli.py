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

@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="서버 호스트"),
    port: int = typer.Option(7878, help="서버 포트"),
) -> None:
    """웹 서버를 시작합니다."""
    import uvicorn

    from cchwc.server.app import create_app
    uvicorn.run(create_app(), host=host, port=port)


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
    from cchwc.config import Settings
    s = Settings()
    console.print(f"scan_mode  : [bold]{s.scan_mode}[/bold]")
    console.print(f"scan_roots : {s.scan_roots or '(설정 없음 — 현재 디렉토리 기본값)'}")
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
    import tomllib

    import tomli_w  # type: ignore[import]
    config_path = Path.home() / ".cchwc" / "config.toml"
    config_path.parent.mkdir(parents=True, exist_ok=True)

    data: dict = {}
    if config_path.exists():
        with open(config_path, "rb") as f:
            data = tomllib.load(f)

    if action == "mode":
        data.setdefault("scan", {})["mode"] = value
    elif action == "add":
        roots = data.setdefault("scan", {}).setdefault("roots", [])
        if value not in roots:
            roots.append(value)
            console.print(f"[green]추가됨: {value}[/green]")
        else:
            console.print(f"[yellow]이미 존재: {value}[/yellow]")
    elif action == "remove":
        roots = data.get("scan", {}).get("roots", [])
        if value in roots:
            roots.remove(value)
            console.print(f"[green]제거됨: {value}[/green]")
        else:
            console.print(f"[yellow]목록에 없음: {value}[/yellow]")

    with open(config_path, "wb") as f:
        tomli_w.dump(data, f)


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

    from cchwc.config import Settings
    settings = Settings()

    console.print("[bold]cchwc doctor[/bold]\n")

    claude_path = shutil.which(settings.claude_bin)
    codex_path = shutil.which(settings.codex_bin)
    node_path = shutil.which("node")
    npm_path = shutil.which("npm")

    def ok(label, path):
        if path:
            console.print(f"  [green]✓[/green] {label}: {path}")
        else:
            console.print(f"  [red]✗[/red] {label}: 설치 안 됨")

    ok("claude CLI", claude_path)
    ok("codex CLI",  codex_path)
    ok("node",       node_path)
    ok("npm",        npm_path)

    console.print()
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


if __name__ == "__main__":
    app()
