"""cchwc 대화형 설치 마법사 — rich 기반 oh-my-opencode 스타일 UX."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.rule import Rule
from rich.status import Status
from rich.table import Table
from rich.text import Text

console = Console()
INSTALL_DIR = Path(__file__).parent.parent.parent.resolve()


# ─────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    console.print(f"  [bold green]✓[/bold green]  {msg}")


def _fail(msg: str) -> None:
    console.print(f"  [bold red]✗[/bold red]  {msg}")


def _info(msg: str) -> None:
    console.print(f"  [dim]→[/dim]  {msg}")


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _which(name: str) -> str | None:
    return shutil.which(name)


# ─────────────────────────────────────────────────────────────────
# Steps
# ─────────────────────────────────────────────────────────────────

def step_welcome() -> None:
    welcome = Text.assemble(
        ("cchwc", "bold white"),
        ("  ·  ", "dim"),
        ("Claude Code + Codex Session Hub", "white"),
    )
    console.print()
    console.print(Panel(
        Align.center(welcome),
        subtitle="[dim]설치 마법사[/dim]",
        border_style="bright_black",
        padding=(1, 4),
    ))
    console.print()


def step_check_prerequisites() -> dict[str, str | None]:
    console.print(Rule("[bold]1 / 6  시스템 요구사항[/bold]", style="bright_black"))
    console.print()

    checks = {
        "python": _which("python") or _which("python3"),
        "node":   _which("node"),
        "npm":    _which("npm"),
        "git":    _which("git"),
        "uv":     _which("uv") or _which(str(Path.home() / ".local" / "bin" / "uv")),
    }

    for name, path in checks.items():
        if path:
            try:
                v = _run([path, "--version"]).stdout.strip().splitlines()[0]
            except Exception:
                v = "설치됨"
            _ok(f"{name}  [dim]{v}[/dim]")
        else:
            _fail(f"{name}  [dim]설치 안 됨[/dim]")

    if not checks["node"]:
        console.print()
        console.print("  [yellow]Node.js가 필요합니다.[/yellow]")
        console.print("  [dim]https://nodejs.org 에서 LTS 버전을 설치한 뒤 다시 실행하세요.[/dim]")
        sys.exit(1)

    console.print()
    return checks


def step_install_uv(checks: dict) -> None:
    if checks.get("uv"):
        return

    console.print(Rule("[bold]2 / 6  uv 설치[/bold]", style="bright_black"))
    console.print()

    if not Confirm.ask("  uv 패키지 매니저를 설치할까요?", default=True):
        console.print("  [red]uv 없이 계속할 수 없습니다.[/red]")
        sys.exit(1)

    with Status("  uv 설치 중…", spinner="dots"):
        result = subprocess.run(
            ["powershell", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"],
            capture_output=True, text=True,
        )

    if result.returncode == 0:
        uv_path = str(Path.home() / ".local" / "bin" / "uv.exe")
        checks["uv"] = uv_path
        _ok(f"uv 설치 완료: {uv_path}")
    else:
        _fail("uv 설치 실패")
        console.print(f"  [dim]{result.stderr}[/dim]")
        sys.exit(1)
    console.print()


def step_sync_deps(checks: dict) -> None:
    console.print(Rule("[bold]3 / 6  의존성 설치[/bold]", style="bright_black"))
    console.print()

    uv = checks.get("uv", "uv")
    with Status("  패키지 설치 중…", spinner="dots"):
        result = _run([uv, "sync"], cwd=str(INSTALL_DIR))

    if result.returncode == 0:
        _ok("의존성 설치 완료")
    else:
        _fail("의존성 설치 실패")
        console.print(f"  [dim]{result.stderr}[/dim]")
        sys.exit(1)
    console.print()


def step_claude_cli(checks: dict) -> None:
    console.print(Rule("[bold]4 / 6  Claude CLI[/bold]", style="bright_black"))
    console.print()

    claude = _which("claude")
    if claude:
        _ok(f"claude CLI: {claude}")
    else:
        _fail("claude CLI: 설치 안 됨")
        if Confirm.ask("  지금 설치할까요? (npm install -g @anthropic-ai/claude-code)", default=True):
            with Status("  설치 중…", spinner="dots"):
                result = _run(["npm", "install", "-g", "@anthropic-ai/claude-code"])
            if result.returncode == 0:
                _ok("claude CLI 설치 완료")
            else:
                _fail("설치 실패 — npm 출력을 확인하세요")
                console.print(f"  [dim]{result.stderr[:400]}[/dim]")

    console.print()
    console.print("  [bold]로그인 상태 확인[/bold]")
    claude_ok = _run(["claude", "config", "list"]).returncode == 0 if _which("claude") else False

    if claude_ok:
        _ok("Claude 로그인 확인됨")
    else:
        _info("로그인이 필요합니다. 아래 명령을 실행하세요:")
        console.print()
        console.print("    [bold cyan]claude login[/bold cyan]")
        console.print()
        if Confirm.ask("  로그인을 지금 실행할까요?", default=True):
            subprocess.run(["claude", "login"])
    console.print()


def step_codex_cli() -> None:
    console.print(Rule("[bold]5 / 6  Codex CLI[/bold]", style="bright_black"))
    console.print()

    codex = _which("codex")
    if codex:
        _ok(f"codex CLI: {codex}")
    else:
        _fail("codex CLI: 설치 안 됨")
        if Confirm.ask("  지금 설치할까요? (npm install -g @openai/codex)", default=True):
            with Status("  설치 중…", spinner="dots"):
                result = _run(["npm", "install", "-g", "@openai/codex"])
            if result.returncode == 0:
                _ok("codex CLI 설치 완료")
            else:
                _fail("설치 실패")
                console.print(f"  [dim]{result.stderr[:400]}[/dim]")

    console.print()
    _info("codex 로그인이 필요하면: [bold cyan]codex login[/bold cyan]")
    console.print()


def step_configure() -> dict:
    console.print(Rule("[bold]6 / 6  초기 설정[/bold]", style="bright_black"))
    console.print()

    # 스캔 범위
    console.print("  [bold]스캔 범위[/bold]")
    console.print("  [dim]1[/dim]  전체  [dim](모든 Claude/Codex 세션 — ~/.claude/projects 전체)[/dim]")
    console.print("  [dim]2[/dim]  현재 디렉토리  [dim](지금 있는 프로젝트만)[/dim]")
    console.print("  [dim]3[/dim]  경로 직접 입력")
    console.print()

    choice = Prompt.ask("  선택", choices=["1", "2", "3"], default="1")

    scan_roots: list[str] | None
    if choice == "1":
        scan_roots = None
        _ok("전체 스캔 모드")
    elif choice == "2":
        scan_roots = [str(Path.cwd())]
        _ok(f"현재 디렉토리: {scan_roots[0]}")
    else:
        path_str = Prompt.ask("  경로 입력")
        scan_roots = [path_str]
        _ok(f"지정 경로: {path_str}")

    console.print()

    # 슬래시 커맨드 / MCP
    install_slash = Confirm.ask("  Claude Code 슬래시 커맨드 설치? (/cchwc-compare 등)", default=True)
    install_mcp   = Confirm.ask("  MCP 서버 등록? (Claude Code에서 tool call로 사용)", default=True)

    console.print()
    return {
        "scan_roots": scan_roots,
        "install_slash": install_slash,
        "install_mcp": install_mcp,
    }


def step_scan(checks: dict, scan_roots: list[str] | None) -> None:
    uv = checks.get("uv", "uv")
    cmd = [uv, "run", "--project", str(INSTALL_DIR), "cchwc", "scan"]
    if scan_roots is None:
        cmd += ["--global"]
    else:
        for r in scan_roots:
            cmd += ["--cwd", r]

    with Status("  세션 인덱싱 중…", spinner="dots"):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(INSTALL_DIR))

    for line in result.stdout.strip().splitlines():
        _ok(line.strip())


def step_install_integrations(install_slash: bool, install_mcp: bool, checks: dict) -> None:
    if not (install_slash or install_mcp):
        return

    uv = checks.get("uv", "uv")
    cmd = [uv, "run", "--project", str(INSTALL_DIR), "cchwc", "install-commands"]
    if not install_mcp:
        cmd += ["--no-mcp"]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(INSTALL_DIR))
    for line in result.stdout.strip().splitlines():
        _ok(line.strip())


def step_done() -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim")
    table.add_column()
    table.add_row("서버 시작",  f"[bold cyan]cd {INSTALL_DIR} && uv run python run.py[/bold cyan]")
    table.add_row("브라우저",   "[bold cyan]http://127.0.0.1:7878[/bold cyan]")
    table.add_row("슬래시 커맨드", "[bold cyan]/cchwc-compare[/bold cyan]  /cchwc-review  /cchwc-debate")
    table.add_row("스캔 추가",  "[bold cyan]cchwc config add-project <path>[/bold cyan]")
    table.add_row("전체 도움말", "[bold cyan]cchwc --help[/bold cyan]")

    console.print()
    console.print(Panel(
        Align.center(table),
        title="[bold green]설치 완료[/bold green]",
        border_style="green",
        padding=(1, 4),
    ))
    console.print()


# ─────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────

def run_wizard() -> None:
    step_welcome()
    checks = step_check_prerequisites()
    step_install_uv(checks)
    step_sync_deps(checks)
    step_claude_cli(checks)
    step_codex_cli()
    cfg = step_configure()
    step_scan(checks, cfg["scan_roots"])
    step_install_integrations(cfg["install_slash"], cfg["install_mcp"], checks)
    step_done()
