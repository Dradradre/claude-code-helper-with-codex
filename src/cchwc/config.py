import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, InitSettingsSource, PydanticBaseSettingsSource

CONFIG_ENV_VAR = "CCHWC_CONFIG_FILE"

_FLAT_CONFIG_KEYS = {
    "db_path",
    "claude_root",
    "codex_root",
    "scan_mode",
    "scan_roots",
    "host",
    "port",
    "watch_debounce_ms",
    "scan_concurrency",
    "default_max_rounds",
    "default_max_cost_usd",
    "default_max_tokens",
    "claude_bin",
    "codex_bin",
    "log_level",
    "log_file",
}

_SECTION_CONFIG_KEYS = {
    "paths": {
        "db_path": "db_path",
        "claude_root": "claude_root",
        "codex_root": "codex_root",
        "log_file": "log_file",
    },
    "scan": {
        "mode": "scan_mode",
        "roots": "scan_roots",
        "concurrency": "scan_concurrency",
    },
    "server": {
        "host": "host",
        "port": "port",
    },
    "watch": {
        "debounce_ms": "watch_debounce_ms",
    },
    "orchestrator": {
        "default_max_rounds": "default_max_rounds",
        "default_max_cost_usd": "default_max_cost_usd",
        "default_max_tokens": "default_max_tokens",
    },
    "agents": {
        "claude_bin": "claude_bin",
        "codex_bin": "codex_bin",
    },
    "logging": {
        "level": "log_level",
        "file": "log_file",
    },
}


def get_config_path() -> Path:
    """Return the user config path, overridable for tests/sandboxes."""
    override = os.environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override).expanduser()
    return Path.home() / ".cchwc" / "config.toml"


def read_user_config() -> dict[str, Any]:
    path = get_config_path()
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return data if isinstance(data, dict) else {}


def write_user_config(data: dict[str, Any]) -> Path:
    import tomli_w  # type: ignore[import]

    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        tomli_w.dump(data, f)
    return path


def save_scan_scope(mode: str, roots: list[str] | None = None) -> Path:
    data = read_user_config()
    scan = data.setdefault("scan", {})
    scan["mode"] = mode
    if roots is not None:
        scan["roots"] = roots
    elif mode == "global":
        scan["roots"] = []
    return write_user_config(data)


def _settings_from_config_file() -> dict[str, Any]:
    data = read_user_config()
    settings: dict[str, Any] = {}

    for key in _FLAT_CONFIG_KEYS:
        if key in data:
            settings[key] = data[key]

    for section_name, mapping in _SECTION_CONFIG_KEYS.items():
        section = data.get(section_name)
        if not isinstance(section, dict):
            continue
        for source_key, target_key in mapping.items():
            if source_key in section:
                settings[target_key] = section[source_key]

    return settings


class CchwcConfigSettingsSource(InitSettingsSource):
    def __init__(self, settings_cls: type[BaseSettings]):
        super().__init__(settings_cls, _settings_from_config_file())


class Settings(BaseSettings):
    db_path: Path = Field(default_factory=lambda: Path.home() / ".cchwc" / "cchwc.db")
    claude_root: Path = Field(default_factory=lambda: Path.home() / ".claude" / "projects")
    codex_root: Path = Field(default_factory=lambda: Path.home() / ".codex" / "sessions")

    # scan scope: "global" = 전체, "project" = scan_roots에 지정된 경로만
    scan_mode: str = "global"
    scan_roots: list[str] = Field(default_factory=list)

    host: str = "127.0.0.1"
    port: int = 7878

    watch_debounce_ms: int = 100
    scan_concurrency: int = 8

    default_max_rounds: int = 3
    default_max_cost_usd: float = 5.0
    default_max_tokens: int = 100_000

    claude_bin: str = "claude"
    codex_bin: str = "codex"

    log_level: str = "INFO"
    log_file: Path | None = None

    model_config = {"env_prefix": "CCHWC_", "env_file": ".env"}

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            CchwcConfigSettingsSource(settings_cls),
            file_secret_settings,
        )
