import json
from pathlib import Path

from typer.testing import CliRunner

from cchwc.cli import INSTALL_DIR, app
from cchwc.config import Settings


def test_install_commands_registers_project_root_mcp(local_tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: local_tmp_path))
    runner = CliRunner()

    result = runner.invoke(app, ["install-commands"])

    assert result.exit_code == 0, result.output
    mcp = json.loads((local_tmp_path / ".claude" / "mcp.json").read_text(encoding="utf-8"))
    cchwc = mcp["mcpServers"]["cchwc"]
    assert cchwc["args"][:4] == ["run", "--no-dev", "--project", str(INSTALL_DIR)]
    assert not cchwc["args"][3].endswith(".venv")
    assert cchwc["env"]["UV_CACHE_DIR"] == str(INSTALL_DIR / ".uv-cache")


def test_config_add_project_persists_project_mode(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    project_path = local_tmp_path / "project"
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))
    runner = CliRunner()

    result = runner.invoke(app, ["config", "add-project", str(project_path)])

    assert result.exit_code == 0, result.output
    settings = Settings()
    assert settings.scan_mode == "project"
    assert settings.scan_roots == [str(project_path.resolve())]


def test_setup_yes_persists_scope_without_prompting(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "setup",
            "--yes",
            "--skip-deps",
            "--scope",
            "current",
            "--no-agent-clis",
            "--no-autostart",
            "--no-slash",
            "--no-mcp",
            "--no-scan",
        ],
    )

    assert result.exit_code == 0, result.output
    settings = Settings()
    assert settings.scan_mode == "project"
    assert settings.scan_roots == [str(Path.cwd())]
