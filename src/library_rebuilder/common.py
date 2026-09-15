"""Small shared helpers; standard library only."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path: Path, value) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    with Path(path).open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def inside(root: Path, relative: str) -> Path:
    """Resolve a recipe-relative path and refuse anything that escapes root."""
    value = str(relative).replace("\\", "/")
    if not value or value.startswith("/") or ":" in value or ".." in value.split("/"):
        raise ValueError(f"Path must be relative and inside {root}: {relative}")
    path = (Path(root) / value).resolve()
    if not path.is_relative_to(Path(root).resolve()):
        raise ValueError(f"Resolved path escapes {root}: {relative}")
    return path
