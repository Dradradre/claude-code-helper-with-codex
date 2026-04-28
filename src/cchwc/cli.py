import typer

app = typer.Typer(name="cchwc", help="Claude Code + Codex CLI 세션 통합 관리 도구")


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
def doctor() -> None:
    """환경 점검을 수행합니다."""
    import shutil

    from rich.console import Console

    console = Console()

    claude_path = shutil.which("claude")
    codex_path = shutil.which("codex")

    console.print("[bold]cchwc doctor[/bold]")
    console.print()

    if claude_path:
        console.print(f"  claude CLI: [green]found[/green] ({claude_path})")
    else:
        console.print("  claude CLI: [red]not found[/red]")

    if codex_path:
        console.print(f"  codex CLI: [green]found[/green] ({codex_path})")
    else:
        console.print("  codex CLI: [red]not found[/red]")


if __name__ == "__main__":
    app()
