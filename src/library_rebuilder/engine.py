"""Drive the Archivist regeneration engine safely; never write into a protected library."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .common import read_json, sha256_file, utc_now, write_json
from .release_contract import approved_release

MARKER = ".custodian/regenerator/recipe.json"


def load_config(path: Path, base: Path) -> dict:
    """Relative paths resolve against base (the repository root), never the caller's cwd."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Missing {path}; copy config/rebuilder.example.json and set explicit paths")
    config = read_json(path)
    if not config.get("archivist_root"):
        raise ValueError("Config needs archivist_root")
    config["archivist_root"] = str((Path(base) / config["archivist_root"]).resolve())
    protected = config.get("protected_libraries", [])
    if not protected or any("<" in str(p) for p in protected):
        raise ValueError("Config needs at least one real protected_libraries entry (the canonical library)")
    config["protected_libraries"] = [str((Path(base) / p).resolve()) for p in protected]
    return config


def protected_overlap(config: dict, target: Path) -> list[str]:
    target = Path(target).resolve()
    return [f"Path overlaps protected library: {protected}" for protected in map(Path, config["protected_libraries"])
            if target == protected or target.is_relative_to(protected) or protected.is_relative_to(target)]


def _engine(config: dict) -> Path:
    return Path(config["archivist_root"]).resolve() / "custodian.py"


def preflight(config: dict, destination: Path) -> dict:
    destination = Path(destination).resolve()
    errors, notes = [], []
    engine = _engine(config)
    if not engine.is_file():
        errors.append(f"Archivist engine not found: {engine}")
    else:
        probe = subprocess.run([sys.executable, str(engine), "regenerate", "--help"],
                               cwd=engine.parent, capture_output=True, text=True)
        if probe.returncode != 0:
            errors.append("Archivist checkout has no working 'regenerate' command")
    errors.extend(protected_overlap(config, destination))
    if destination.exists():
        if not destination.is_dir():
            errors.append("Destination exists and is not a directory")
        elif (destination / MARKER).is_file():
            notes.append("Destination belongs to an earlier regeneration attempt; the engine will require the same recipe")
        elif any(destination.iterdir()):
            errors.append("Destination is not empty; existing libraries are never replaced")
    lock = destination.parent / f".{destination.name}.regeneration.lock"
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
             "preflight": check, "exit_code": None}
    if check["ok"]:
        proc = subprocess.run([sys.executable, str(_engine(config)), "regenerate",
                               "--recipe", str(recipe), "--destination", str(destination)],
                              cwd=_engine(config).parent, capture_output=True, text=True)
        entry["exit_code"] = proc.returncode
        try:
            entry["result"] = json.loads(proc.stdout) if proc.stdout.strip() else None
        except json.JSONDecodeError:
            entry["result"] = None
            entry["stdout_tail"] = proc.stdout[-4000:]
        if proc.returncode:
            entry["stderr_tail"] = proc.stderr[-4000:]
    entry["finished_utc"] = utc_now()
    entry["ok"] = entry["exit_code"] == 0
    stamp = entry["started_utc"].replace(":", "").replace("-", "")
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
            result["errors"].append("Destination has no regeneration marker; it was not built by a recipe")
    except Exception as exc:  # fail closed on any readiness error
        result["errors"].append(f"{type(exc).__name__}: {exc}")
    result["ok"] = not result["errors"]
    return result
