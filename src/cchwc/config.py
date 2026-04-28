from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: Path = Path.home() / ".cchwc" / "cchwc.db"
    claude_root: Path = Path.home() / ".claude" / "projects"
    codex_root: Path = Path.home() / ".codex" / "sessions"

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
