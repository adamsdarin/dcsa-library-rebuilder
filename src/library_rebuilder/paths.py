"""Path bounding for recipe-relative inputs."""
from __future__ import annotations

from pathlib import Path


def inside(root: Path, relative: str) -> Path:
    """Resolve a recipe-relative path and refuse anything that escapes root."""
    value = str(relative).replace("\\", "/")
    if not value or value.startswith("/") or ":" in value or ".." in value.split("/"):
        raise ValueError(f"Path must be relative and inside {root}: {relative}")
    path = (Path(root) / value).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f"Resolved path escapes {root}: {relative}")
    return path
