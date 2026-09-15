"""Run standalone builds safely; never write into a protected library. No Archivist or Librarian."""
from __future__ import annotations

import contextlib
import os
from pathlib import Path
import shutil
import sqlite3

from .build import MARKER, BuildRefused, build
from .common import read_json, sha256_file, utc_now, write_json
from .notice import MAINTENANCE_MODE, NOTICE
from .release_contract import STATE, approved_release


def load_config(path: Path, base: Path) -> dict:
    """Relative paths resolve against base (the repository root), never the caller's cwd."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing {path}; copy config/rebuilder.example.json and set explicit paths")
    config = read_json(path)
    protected = config.get("protected_libraries", [])
    if not protected or any("<" in str(p) for p in protected):
        raise ValueError("Config needs at least one real protected_libraries entry (the canonical library)")
    config["protected_libraries"] = [str((Path(base) / p).resolve()) for p in protected]
    return config


def protected_overlap(config: dict, target: Path) -> list[str]:
    target = Path(target).resolve()
    return [f"Path overlaps protected library: {protected}" for protected in map(Path, config["protected_libraries"])
            if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target)]


def _fts5_available() -> bool:
    try:
        with contextlib.closing(sqlite3.connect(":memory:")) as conn:
            conn.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
        return True
    except sqlite3.OperationalError:
        return False


def preflight(config: dict, destination: Path) -> dict:
    destination = Path(destination).resolve()
    errors, notes = [], []
    if not _fts5_available():
        errors.append("This Python's SQLite lacks FTS5; retrieval indexes cannot be built")
    errors.extend(protected_overlap(config, destination))
    if destination.exists():
        if not destination.is_dir():
            errors.append("Destination exists and is not a directory")
        elif (destination / MARKER).is_file():
            notes.append("Destination holds an earlier rebuild; only the identical recipe is accepted (verified, not rebuilt)")
        elif any(destination.iterdir()):
            errors.append("Destination is not empty; existing libraries are never replaced")
    lock = destination.parent / f".{destination.name}.rebuild.lock"
    if lock.exists():
        pid = lock.read_text(encoding="utf-8", errors="replace").strip()
        errors.append(f"Writer lock held by PID {pid or '?'}: inspect that process before any recovery; do not delete blindly")
    probe_dir = next((p for p in [destination, *destination.parents] if p.exists()), None)
    if probe_dir is not None:
        notes.append(f"Free space at {probe_dir}: {shutil.disk_usage(probe_dir).free // 2**30} GiB")
    return {"ok": not errors, "destination": str(destination), "errors": errors, "notes": notes}


def run(config: dict, recipe: Path, destination: Path, ledger_dir: Path) -> dict:
    recipe, destination = Path(recipe).resolve(), Path(destination).resolve()
    check = preflight(config, destination)
    entry = {"started_utc": utc_now(), "recipe": str(recipe), "recipe_sha256": sha256_file(recipe),
             "release_id": read_json(recipe).get("release_id"), "destination": str(destination),
             "preflight": check, "status": "preflight_failed", "maintenance_mode": MAINTENANCE_MODE}
    if check["ok"]:
        try:
            entry["result"] = build(recipe, destination)
            entry["status"] = entry["result"]["status"]
        except BuildRefused as exc:
            entry.update(status="refused", error=str(exc))
        except (OSError, ValueError, sqlite3.Error) as exc:
            entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    entry["finished_utc"] = utc_now()
    entry["ok"] = entry["status"] in ("published", "already_published")
    stamp = entry["started_utc"].replace(":", "").replace("-", "").replace("+", "")
    write_json(Path(ledger_dir) / f"{stamp}-{entry['release_id']}-{os.getpid()}.json", entry)
    return entry


def verify(destination: Path, release_id: str | None = None) -> dict:
    destination = Path(destination).resolve()
    result = {"ok": False, "destination": str(destination), "errors": []}
    try:
        release = approved_release(destination, check_integrity=True)
        result["release_id"] = release["release_id"]
        result["index_checks"] = release["index_checks"]
        if release_id and release["release_id"] != release_id:
            result["errors"].append(f"Published release {release['release_id']} is not {release_id}")
        if not (destination / MARKER).is_file():
            result["errors"].append("Destination has no rebuild marker; it was not built by this agent")
        state = read_json(destination / STATE)
        result["maintenance_mode"] = state.get("maintenance_mode", "unknown")
        result["built_utc"] = state.get("published_utc")
        if result["maintenance_mode"] == MAINTENANCE_MODE:
            result["warning"] = NOTICE
    except Exception as exc:  # fail closed on any readiness error
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    result["ok"] = not result["errors"]
    return result
