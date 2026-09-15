from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any


INDEX_RULES = {
    "DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite": {
        "purpose": "Current regulations and contract clauses eligible to lead contractor-obligation answers",
        "eligibility": {"answer_eligible"},
        "roles": {"controlling_regulation", "contract_clause"},
        "default_allowed": True,
        "allowed_intents": {"contractor_or_fso_obligation", "cui", "general_current"},
        "retrieval_stage": 1,
    },
    "DCSA_GOVERNMENT_ISSUANCE_CHUNKS_FTS.sqlite": {
        "purpose": "Current Government and agency issuances; not a substitute for contractor-controlling authority",
        "eligibility": {"answer_eligible"},
        "roles": {"executive_order", "binding_government_issuance"},
        "default_allowed": True,
        "allowed_intents": {"government_or_gca_procedure", "government_personnel_vetting", "general_current"},
        "retrieval_stage": 1,
    },
    "DCSA_CURRENT_GUIDANCE_CHUNKS_FTS.sqlite": {
        "purpose": "Current interpretive and operational guidance after authority retrieval",
        "eligibility": {"answer_eligible"},
        "roles": {"dcsa_interpretation", "official_operational_guidance", "incorporated_framework"},
        "default_allowed": True,
        "allowed_intents": {"government_or_gca_procedure", "government_personnel_vetting", "system_or_workflow_how_to", "general_current"},
        "retrieval_stage": 2,
    },
    "DCSA_CONTEXT_CHUNKS_FTS.sqlite": {
        "purpose": "Training and context that cannot independently support requirements",
        "eligibility": {"answer_eligible"},
        "roles": {"training_or_context"},
        "default_allowed": False,
        "allowed_intents": {"training_or_context"},
        "retrieval_stage": 3,
    },
    "DCSA_UNRESOLVED_RESEARCH_CHUNKS_FTS.sqlite": {
        "purpose": "Currency or metadata unresolved; excluded from controlling conclusions",
        "eligibility": {"unresolved_currency", "excluded_unresolved"},
        "roles": None,
        "default_allowed": False,
        "allowed_intents": {"maintenance_research"},
        "retrieval_stage": 4,
    },
    "DCSA_HISTORICAL_RESEARCH_CHUNKS_FTS.sqlite": {
        "purpose": "Historical and superseded research only",
        "eligibility": {"historical_only"},
        "roles": None,
        "default_allowed": False,
        "allowed_intents": {"historical_research"},
        "retrieval_stage": 4,
    },
}


SCHEMA = """
CREATE TABLE documents(
    document_id TEXT PRIMARY KEY,
    canonical_document_id TEXT NOT NULL,
    collection_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    authority_role TEXT NOT NULL,
    authority_priority INTEGER NOT NULL,
    current_status TEXT NOT NULL,
    answer_eligibility TEXT NOT NULL,
    contractor_binding TEXT NOT NULL,
    human_source_path TEXT NOT NULL,
    robot_text_path TEXT NOT NULL,
    robot_content_sha256 TEXT NOT NULL
);
CREATE VIRTUAL TABLE corpus USING fts5(
    chunk_id UNINDEXED,
    document_id UNINDEXED,
    canonical_document_id UNINDEXED,
    collection_id UNINDEXED,
    domain UNINDEXED,
    authority_role UNINDEXED,
    authority_priority UNINDEXED,
    current_status UNINDEXED,
    answer_eligibility UNINDEXED,
    contractor_binding UNINDEXED,
    effective_date UNINDEXED,
    locator UNINDEXED,
    human_source_path UNINDEXED,
    robot_text_path UNINDEXED,
    content_sha256 UNINDEXED,
    content,
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE vectors(
    chunk_id TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    dim INTEGER NOT NULL,
    vector BLOB NOT NULL
);
"""


def _matches(chunk: dict[str, Any], rule: dict[str, Any]) -> bool:
    if chunk["answer_eligibility"] not in rule["eligibility"]:
        return False
    return rule["roles"] is None or chunk["authority_role"] in rule["roles"]


def build_indexes(
    output_dir: Path,
    records: list[dict[str, Any]],
    chunks: list[dict[str, Any]],
    vectors: dict[str, bytes] | None = None,
    vector_model: str | None = None,
    vector_dim: int | None = None,
) -> list[dict[str, Any]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    records_by_id = {record["document_id"]: record for record in records}
    catalog: list[dict[str, Any]] = []
    for filename, rule in INDEX_RULES.items():
        output = output_dir / filename
        temp = output.with_suffix(output.suffix + ".building")
        if temp.exists():
            temp.unlink()
        conn = sqlite3.connect(temp)
        conn.executescript(SCHEMA)
        selected = [chunk for chunk in chunks if _matches(chunk, rule)]
        document_ids = sorted({chunk["document_id"] for chunk in selected})
        conn.executemany("INSERT INTO documents VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [
            (
                doc_id, records_by_id[doc_id]["canonical_document_id"], records_by_id[doc_id]["collection_id"],
                records_by_id[doc_id]["domain"], records_by_id[doc_id]["authority_role"],
                records_by_id[doc_id]["authority_priority"], records_by_id[doc_id]["current_status"],
                records_by_id[doc_id]["answer_eligibility"], records_by_id[doc_id]["contractor_binding"],
                records_by_id[doc_id]["human_source_path"], records_by_id[doc_id]["robot_text_path"],
                records_by_id[doc_id]["robot_content_sha256"],
            ) for doc_id in document_ids
        ])
        conn.executemany("INSERT INTO corpus VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", [
            tuple(chunk[key] for key in (
                "chunk_id", "document_id", "canonical_document_id", "collection_id", "domain", "authority_role",
                "authority_priority", "current_status", "answer_eligibility", "contractor_binding", "effective_date",
                "locator", "human_source_path", "robot_text_path", "content_sha256", "content"
            )) for chunk in selected
        ])
        conn.execute("INSERT INTO corpus(corpus) VALUES('optimize')")
        vectors_written = 0
        if vectors:
            vector_rows = [
                (chunk["chunk_id"], vector_model, vector_dim, vectors[chunk["chunk_id"]])
                for chunk in selected if chunk["chunk_id"] in vectors
            ]
            conn.executemany("INSERT INTO vectors VALUES(?,?,?,?)", vector_rows)
            vectors_written = len(vector_rows)
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.close()
        if integrity != "ok":
            temp.unlink(missing_ok=True)
            raise RuntimeError(f"index integrity failure for {filename}: {integrity}")
        os.replace(temp, output)
        catalog.append({
            "path": f"indexes/{filename}",
            "purpose": rule["purpose"],
            "default_allowed": rule["default_allowed"],
            "allowed_intents": sorted(rule["allowed_intents"]),
            "retrieval_stage": rule["retrieval_stage"],
            "documents": len(document_ids),
            "chunks": len(selected),
            "authority_first": True,
            "human_source_path_mode": "unindexed_citation_metadata_only",
            "semantic_index": {
                "model": vector_model,
                "dim": vector_dim,
                "vectors": vectors_written,
            } if vectors else None,
        })
    return catalog
