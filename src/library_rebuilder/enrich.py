from __future__ import annotations

import collections
import contextlib
import sqlite3
from pathlib import Path
from typing import Any

from .authority import ROLE_PRIORITY, classify_authority, lifecycle_eligibility, parse_authority_header
from .common import iter_jsonl, norm, normalize_domain, sha256_file, sha256_text


def _doha_metadata(root: Path) -> dict[str, dict[str, Any]]:
    path = root / "LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite"
    if not path.is_file():
        return {}
    output: dict[str, dict[str, Any]] = {}
    with contextlib.closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        for row in conn.execute("SELECT document_id,answer_eligible,content_sha256,case_id,decision_level,outcome,guideline_codes,current_group FROM decisions"):
            output[row[0]] = {
                "answer_eligible": bool(row[1]), "content_sha256": row[2], "case_id": row[3],
                "decision_level": row[4], "outcome": row[5], "guideline_codes": row[6], "current_group": row[7],
            }
    return output


def _canonical_sort(item: dict[str, Any]) -> tuple[Any, ...]:
    return (
        item["authority_priority"],
        item["answer_eligibility"] != "answer_eligible",
        "LEGACY" in item["robot_text_path"].upper(),
        not bool(item.get("rename_history")),
        len(item["robot_text_path"]),
        item["robot_text_path"].casefold(),
    )


def enrich_manifest(root: Path, manifest_path: Path, human_hashes: dict[str, str] | None = None) -> list[dict[str, Any]]:
    human_hashes = human_hashes or {}
    doha = _doha_metadata(root)
    enriched: list[dict[str, Any]] = []
    original_id_counts: collections.Counter[str] = collections.Counter()

    for ordinal, (_, source) in enumerate(iter_jsonl(manifest_path), 1):
        record = dict(source)
        original_id = str(record["document_id"])
        original_id_counts[original_id] += 1
        robot_rel = norm(record["robot_text_path"])
        robot_path = root / robot_rel
        doha_item = doha.get(original_id)
        digest = doha_item["content_sha256"] if doha_item else sha256_file(robot_path)
        header = {} if record.get("collection_id") == "doha_decisions" else parse_authority_header(robot_path.read_text(encoding="utf-8", errors="replace"))
        role, contractor_binding = classify_authority(record, header)
        eligibility, eligibility_basis = lifecycle_eligibility(record, doha_item["answer_eligible"] if doha_item else None)
        proposed_id = original_id
        if original_id_counts[original_id] > 1:
            proposed_id = f"{original_id}-duplicate-{sha256_text(robot_rel)[:8]}"
        record.update({
            "document_id": proposed_id,
            "source_document_id": original_id,
            # Folded here rather than in the source manifest: the raw value stays intact for
            # provenance, and every derived artifact (chunks, index `domain` column, the
            # knowledge graph) sees one spelling instead of two.
            "domain": normalize_domain(record.get("domain")),
            "source_domain": record.get("domain"),
            "source_manifest_ordinal": ordinal,
            "robot_content_sha256": digest,
            "human_artifact_sha256": human_hashes.get(original_id),
            "authority_role": role,
            "authority_priority": ROLE_PRIORITY[role],
            "contractor_binding": contractor_binding,
            "answer_eligibility": eligibility,
            "answer_eligibility_basis": eligibility_basis,
            "effective_date": header.get("effective_date"),
            "header_status": header.get("header_status"),
            "header_authority_tier": header.get("header_tier"),
            "authority_tier_conflict": header.get("header_tier") is not None and int(record["authority_tier"]) != int(header["header_tier"]),
            "metadata_basis": header.get("metadata_basis"),
            "stable_locator_strategy": "form_feed_page_then_paragraph_block",
            "extraction_provenance": "existing_robot_representation",
            "duplicate_of": None,
            "canonical_document_id": proposed_id,
        })
        if doha_item:
            record["doha_case_metadata"] = {key: value for key, value in doha_item.items() if key not in {"content_sha256", "answer_eligible"}}
        enriched.append(record)

    # Group by the real source artifact's hash when we have one (human_artifact_sha256, from
    # audit_library's deep pass over the actual human file bytes), not robot_content_sha256.
    # robot_content_sha256 is itself sourced from two different places depending on the record
    # (a DOHA SQLite side-table's content_sha256 when present, otherwise a hash of the extracted
    # robot text) -- two byte-identical source PDFs can end up on opposite sides of that split
    # and never collide there even though they're the same document. human_artifact_sha256 is
    # always computed the same way (sha256 of the actual file), so it doesn't have that split.
    groups: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in enriched:
        dedup_digest = record["human_artifact_sha256"] or record["robot_content_sha256"]
        groups[dedup_digest].append(record)
    for group in groups.values():
        if len(group) < 2:
            continue
        group.sort(key=_canonical_sort)
        canonical = group[0]
        canonical["canonical_document_id"] = canonical["document_id"]
        for duplicate in group[1:]:
            duplicate["duplicate_of"] = canonical["document_id"]
            duplicate["canonical_document_id"] = canonical["document_id"]
            duplicate["answer_eligibility"] = "excluded_duplicate"
            duplicate["answer_eligibility_basis"] = (
                "identical_human_artifact_sha256" if duplicate["human_artifact_sha256"] else "identical_robot_content_sha256"
            )
    return enriched
