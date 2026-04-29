import platform
from pathlib import Path

from fastapi import APIRouter, Query

router = APIRouter()

_SKIP_NAMES = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
               ".mypy_cache", ".ruff_cache", ".next", ".nuxt", "coverage"}


def _posix(path: Path) -> str:
    return str(path).replace("\\", "/")


def _safe_listdir(path: Path, show_hidden: bool = False) -> list:
    entries = []
    try:
        for child in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            if not show_hidden and child.name.startswith("."):
                continue
            entries.append({"name": child.name, "is_dir": child.is_dir(), "path": _posix(child)})
    except PermissionError:
        pass
    return entries


@router.get("/browse")
async def browse(path: str = Query(default="~"), show_hidden: bool = Query(default=False)):
    p = Path(path).expanduser().resolve()
    if not p.exists():
        p = Path.home()
    if not p.is_dir():
        p = p.parent if p.parent.exists() else Path.home()

    drives: list[str] = []
    if platform.system() == "Windows":
        import string
        drives = [f"{d}:/" for d in string.ascii_uppercase if Path(f"{d}:/").exists()]

    parent = _posix(p.parent) if p != p.parent else None
    return {
        "path": _posix(p),
        "parent": parent,
        "entries": _safe_listdir(p, show_hidden),
        "drives": drives,
        "home": _posix(Path.home()),
    }


@router.get("/tree")
async def tree(path: str = Query(default="."), max_depth: int = Query(default=3)):
    p = Path(path).expanduser().resolve()
    if not p.exists() or not p.is_dir():
        return {"path": _posix(p), "tree": []}

    def _build(dir_path: Path, depth: int) -> list:
        if depth <= 0:
            return []
        result = []
        try:
            for child in sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                if child.name.startswith(".") or child.name in _SKIP_NAMES:
                    continue
                node = {"name": child.name, "path": _posix(child), "is_dir": child.is_dir()}
                if child.is_dir():
                    node["children"] = _build(child, depth - 1)
                result.append(node)
        except PermissionError:
            pass
        return result

    return {"path": _posix(p), "tree": _build(p, max_depth)}
