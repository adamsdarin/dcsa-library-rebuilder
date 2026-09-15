"""Assemble a hash-bound regeneration recipe and refuse what the engine would refuse."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

from .common import inside, read_json, sha256_file, write_json

RELEASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
REVIEW_FIELDS = ("reviewed_by", "reviewed_utc", "identity", "provenance", "extraction", "parity", "taxonomy", "lifecycle")
RECORD_FIELDS = ("document_id", "collection_id", "domain", "authority_tier", "current_status",
                 "human_source_path", "robot_text_path")


def check_evaluations(path: Path) -> None:
    cases = read_json(path).get("cases", [])
    if not any(case.get("require_hit") is True and case.get("require_locator") is True
               and case.get("expected_document_ids") for case in cases):
        raise ValueError("Evaluations need a positive document-and-locator retrieval case")


def check_intake(plan_path: Path) -> list[str]:
    plan = read_json(plan_path)
    items = plan.get("items", [])
    if plan.get("schema_version") != "1.0" or not items:
        raise ValueError("Intake plan needs schema_version 1.0 and at least one item")
    base = plan_path.parent
    ids = []
    for item in items:
        record, review = item.get("record", {}), item.get("review", {})
        document_id = record.get("document_id")
        if not isinstance(document_id, str) or not document_id.strip():
            raise ValueError("Every intake item needs a document_id")
        if record.get("collection_id") == "doha_decisions":
            raise ValueError(f"DOHA reconstruction is unsupported: {document_id}")
        # Mirrors dcsa_custodian.intake.stage_intake so failures surface before a build.
        missing = [k for k in REVIEW_FIELDS if not str(review.get(k, "")).strip()]
        if missing:
            raise ValueError(f"{document_id} lacks review evidence: {', '.join(missing)}")
        missing = [k for k in RECORD_FIELDS if record.get(k) in (None, "")]
        if missing:
            raise ValueError(f"{document_id} lacks reviewed record fields: {', '.join(missing)}")
        package_path = inside(base, item.get("package", ""))
        package = read_json(package_path)
        if package.get("approval_state") != "quarantined_unreviewed":
            raise ValueError(f"{document_id} package is not a quarantined, unreviewed acquisition")
        if any(urlparse(package.get(k, "")).scheme != "https" for k in ("requested_source_uri", "resolved_source_uri")):
            raise ValueError(f"{document_id} package lacks HTTPS requested/resolved provenance")
        if not package.get("retrieved_at") or not package.get("mime_type"):
            raise ValueError(f"{document_id} package lacks retrieval provenance")
        source = inside(package_path.parent, package.get("source_filename", ""))
        robot = inside(base, item.get("robot_file", ""))
        if sha256_file(source) != package.get("source_sha256") or source.stat().st_size != package.get("source_bytes"):
            raise ValueError(f"{document_id} source bytes do not match the intake package hash or size")
        if sha256_file(robot) != item.get("robot_sha256") or not robot.read_text(encoding="utf-8").strip():
            raise ValueError(f"{document_id} extraction does not match robot_sha256 or is empty")
        ids.append(document_id)
    if len(set(ids)) != len(ids):
        raise ValueError("Intake plan repeats a document_id")
    return ids


def build_recipe(directory: Path, release_id: str, scope: str,
                 intake_plan: str = "intake_plan.json", evaluations: str = "golden_queries.json") -> Path:
    directory = Path(directory).resolve()
    if not RELEASE_ID.fullmatch(release_id or ""):
        raise ValueError("Invalid release ID")
    if not scope or not scope.strip():
        raise ValueError("A reviewed scope statement is required")
    plan_path, eval_path = inside(directory, intake_plan), inside(directory, evaluations)
    check_evaluations(eval_path)
    ids = check_intake(plan_path)
    recipe = {
        "schema_version": "1.0",
        "release_id": release_id,
        "scope": scope.strip(),
        "required_document_ids": sorted(ids),
        "intake_plan": {"path": intake_plan, "sha256": sha256_file(plan_path)},
        "evaluations": {"path": evaluations, "sha256": sha256_file(eval_path)},
    }
    out = directory / "recipe.json"
    write_json(out, recipe)
    return out
