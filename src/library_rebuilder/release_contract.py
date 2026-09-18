"""Portable, read-only consumer preflight for an approved library release.

Maintained by the Custodian; vendored unchanged into the question-bot package.
Only robot metadata and explicitly approved indexes are read.
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import sqlite3
from pathlib import Path, PurePosixPath

STATE = "ROBOT_READABLE_DIRECTORY/STATE/LIBRARY_STATE.json"
POINTER = "ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json"
CATALOG = "ROBOT_READABLE_DIRECTORY/RETRIEVAL/INDEX_CATALOG.json"
QUERY = "ROBOT_READABLE_DIRECTORY/RETRIEVAL/QUERY_POLICY.json"
POLICY = "ROBOT_READABLE_DIRECTORY/RETRIEVAL/ROBOT_ACCESS_POLICY.json"
CONFIG = "ROBOT_READABLE_DIRECTORY/RETRIEVAL/RETRIEVAL_CONFIG.json"
ROUTER = "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_SEARCH_ROUTER.json"


def bounded_path(root: Path, relative: str, prefix: str) -> Path:
    value = str(relative).replace("\\", "/")
    if not value.startswith(prefix) or ".." in PurePosixPath(value).parts:
        raise ValueError(f"Path outside {prefix}: {relative}")
    path = (root / value).resolve()
    if not path.is_relative_to((root / prefix).resolve()):
        raise ValueError(f"Resolved path outside {prefix}: {relative}")
    return path


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def approved_release(root: Path, check_integrity: bool = False, verify_indexes: bool = True) -> dict:
    root = root.resolve()
    entry = read_json(root / "START_HERE_FOR_ROBOTS.json")
    expected = {"current_release": POINTER, "library_state": STATE,
                "index_catalog": CATALOG, "query_policy": QUERY,
                "access_policy": POLICY, "retrieval": CONFIG, "doha_router": ROUTER}
    for key, value in expected.items():
        if entry.get(key) != value:
            raise ValueError(f"Entry point {key} does not resolve to {value}")
    nested = read_json(root / "ROBOT_READABLE_DIRECTORY/START_HERE.json")
    if any(nested.get(key) != value for key, value in expected.items()):
        raise ValueError("Nested robot entry point disagrees with the root entry point")
    pointer, state, catalog, query, policy, config, router = [
        read_json(bounded_path(root, value, "ROBOT_READABLE_DIRECTORY/"))
        for value in (POINTER, STATE, CATALOG, QUERY, POLICY, CONFIG, ROUTER)
    ]
    release_id = pointer.get("release_id")
    if not release_id or any(char in release_id for char in "/\\:") or release_id in {".", ".."}:
        raise ValueError("Invalid published release ID")
    if any(item.get("release_id") != release_id for item in (state, catalog, query)):
        raise ValueError("Published pointer, state, index catalog, and query policy disagree on release ID")
    approval = pointer.get("approval", {})
    if approval.get("release_id") != release_id or not approval.get("approved_by") or not approval.get("approved_utc"):
        raise ValueError("Published release lacks a matching approval receipt")
    if state.get("release_status") != "published" or state.get("production_response_ready") is not True:
        raise ValueError("Library state is not published and ready for production retrieval")
    if state.get("publication_blockers") or state.get("production_integrity_healthy") is not True:
        raise ValueError("Published state has publication or integrity blockers")
    if state.get("approval") != approval or state.get("published_utc") != pointer.get("published_utc"):
        raise ValueError("Published state and pointer disagree on approval or publication time")
    indexes = catalog.get("indexes", [])
    if not indexes or state.get("approved_indexes") != indexes or query.get("indexes") != indexes:
        raise ValueError("Approved index lists disagree or are empty")
    if catalog.get("default_sequence") != [item["production_path"] for item in indexes if item.get("default_allowed")]:
        raise ValueError("Default retrieval sequence disagrees with the catalog")
    access = policy.get("content_access", {})
    if access.get("approved_indexes_mode") != "resolve_from_index_catalog" or config.get("default_index_mode") != "resolve_from_index_catalog":
        raise ValueError("Retrieval policy does not resolve release-scoped indexes")
    for key, value in {"index_catalog": CATALOG, "query_policy": QUERY, "current_release_pointer": POINTER,
                       "access_policy": POLICY, "library_state": STATE, "entry_point": "START_HERE_FOR_ROBOTS.json"}.items():
        if config.get(key) != value:
            raise ValueError(f"Retrieval configuration disagrees on {key}")
    if query.get("fail_closed") is not True or query.get("content_source") != "robot_only":
        raise ValueError("Query policy does not enforce robot-only, fail-closed access")
    agents = (root / "AGENTS.md").read_text(encoding="utf-8-sig")
    if "General retrieval uses `LOCAL_INDEXES/DCSA_GENERAL_FTS.sqlite`" in agents:
        raise ValueError("Library AGENTS.md still mandates the retired general index")
    if entry.get("local_indexes") or config.get("default_index"):
        raise ValueError("Legacy static index routing conflicts with release-scoped routing")
    forbidden = set(access.get("retrieval_forbidden_indexes", []))
    paths = []
    for item in indexes:
        relative = item.get("production_path", "")
        if relative in forbidden or relative in paths:
            raise ValueError(f"Forbidden or duplicate index: {relative}")
        bounded_path(root, relative, f"LOCAL_INDEXES/CUSTODIAN/{release_id}/")
        paths.append(relative)
    if not any(item.get("default_allowed") and "contractor_or_fso_obligation" in item.get("allowed_intents", []) and item.get("chunks", 0) > 0 for item in indexes):
        raise ValueError("No approved controlling authority index is available")
    doha_paths = access.get("doha_approved_indexes", [])
    if not doha_paths or entry.get("doha_local_indexes") != doha_paths:
        raise ValueError("DOHA approved index lists disagree")
    if router.get("doha_content_index") != config.get("doha_index") or router.get("current_doha_path_index") != config.get("doha_current_paths_index"):
        raise ValueError("DOHA router and retrieval configuration disagree")
    for relative in doha_paths:
        if relative in forbidden:
            raise ValueError(f"Forbidden DOHA index: {relative}")
        bounded_path(root, relative, "LOCAL_INDEXES/")
    doha_hashes = access.get('doha_index_sha256')
    if doha_hashes is not None and (not isinstance(doha_hashes, dict) or set(doha_hashes) != set(doha_paths)):
        raise ValueError('DOHA approved index hashes are incomplete')
    for relative, expected_hash in pointer.get("metadata_sha256", {}).items():
        if digest(bounded_path(root, relative, "ROBOT_READABLE_DIRECTORY/")) != expected_hash:
            raise ValueError(f"Published metadata hash mismatch: {relative}")
    checks = []
    for relative in paths + doha_paths if verify_indexes else []:
        path = bounded_path(root, relative, "LOCAL_INDEXES/")
        if not path.is_file():
            raise ValueError(f"Approved index missing: {relative}")
        item = next((item for item in indexes if item["production_path"] == relative), None)
        with contextlib.closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            table = "corpus" if "corpus" in tables else "current_paths" if "current_paths" in tables else None
            if table is None:
                raise ValueError(f"Approved index has no retrieval table: {relative}")
            count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            if item:
                if count != item.get("chunks"):
                    raise ValueError(f"Approved chunk count mismatch: {relative}")
                if item.get("default_allowed") and conn.execute("SELECT count(*) FROM corpus WHERE answer_eligibility != 'answer_eligible'").fetchone()[0]:
                    raise ValueError(f"Ineligible content in a default index: {relative}")
                if "contractor_or_fso_obligation" in item.get("allowed_intents", []) and conn.execute("SELECT count(*) FROM corpus WHERE authority_role NOT IN ('controlling_regulation','contract_clause')").fetchone()[0]:
                    raise ValueError(f"Noncontrolling content in the obligation index: {relative}")
            if check_integrity and conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError(f"Approved index integrity failure: {relative}")
        if check_integrity and item and item.get("sha256") and digest(path) != item["sha256"]:
            raise ValueError(f"Approved index hash mismatch: {relative}")
        if check_integrity and doha_hashes is not None and relative in doha_hashes and digest(path) != doha_hashes[relative]:
            raise ValueError(f"Approved DOHA index hash mismatch: {relative}")
        checks.append({"path": relative, "records": count, "integrity": "ok" if check_integrity else "not_requested"})
    return {"release_id": release_id, "indexes": indexes, "index_checks": checks,
            "state": state, "query_policy": query, "approval": approval}


def readiness(root: Path, check_integrity: bool = False) -> dict:
    """Same fail-closed readiness vocabulary for every consumer."""
    result = {"ready": False, "release_id": None, "errors": [],
              "capabilities": {"approved_retrieval": False, "doha_search": False}}
    try:
        release = approved_release(root, check_integrity=check_integrity)
        result.update(ready=True, release_id=release["release_id"])
        result["capabilities"]["approved_retrieval"] = True
        result["capabilities"]["doha_search"] = any(
            "DOHA_CASE_TOPICS" in item["path"] and item["records"] > 0
            for item in release["index_checks"]
        )
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error) as exc:
        result["errors"].append(str(exc))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Check approved library readiness without modifying the library")
    parser.add_argument("--library-root", type=Path, required=True)
    parser.add_argument("--check-integrity", action="store_true")
    args = parser.parse_args()
    result = readiness(args.library_root, args.check_integrity)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["ready"] else 1)
