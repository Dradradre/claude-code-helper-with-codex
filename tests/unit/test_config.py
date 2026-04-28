from pathlib import Path

from cchwc.config import Settings, save_scan_scope


def test_settings_loads_user_config(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    config_path.write_text(
        """
[scan]
mode = "project"
roots = ["C:/work/app"]

[server]
host = "127.0.0.2"
port = 8787
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))

    settings = Settings()

    assert settings.scan_mode == "project"
    assert settings.scan_roots == ["C:/work/app"]
    assert settings.host == "127.0.0.2"
    assert settings.port == 8787


def test_env_overrides_user_config(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    config_path.write_text(
        """
[scan]
mode = "project"
roots = ["C:/work/app"]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))
    monkeypatch.setenv("CCHWC_SCAN_MODE", "global")

    settings = Settings()

    assert settings.scan_mode == "global"
    assert settings.scan_roots == ["C:/work/app"]


def test_save_scan_scope_round_trips(local_tmp_path, monkeypatch):
    config_path = local_tmp_path / "config.toml"
    monkeypatch.setenv("CCHWC_CONFIG_FILE", str(config_path))

    save_scan_scope("project", [str(Path("C:/work/app"))])

    settings = Settings()
    assert settings.scan_mode == "project"
    assert settings.scan_roots == [str(Path("C:/work/app"))]
