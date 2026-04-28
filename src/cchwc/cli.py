import asyncio
import logging

import typer
from rich.console import Console

app = typer.Typer(name="cchwc", help="Claude Code + Codex CLI 세션 통합 관리 도구")
console = Console()


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="서버 호스트"),
    port: int = typer.Option(7878, help="서버 포트"),
) -> None:
    """웹 서버를 시작합니다."""
    import uvicorn

    from cchwc.server.app import create_app

    application = create_app()
    uvicorn.run(application, host=host, port=port)


@app.command()
def scan(
    claude: bool = typer.Option(True, help="Claude 세션 스캔"),
    codex: bool = typer.Option(True, help="Codex 세션 스캔"),
) -> None:
    """모든 세션을 풀스캔합니다."""
    asyncio.run(_scan(claude, codex))


async def _scan(claude: bool, codex: bool) -> None:
    from cchwc.adapters.claude_adapter import ClaudeAdapter
    from cchwc.adapters.codex_adapter import CodexAdapter
    from cchwc.config import Settings
    from cchwc.core.db import get_engine, get_session_factory
    from cchwc.core.models import Base
    from cchwc.indexer.scanner import initial_scan

    settings = Settings()
    engine = get_engine(settings)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = get_session_factory(settings)
    adapters = []
    if claude:
        adapters.append(ClaudeAdapter(settings.claude_root))
    if codex:
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


@app.command()
def daemon(
    foreground: bool = typer.Option(False, help="포그라운드에서 실행"),
) -> None:
    """백그라운드 watcher 데몬을 실행합니다."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    from cchwc.daemon.runner import run_daemon

    asyncio.run(run_daemon(foreground=foreground))


@app.command()
def doctor() -> None:
    """환경 점검을 수행합니다."""
    import shutil

    from cchwc.config import Settings

    settings = Settings()

    console.print("[bold]cchwc doctor[/bold]\n")

    claude_path = shutil.which(settings.claude_bin)
    codex_path = shutil.which(settings.codex_bin)

    if claude_path:
        console.print(f"  claude CLI: [green]found[/green] ({claude_path})")
    else:
        console.print(f"  claude CLI: [red]not found[/red] (looked for '{settings.claude_bin}')")

    if codex_path:
        console.print(f"  codex CLI: [green]found[/green] ({codex_path})")
    else:
        console.print(f"  codex CLI: [red]not found[/red] (looked for '{settings.codex_bin}')")

    console.print(f"\n  DB path: {settings.db_path}")
    claude_status = "exists" if settings.claude_root.exists() else "not found"
    codex_status = "exists" if settings.codex_root.exists() else "not found"
    console.print(f"  Claude root: {settings.claude_root} ({claude_status})")
    console.print(f"  Codex root: {settings.codex_root} ({codex_status})")


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
    reviewer: str = typer.Option("codex", help="리뷰 에이전트"),
    cwd: str = typer.Option(".", help="작업 디렉토리"),
) -> None:
    """Review 모드: 한쪽이 구현, 다른 쪽이 리뷰합니다."""
    asyncio.run(_run_mode("review", prompt, cwd, config={"implementer": implementer, "reviewer": reviewer}))


@app.command()
def debate(
    prompt: str = typer.Argument(help="토론 주제"),
    max_rounds: int = typer.Option(3, help="최대 라운드"),
    cwd: str = typer.Option(".", help="작업 디렉토리"),
) -> None:
    """Debate 모드: 양쪽이 토론하고 judge가 판정합니다."""
    asyncio.run(_run_mode("debate", prompt, cwd, config={"max_rounds": max_rounds}))


async def _run_mode(mode: str, prompt: str, cwd: str, config: dict | None = None) -> None:
    from cchwc.orchestrator.modes.compare import CompareMode
    from cchwc.orchestrator.modes.debate import DebateMode
    from cchwc.orchestrator.modes.review import ReviewMode

    modes = {"compare": CompareMode, "review": ReviewMode, "debate": DebateMode}
    mode_cls = modes[mode]()

    async def emit(event_data: str):
        import json
        data = json.loads(event_data)
        if data.get("type") == "status":
            console.print(f"[dim]{data['text']}[/dim]")
        elif data.get("type") == "result":
            agent = data.get("agent", "")
            role = data.get("role", "")
            console.print(f"\n[bold cyan]{agent}[/bold cyan] ([dim]{role}[/dim]):")
            console.print(data.get("text", ""))
        elif data.get("type") == "error":
            console.print(f"[red]Error ({data.get('agent', '')}): {data.get('text', '')}[/red]")

    result = await mode_cls.execute(
        prompt=prompt,
        cwd=cwd,
        config=config or {},
        run_id=0,
        emit=emit,
    )

    console.print(f"\n[bold green]Done![/bold green] Tokens: {result.get('total_tokens', 0):,}")


if __name__ == "__main__":
    app()
