"""cchwc 설치 마법사 — questionary 기반, 다국어 지원."""

from __future__ import annotations

import os
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
def _which(name: str) -> str | None:
    if IS_WIN and name == "npm":
        return shutil.which("npm.cmd") or shutil.which("npm.exe") or shutil.which("npm")
    return shutil.which(name)


def _subprocess_cmd(cmd: list[str]) -> list[str]:
    exe = Path(cmd[0]).suffix.lower()
    if IS_WIN and exe in {".cmd", ".bat"}:
        return ["cmd", "/c", *cmd]
    return cmd


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(_subprocess_cmd(cmd), capture_output=True, text=True, **kw)


def _ensure_uv_cache_env() -> None:
    if os.environ.get("UV_CACHE_DIR"):
        return
    cache_dir = INSTALL_DIR / ".uv-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["UV_CACHE_DIR"] = str(cache_dir)


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
        "node":   _which("node"),
        "npm":    _which("npm"),
        "git":    _which("git"),
        "uv":     _which("uv") or shutil.which(
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
    if not checks["npm"]:
        console.print(f"  [yellow]{t('npm_missing')}[/yellow]")
    console.print()
    return checks


def step_install_uv(checks: dict) -> None:
    if checks.get("uv"):
        _ensure_uv_cache_env()
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
        uv_path = _which("uv") or str(Path.home() / ".local" / "bin" / bin_name)
        checks["uv"] = uv_path
        _ensure_uv_cache_env()
        _ok(f"uv  [dim]{uv_path}[/dim]")
    else:
        _fail(t("uv_install_failed"))
        sys.exit(1)
    console.print()


def step_sync_deps(checks: dict) -> None:
    console.print(Rule(f"[bold]{t('step_deps')}[/bold]", style="bright_black"))
    console.print()
    uv = checks.get("uv", "uv")
    _ensure_uv_cache_env()
    with Status(f"  {t('installing')}", spinner="dots"):
        result = _run([uv, "sync", "--frozen", "--no-dev"], cwd=str(INSTALL_DIR))
    if result.returncode == 0:
        _ok(t("done"))
    else:
        _fail(result.stderr[:300])
        sys.exit(1)

    with Status(f"  {t('registering_cmd')}", spinner="dots"):
        result = _run([uv, "tool", "install", "--editable", str(INSTALL_DIR)])
    if result.returncode == 0:
        _ok("cchwc")
    else:
        _fail(result.stderr[:300])
        sys.exit(1)
    console.print()


def _install_cli(
    label: str,
    pkg: str,
    check_cmd: str,
    checks: dict,
    prompt_key: str,
    hint_key: str,
    *,
    interactive: bool = True,
    install_missing: bool = True,
) -> None:
    path = _which(check_cmd)
    if path:
        _ok(f"{check_cmd}  [dim]{path}[/dim]")
        return
    _fail(f"{check_cmd}  [dim]{t('not_found')}[/dim]")
    npm = checks.get("npm") or _which("npm")
    if not npm:
        _info(t("npm_missing_cli", package=pkg))
        return
    should_install = install_missing
    if interactive:
        should_install = bool(questionary.confirm(t(prompt_key), default=True, style=_STYLE).ask())
    if should_install:
        with Status(f"  {t('installing')}", spinner="dots"):
            result = _run([npm, "install", "-g", pkg])
        if result.returncode == 0:
            installed = _which(check_cmd)
            detail = f"  [dim]{installed}[/dim]" if installed else ""
            _ok(f"{check_cmd}  {t('done')}{detail}")
        else:
            _fail(result.stderr.strip()[:300] or t("install_failed"))
    else:
        _info(t(hint_key))


def step_claude_cli(checks: dict, *, interactive: bool = True, install_missing: bool = True) -> None:
    console.print(Rule(f"[bold]{t('step_claude')}[/bold]", style="bright_black"))
    console.print()
    _install_cli("Claude", "@anthropic-ai/claude-code", "claude", checks,
                 "install_claude_prompt", "login_hint_claude",
                 interactive=interactive, install_missing=install_missing)

    claude = _which("claude")
    if claude:
        try:
            probe = _run([claude, "config", "list"], timeout=8)
            authenticated = probe.returncode == 0
        except subprocess.TimeoutExpired:
            authenticated = False

        if authenticated:
            _ok(t("login_ok"))
        elif interactive:
            console.print()
            console.print(f"  [yellow]{t('login_manual')}[/yellow]")
            console.print("  [bold cyan]  claude login[/bold cyan]")
            console.print(f"  [dim]{t('login_manual_hint')}[/dim]")
            questionary.press_any_key_to_continue(t("login_press_key"), style=_STYLE).ask()
        else:
            _info(t("login_hint_claude"))
    console.print()


def step_codex_cli(checks: dict, *, interactive: bool = True, install_missing: bool = True) -> None:
    console.print(Rule(f"[bold]{t('step_codex')}[/bold]", style="bright_black"))
    console.print()
    _install_cli("Codex", "@openai/codex", "codex", checks,
                 "install_codex_prompt", "login_hint_codex",
                 interactive=interactive, install_missing=install_missing)

    codex = _which("codex")
    if codex:
        try:
            probe = _run([codex, "config", "get", "api-key"], timeout=8)
            authenticated = probe.returncode == 0 and bool(probe.stdout.strip())
        except subprocess.TimeoutExpired:
            authenticated = False

        if authenticated:
            _ok(t("codex_login_ok"))
        elif interactive:
            console.print()
            console.print(f"  [yellow]{t('codex_login_manual')}[/yellow]")
            console.print("  [bold cyan]  codex login[/bold cyan]")
            console.print(f"  [dim]{t('login_manual_hint')}[/dim]")
            questionary.press_any_key_to_continue(t("login_press_key"), style=_STYLE).ask()
        else:
            _info(t("login_hint_codex"))
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
    uv = checks.get("uv") or _which("uv") or "uv"
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
    uv_bin = _which("uv") or "uv"
    existing.setdefault("mcpServers", {})["cchwc"] = {
        "command": uv_bin,
        "args": ["run", "--no-dev", "--project", str(INSTALL_DIR), "cchwc", "mcp-server"],
        "env": {"UV_CACHE_DIR": str(INSTALL_DIR / ".uv-cache")},
    }
    with open(mcp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)


def step_scan(checks: dict, scan_roots: list[str] | None) -> None:
    console.print(Rule(f"[bold]{t('step_scan')}[/bold]", style="bright_black"))
    console.print()
    uv = checks.get("uv", "uv")
    _ensure_uv_cache_env()
    cmd = [uv, "run", "--no-dev", "--project", str(INSTALL_DIR), "cchwc", "scan"]
    if scan_roots is None:
        cmd += ["--global"]
    else:
        for r in scan_roots:
            cmd += ["--cwd", r]

    with Status(f"  {t('scanning')}", spinner="dots"):
        result = _run(cmd, cwd=str(INSTALL_DIR))

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

def _save_scope(scan_roots: list[str] | None) -> None:
    from cchwc.config import save_scan_scope

    if scan_roots is None:
        save_scan_scope("global", [])
    else:
        save_scan_scope("project", scan_roots)


def _scope_from_options(scope: str, roots: list[str] | None) -> list[str] | None:
    normalized = scope.lower()
    if normalized == "global":
        return None
    if normalized == "current":
        return [str(Path.cwd())]
    if normalized in {"custom", "project"}:
        if roots:
            return [str(Path(path).expanduser().resolve()) for path in roots]
        return [str(Path.cwd())]
    raise ValueError(f"Unsupported setup scope: {scope}")


def run_wizard(
    skip_deps: bool = False,
    *,
    non_interactive: bool = False,
    lang: str = "en",
    scope: str = "global",
    roots: list[str] | None = None,
    install_agent_clis: bool = False,
    autostart: bool = False,
    slash: bool = True,
    mcp: bool = True,
    scan: bool = True,
) -> None:
    try:
        if non_interactive:
            set_lang(lang)
        else:
            step_language()
        step_welcome()
        checks = step_prereqs()
        step_install_uv(checks)
        if not skip_deps:
            step_sync_deps(checks)
        if non_interactive:
            if install_agent_clis:
                step_claude_cli(checks, interactive=False, install_missing=True)
                step_codex_cli(checks, interactive=False, install_missing=True)
            else:
                _info(t("agent_cli_skip"))
            scan_roots = _scope_from_options(scope, roots)
        else:
            step_claude_cli(checks)
            step_codex_cli(checks)
            scan_roots = step_scope()
        _save_scope(scan_roots)
        if non_interactive:
            autostart_ok = install_autostart_noninteractive(checks) if autostart else False
            integrations = install_integrations_noninteractive(slash=slash, mcp=mcp)
        else:
            autostart_ok = step_autostart(checks)
            integrations = step_integrations()
        if scan:
            step_scan(checks, scan_roots)
        step_done(autostart_ok, integrations)
    except KeyboardInterrupt:
        console.print("\n\n  [dim]Setup cancelled.[/dim]\n")
        sys.exit(0)


def install_autostart_noninteractive(checks: dict) -> bool:
    from cchwc.server_runner import install_autostart

    uv = checks.get("uv") or _which("uv") or "uv"
    ok = install_autostart(uv_path=uv, install_dir=INSTALL_DIR)
    if ok:
        _ok(t("autostart_ok"))
    else:
        _fail(t("autostart_failed"))
    return ok


def install_integrations_noninteractive(*, slash: bool, mcp: bool) -> dict:
    if slash or mcp:
        try:
            _install_integrations(mcp)
            _ok(t("integration_ok"))
        except Exception as e:
            _fail(str(e))
    return {"slash": slash, "mcp": mcp}
