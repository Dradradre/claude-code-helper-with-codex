"""cchwc 설치 마법사 — questionary 기반, 다국어 지원."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path

import questionary
from questionary import Style
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.status import Status
from rich.table import Table

from cchwc.i18n import set_lang, t

IS_WIN = platform.system() == "Windows"
INSTALL_DIR = Path(__file__).parent.parent.parent.resolve()
console = Console()

_STYLE = Style([
    ("qmark",     "fg:#00b4d8 bold"),
    ("question",  "bold"),
    ("answer",    "fg:#90e0ef bold"),
    ("pointer",   "fg:#00b4d8 bold"),
    ("selected",  "fg:#caf0f8"),
    ("separator", "fg:#444444"),
    ("instruction", "fg:#888888"),
])


# ─────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────

def _ok(msg: str)   -> None: console.print(f"  [bold green]✓[/bold green]  {msg}")
def _fail(msg: str) -> None: console.print(f"  [bold red]✗[/bold red]  {msg}")
def _info(msg: str) -> None: console.print(f"  [dim]→[/dim]  {msg}")
def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


# ─────────────────────────────────────────────────────────────────
# steps
# ─────────────────────────────────────────────────────────────────

def step_language() -> str:
    lang = questionary.select(
        "Select language / 언어를 선택하세요",
        choices=["English", "한국어"],
        style=_STYLE,
    ).ask()
    if lang is None:
        sys.exit(0)
    chosen = "ko" if lang == "한국어" else "en"
    set_lang(chosen)
    return chosen


def step_welcome() -> None:
    tbl = Table.grid(padding=(0, 1))
    tbl.add_column()
    tbl.add_row("[bold white]cchwc[/bold white]  [dim]—[/dim]  [white]Claude Code + Codex CLI Session Hub[/white]")
    tbl.add_row(f"[dim]{t('welcome_tagline')}[/dim]")
    console.print()
    console.print(Panel(Align.center(tbl), subtitle=f"[dim]{t('welcome_subtitle')}[/dim]",
                        border_style="bright_black", padding=(1, 6)))
    console.print()


def step_prereqs() -> dict:
    console.print(Rule(f"[bold]{t('step_prereqs')}[/bold]", style="bright_black"))
    console.print()

    checks: dict[str, str | None] = {
        "node":   shutil.which("node"),
        "npm":    shutil.which("npm"),
        "git":    shutil.which("git"),
        "uv":     shutil.which("uv") or shutil.which(
                      str(Path.home() / ".local" / "bin" / ("uv.exe" if IS_WIN else "uv"))),
    }
    for name, path in checks.items():
        if path:
            try:
                ver = _run([path, "--version"]).stdout.strip().splitlines()[0]
            except Exception:
                ver = t("found")
            _ok(f"{name}  [dim]{ver}[/dim]")
        else:
            _fail(f"{name}  [dim]{t('not_found')}[/dim]")

    if not checks["node"]:
        console.print()
        console.print(f"  [yellow]{t('node_missing')}[/yellow]")
        sys.exit(1)
    console.print()
    return checks


def step_install_uv(checks: dict) -> None:
    if checks.get("uv"):
        return
    console.print(Rule(f"[bold]{t('step_uv')}[/bold]", style="bright_black"))
    console.print()

    if not questionary.confirm(t("uv_install_prompt"), default=True, style=_STYLE).ask():
        console.print(f"  [red]{t('uv_install_failed')}[/red]")
        sys.exit(1)

    with Status(f"  {t('installing')}", spinner="dots"):
        if IS_WIN:
            result = subprocess.run(
                ["powershell", "-Command", "irm https://astral.sh/uv/install.ps1 | iex"],
                capture_output=True, text=True)
        else:
            result = subprocess.run(
                ["sh", "-c", "curl -LsSf https://astral.sh/uv/install.sh | sh"],
                capture_output=True, text=True)

    if result.returncode == 0:
        bin_name = "uv.exe" if IS_WIN else "uv"
        uv_path = str(Path.home() / ".local" / "bin" / bin_name)
        checks["uv"] = uv_path
        _ok(f"uv  [dim]{uv_path}[/dim]")
    else:
        _fail(t("uv_install_failed"))
        sys.exit(1)
    console.print()


def step_sync_deps(checks: dict) -> None:
    console.print(Rule(f"[bold]{t('step_deps')}[/bold]", style="bright_black"))
    console.print()
    uv = checks.get("uv", "uv")
    with Status(f"  {t('installing')}", spinner="dots"):
        result = _run([uv, "sync"], cwd=str(INSTALL_DIR))
    if result.returncode == 0:
        _ok(t("done"))
    else:
        _fail(result.stderr[:300])
        sys.exit(1)
    console.print()


def _install_cli(label: str, pkg: str, check_cmd: str, checks: dict,
                  prompt_key: str, hint_key: str) -> None:
    path = shutil.which(check_cmd)
    if path:
        _ok(f"{check_cmd}  [dim]{path}[/dim]")
        return
    _fail(f"{check_cmd}  [dim]{t('not_found')}[/dim]")
    if questionary.confirm(t(prompt_key), default=True, style=_STYLE).ask():
        with Status(f"  {t('installing')}", spinner="dots"):
            result = subprocess.run(
                ["npm", "install", "-g", pkg],
                capture_output=True, text=True, shell=IS_WIN,
            )
        if result.returncode == 0:
            _ok(f"{check_cmd}  {t('done')}")
        else:
            _fail(t("install_failed"))
    else:
        _info(t(hint_key))


def step_claude_cli(checks: dict) -> None:
    console.print(Rule(f"[bold]{t('step_claude')}[/bold]", style="bright_black"))
    console.print()
    _install_cli("Claude", "@anthropic-ai/claude-code", "claude", checks,
                 "install_claude_prompt", "login_hint_claude")

    claude = shutil.which("claude")
    if claude:
        # 이미 로그인 여부 확인 (claude config list 로 체크)
        probe = subprocess.run(
            ["claude", "config", "list"],
            capture_output=True, text=True, shell=IS_WIN,
        )
        if probe.returncode == 0:
            _ok(t("login_ok"))
        else:
            console.print()
            console.print(f"  [yellow]{t('login_manual')}[/yellow]")
            console.print("  [bold cyan]  claude login[/bold cyan]")
            console.print(f"  [dim]{t('login_manual_hint')}[/dim]")
            questionary.press_any_key_to_continue(t("login_press_key"), style=_STYLE).ask()
    console.print()


def step_codex_cli() -> None:
    console.print(Rule(f"[bold]{t('step_codex')}[/bold]", style="bright_black"))
    console.print()
    _install_cli("Codex", "@openai/codex", "codex", {},
                 "install_codex_prompt", "login_hint_codex")

    codex = shutil.which("codex")
    if codex:
        # codex config get api-key 로 로그인 여부 확인
        probe = subprocess.run(
            ["codex", "config", "get", "api-key"],
            capture_output=True, text=True, shell=IS_WIN,
        )
        if probe.returncode == 0 and probe.stdout.strip():
            _ok(t("codex_login_ok"))
        else:
            console.print()
            console.print(f"  [yellow]{t('codex_login_manual')}[/yellow]")
            console.print("  [bold cyan]  codex login[/bold cyan]")
            console.print(f"  [dim]{t('login_manual_hint')}[/dim]")
            questionary.press_any_key_to_continue(t("login_press_key"), style=_STYLE).ask()
    console.print()


def step_scope() -> list[str] | None:
    """None = global, list = project roots."""
    console.print(Rule(f"[bold]{t('step_scope')}[/bold]", style="bright_black"))
    console.print()

    choice = questionary.select(
        t("scope_prompt"),
        choices=[t("scope_global"), t("scope_current"), t("scope_custom")],
        style=_STYLE,
    ).ask()
    if choice is None:
        return None

    if choice == t("scope_global"):
        _ok(t("scope_global"))
        console.print()
        return None

    if choice == t("scope_current"):
        path = str(Path.cwd())
        _ok(path)
        console.print()
        return [path]

    # custom
    paths: list[str] = []
    while True:
        p = questionary.text(t("scope_path_prompt"), style=_STYLE).ask()
        if not p:
            break
        resolved = str(Path(p).resolve())
        paths.append(resolved)
        _ok(resolved)

    if not paths:
        _info(t("scope_no_paths"))
        paths = [str(Path.cwd())]
    console.print()
    return paths


def step_autostart(checks: dict) -> bool:
    console.print(Rule(f"[bold]{t('step_autostart')}[/bold]", style="bright_black"))
    console.print()

    if not questionary.confirm(t("autostart_prompt"), default=True, style=_STYLE).ask():
        _info(t("autostart_skip"))
        console.print()
        return False

    from cchwc.server_runner import install_autostart
    uv = checks.get("uv") or shutil.which("uv") or "uv"
    ok = install_autostart(uv_path=uv, install_dir=INSTALL_DIR)
    if ok:
        _ok(t("autostart_ok"))
    else:
        _fail(t("autostart_failed"))
    console.print()
    return ok


def step_integrations() -> dict:
    console.print(Rule(f"[bold]{t('step_integrations')}[/bold]", style="bright_black"))
    console.print()

    do_slash = questionary.confirm(t("slash_prompt"), default=True, style=_STYLE).ask() or False
    do_mcp   = questionary.confirm(t("mcp_prompt"),   default=True, style=_STYLE).ask() or False

    if do_slash or do_mcp:
        try:
            _install_integrations(do_mcp)
            _ok(t("integration_ok"))
        except Exception as e:
            _fail(str(e))
    console.print()
    return {"slash": do_slash, "mcp": do_mcp}


def _install_integrations(do_mcp: bool) -> None:
    import json

    from cchwc.cli import _SLASH_TEMPLATES

    commands_dir = Path.home() / ".claude" / "commands"
    commands_dir.mkdir(parents=True, exist_ok=True)
    for name, content in _SLASH_TEMPLATES.items():
        (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")

    # start/stop slash commands
    _extra = {
        "cchwc-start": "Use Bash to run: cchwc start\nThen open: http://127.0.0.1:7878",
        "cchwc-stop":  "Use Bash to run: cchwc stop",
        "cchwc-open":  "Use Bash to run: cchwc open",
    }
    for name, content in _extra.items():
        (commands_dir / f"{name}.md").write_text(content, encoding="utf-8")

    if not do_mcp:
        return

    mcp_path = Path.home() / ".claude" / "mcp.json"
    existing: dict = {}
    if mcp_path.exists():
        with open(mcp_path, encoding="utf-8") as f:
            existing = json.load(f)
    uv_bin = shutil.which("uv") or "uv"
    existing.setdefault("mcpServers", {})["cchwc"] = {
        "command": uv_bin,
        "args": ["run", "--project", str(INSTALL_DIR), "cchwc", "mcp-server"],
    }
    with open(mcp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def step_scan(checks: dict, scan_roots: list[str] | None) -> None:
    console.print(Rule(f"[bold]{t('step_scan')}[/bold]", style="bright_black"))
    console.print()
    uv = checks.get("uv", "uv")
    cmd = [uv, "run", "--project", str(INSTALL_DIR), "cchwc", "scan"]
    if scan_roots is None:
        cmd += ["--global"]
    else:
        for r in scan_roots:
            cmd += ["--cwd", r]

    with Status(f"  {t('scanning')}", spinner="dots"):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(INSTALL_DIR))

    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line:
            _ok(line)
    console.print()


def step_done(autostart_ok: bool, integrations: dict) -> None:
    console.print(Rule(f"[bold green]{t('step_done')}[/bold green]", style="green"))
    console.print()

    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(style="dim", no_wrap=True)
    tbl.add_column()

    if autostart_ok:
        tbl.add_row("", f"[green]{t('done_autostart_on')}[/green]")
    else:
        tbl.add_row("start", f"[cyan]{t('done_autostart_off')}[/cyan]")

    tbl.add_row("browser", f"[cyan]{t('done_url')}[/cyan]")

    if integrations.get("slash"):
        tbl.add_row("slash", f"[dim]{t('done_slash')}[/dim]")

    tbl.add_row("tip", f"[dim]{t('done_tip')}[/dim]")

    console.print(Panel(tbl, border_style="green", padding=(1, 4)))
    console.print()


# ─────────────────────────────────────────────────────────────────
# entry point
# ─────────────────────────────────────────────────────────────────

def run_wizard() -> None:
    try:
        step_language()
        step_welcome()
        checks = step_prereqs()
        step_install_uv(checks)
        step_sync_deps(checks)
        step_claude_cli(checks)
        step_codex_cli()
        scan_roots = step_scope()
        autostart_ok = step_autostart(checks)
        integrations = step_integrations()
        step_scan(checks, scan_roots)
        step_done(autostart_ok, integrations)
    except KeyboardInterrupt:
        console.print("\n\n  [dim]Setup cancelled.[/dim]\n")
        sys.exit(0)
