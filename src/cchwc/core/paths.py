import platform
import re
from pathlib import Path


def decode_claude_project_dir(dirname: str) -> str | None:
    if not dirname:
        return None
    decoded = re.sub(r"^-", "/", dirname)
    decoded = decoded.replace("-", "/")
    if platform.system() == "Windows" and len(decoded) > 2 and decoded[2] == "/":
        decoded = decoded[0] + ":" + decoded[2:]
    return decoded


def get_claude_root() -> Path:
    return Path.home() / ".claude" / "projects"


def get_codex_root() -> Path:
    return Path.home() / ".codex" / "sessions"
