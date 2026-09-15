from __future__ import annotations

import re
from typing import Any


ROLE_PRIORITY = {
    "controlling_regulation": 10,
    "contract_clause": 20,
    "executive_order": 25,
    "binding_government_issuance": 30,
    "dcsa_interpretation": 40,
    "official_operational_guidance": 50,
    "incorporated_framework": 60,
    "training_or_context": 70,
    "adjudicative_precedent": 80,
    "historical_reference": 90,
    "unclassified_role": 99,
}


def parse_authority_header(text: str) -> dict[str, Any]:
    header = text[:8000]
    fields: dict[str, Any] = {}
    patterns = {
        "header_tier": r"(?mi)^TIER\s*:\s*(\d+)",
        "header_status": r"(?mi)^STATUS\s*:\s*([^\r\n]+)",
        "effective_date": r"(?mi)^EFFECTIVE\s*:\s*([^\r\n]+)",
        "document_type_header": r"(?mi)^DOC TYPE\s*:\s*([^\r\n]+)",
        "metadata_basis": r"(?mi)^BASIS\s*:\s*([^\r\n]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, header)
        if match:
            value: Any = match.group(1).strip()
            fields[key] = int(value) if key == "header_tier" else value
    return fields


def classify_authority(record: dict[str, Any], header: dict[str, Any]) -> tuple[str, str]:
    collection = str(record.get("collection_id") or "").lower()
    status = str(record.get("current_status") or "").lower()
    doc_type = str(header.get("document_type_header") or record.get("document_type") or "").lower()
    if status in {"historical", "rescinded", "superseded"} or collection in {"isl_legacy", "nispom_legacy"}:
        return "historical_reference", "not_independently_binding"
    if collection == "doha_decisions":
        return "adjudicative_precedent", "not_independently_binding"
    if collection == "cfr" or doc_type in {"regulation", "statute"}:
        return "controlling_regulation", "generally_binding_with_scope_checks"
    if collection in {"dfars", "far"} or "contract clause" in doc_type:
        return "contract_clause", "binding_only_when_applicable_or_incorporated"
    if collection == "executive_orders" or doc_type == "executive order":
        return "executive_order", "government_direction_not_automatically_contractor_binding"
    if collection in {"dodi", "sead", "icd"} or doc_type in {"directive", "instruction", "manual"}:
        return "binding_government_issuance", "scope_dependent_not_automatically_contractor_binding"
    if collection == "isl_current":
        return "dcsa_interpretation", "interpretive_not_independently_binding"
    if collection == "nist":
        return "incorporated_framework", "binding_only_when_incorporated"
    if collection in {"voi", "cdse_pulse", "cdse_resources"}:
        return "training_or_context", "not_independently_binding"
    if collection in {
        "job_aids", "cui", "nisp_tools", "forms", "information_security", "rmf", "cmmc",
        "trusted_workforce_2_0", "nisp_cybersecurity", "personnel_vetting_forms", "foci", "export_control",
        "industrial_security"
    }:
        return "official_operational_guidance", "implementation_guidance_scope_check_required"
    return "unclassified_role", "unresolved"


def lifecycle_eligibility(record: dict[str, Any], doha_eligible: bool | None) -> tuple[str, str]:
    status = str(record.get("current_status") or "").lower()
    if status in {"current", "active"}:
        return "answer_eligible", "manifest_current"
    if status == "current_or_verify":
        return "unresolved_currency", "requires_official_currency_verification"
    if status == "historical_case_research":
        return ("precedent_only", "topic_and_outcome_confirmed") if doha_eligible else ("exact_case_only", "untagged_or_incomplete_doha_metadata")
    if status in {"historical", "legacy", "rescinded", "superseded", "archived"}:
        return "historical_only", f"lifecycle_{status}"
    return "excluded_unresolved", "unknown_lifecycle"
