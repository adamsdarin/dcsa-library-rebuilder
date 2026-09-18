"""Derived knowledge layer over the enriched manifest.

Builds an issuance/subject graph and lints it for corpus-wide contradictions that
per-answer retrieval gating cannot see. Everything here is *derived*: edges carry an
explicit basis and confidence, and nothing in this module is answer evidence. The graph
is a maintenance artifact written under the candidate release directory, not a published
consumer surface -- consumers continue to cite chunks, never a topic.

Metadata only. This module never reads document text; text-derived relationships
(citation edges, incorporation by reference) are deliberately out of scope until the
metadata edges here have been reviewed for quality.
"""
from __future__ import annotations

import collections
import re
from typing import Any

from .common import normalize_domain, utc_now


# --------------------------------------------------------------------------------------
# Issuance identifiers
# --------------------------------------------------------------------------------------
# A "family" is one issuance identity across editions: DoDI 5200.48 (2020) and DoDI
# 5200.48 (2024) share a family, which is what makes supersession derivable at all. The
# series letter and volume are part of the identity (DoDM 5200.01 Vol 1 and Vol 2 are
# different documents); dates, change numbers, and incorporation notices are not.

ISSUANCE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("cfr", re.compile(r"(?i)\b(\d{1,2})\s*C\.?\s?F\.?\s?R\.?\s*(?:part\s*)?(\d{2,4})\b")),
    ("dfars", re.compile(r"(?i)\b(DFARS|FAR)\s*(\d{3}\.\d+(?:-\d+)?)")),
    # Captures the series letter only, so "DoDI 5200.48" and "DoD Instruction 5200.48"
    # land in one family instead of two.
    ("dod", re.compile(r"(?i)\bDoD\s*(I|D|M)(?:nstruction|irective|anual)?\s*(\d{4}\.\d+)(?:\s*(?:Volume|Vol\.?)\s*(\d+))?")),
    ("sead", re.compile(r"(?i)\bSEAD[\s\-]*(\d+)\b")),
    ("eo", re.compile(r"(?i)\b(?:E\.?\s?O\.?|Executive\s+Order)\s*(\d{5})\b")),
    ("isl", re.compile(r"(?i)\bISL[\s\-]*(\d{4})[\s\-](\d{2})\b")),
    ("nist", re.compile(r"(?i)\bNIST\s*SP\s*(\d{3}-\d+[A-Za-z]?)")),
    ("icd", re.compile(r"(?i)\bICD\s*(\d{3})\b")),
    ("cnssi", re.compile(r"(?i)\bCNSSI\s*(\d{3,4})\b")),
    ("usc", re.compile(r"(?i)\b(\d{1,2})\s*U\.?\s?S\.?\s?C\.?\s*(?:§\s*)?(\d{3,4})\b")),
    ("sf", re.compile(r"(?i)\bSF[\s\-]*(\d{2,4}[a-z]?)\b")),
)


def issuance_family(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return (family_key, display) for a record, or (None, None) when unidentifiable.

    Matches the title first and the document_id second: titles carry the human form
    ("DoD Instruction 5200.48"), document_ids carry the slug form. The first matching
    pattern wins, so a title naming both an issuance and the CFR part it implements
    resolves to the issuance -- the more specific identity.
    """
    haystacks = [
        str(record.get("title") or ""),
        str(record.get("document_id") or "").replace("-", " "),
    ]
    for haystack in haystacks:
        for kind, pattern in ISSUANCE_PATTERNS:
            match = pattern.search(haystack)
            if not match:
                continue
            parts = [part for part in match.groups() if part]
            return f"{kind}:" + ".".join(part.upper() for part in parts), match.group(0).strip()
    return None, None


# --------------------------------------------------------------------------------------
# Subject axis
# --------------------------------------------------------------------------------------
# collection_id mixes two axes: some collections name a *subject* (cui, foci, rmf) and
# some name a *source type* (cfr, dodi, sead, forms). Grouping naively by collection
# therefore cannot support the "guidance with no controlling authority" check, because
# the guidance and the regulation covering one subject live in different collections by
# construction. This mapping is explicit rather than inferred so a wrong grouping is
# visible and correctable instead of silently skewing lint output.

SUBJECT_BEARING_COLLECTIONS = {
    "cui": "cui",
    "rmf": "rmf",
    "cmmc": "cmmc",
    "foci": "foci",
    "export_control": "export_control",
    "trusted_workforce_2_0": "trusted_workforce_2_0",
    "nisp_cybersecurity": "nisp_cybersecurity",
    "information_security": "information_security",
    "industrial_security": "industrial_security",
    "personnel_vetting_forms": "personnel_vetting_forms",
    "nisp_tools": "nisp_tools",
}

# Which controlling authority governs which subject cannot be derived from the manifest:
# the authority and the subject live in different collections by construction (32 CFR 2002
# is filed under `cfr`, the CUI guidance under `cui`), and nothing in the metadata links
# them. Asserting that link is regulatory interpretation, so it is curated here by a human
# rather than inferred -- the same reason Guidance Watch gates its Stage 2/3 writes.
#
# Format: subject_id -> list of document_id values that carry controlling authority for it.
# Three states, deliberately distinct:
#   absent      -> not yet reviewed; lint reports `subject_authority_unmapped`
#   populated   -> lint verifies each entry is present and answer-eligible
#   empty list  -> reviewed and found to have NO contractor-controlling authority. That is a
#                  finding, not silence: guidance in such a subject cannot establish a
#                  contractor obligation, so a consumer must abstain or qualify.
#
# Confirmed by Darin 2026-09-09 against the ten controlling_regulation / contract_clause
# records the corpus actually holds.
SUBJECT_CONTROLLING_AUTHORITY: dict[str, list[str]] = {
    "cui": [
        "dcsa-cfr-32cfr-2002-cui",
        "dcsa-dfars-dfars-252-204-7012-safeguarding-cui",
    ],
    "industrial_security": [
        "dcsa-cfr-32-cfr-part-117-up-to-date-as-of-7-24-2026",
        "dcsa-cfr-32cfr-2004-nisp-directive",
    ],
    "export_control": [
        "dcsa-cfr-ear-15-cfr-300-744-2025",
        "dcsa-cfr-ear-15-cfr-745-799-2025",
        "dcsa-cfr-itar-22-cfr-1-299-2025",
    ],
    "cmmc": [
        "dcsa-dfars-dfars-252-204-7012-safeguarding-cui",
        "dcsa-cfr-32cfr-2002-cui",
    ],
    "foci": [
        "dcsa-cfr-32-cfr-part-117-up-to-date-as-of-7-24-2026",
    ],
    "nisp_cybersecurity": [
        "dcsa-cfr-32-cfr-part-117-up-to-date-as-of-7-24-2026",
        "dcsa-dfars-dfars-252-204-7012-safeguarding-cui",
    ],
    # Contractor personnel vetting runs on SEADs and Executive Orders, which
    # classify_authority types as binding_government_issuance / executive_order --
    # explicitly not automatically contractor-binding. No controlling regulation exists for
    # these subjects, and that is the answer rather than a gap to be filled.
    "personnel_vetting_forms": [],
    "trusted_workforce_2_0": [],
}

CONTROLLING_ROLES = {"controlling_regulation", "contract_clause"}
DEPENDENT_ROLES = {
    "dcsa_interpretation",
    "official_operational_guidance",
    "incorporated_framework",
    "training_or_context",
}
CURRENT_STATUSES = {"current", "active"}
NON_CURRENT_STATUSES = {"historical", "superseded", "rescinded", "legacy", "archived"}

# Collections that exist to hold superseded material. A rescinded ISL with no successor is
# these collections working correctly, so supersession checks skip families living wholly
# inside them.
HISTORICAL_BY_DESIGN_COLLECTIONS = {"isl_legacy", "nispom_legacy"}

# Collections holding material *about* an issuance rather than the issuance itself. A CDSE
# deck titled for DoDI 5200.08 shares that issuance family legitimately, so it is not
# evidence of a filing split.
REFERENCING_COLLECTIONS = {"cdse_resources", "cdse_pulse", "voi", "job_aids"}


def raw_domain(record: dict[str, Any]) -> str:
    """The domain as the source manifest spells it.

    Enrichment folds `domain` and preserves the original in `source_domain`, so the casing
    check has to look at the preserved value or it goes blind the moment the fold lands.
    Falls back to `domain` for manifests enriched before that change.
    """
    return str(record.get("source_domain") or record.get("domain") or "")


def subject_for(record: dict[str, Any], family: str | None) -> tuple[str, str]:
    """Return (subject_id, basis). The basis records how firm the grouping is."""
    collection = str(record.get("collection_id") or "")
    if collection in SUBJECT_BEARING_COLLECTIONS:
        return SUBJECT_BEARING_COLLECTIONS[collection], "subject_bearing_collection"
    if family:
        return f"issuance:{family}", "issuance_family"
    return f"domain:{normalize_domain(record.get('domain'))}", "domain_fallback"


def _status(record: dict[str, Any]) -> str:
    return str(record.get("current_status") or "").lower()


# --------------------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------------------

def build_edges(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Derive typed edges from manifest metadata.

    Every edge carries `basis` (what in the data produced it) and `confidence`:
    `recorded` for edges read straight out of the manifest, `derived` for edges inferred
    by comparing status and date. Nothing downstream may treat `derived` as fact without
    review -- that distinction is the reason it is on the edge.
    """
    edges: list[dict[str, Any]] = []
    for record in records:
        document_id = record["document_id"]
        if record.get("duplicate_of"):
            edges.append({
                "edge_type": "duplicate_of",
                "from_document_id": document_id,
                "to_document_id": record["duplicate_of"],
                "basis": record.get("answer_eligibility_basis") or "content_hash_match",
                "confidence": "recorded",
            })
        for entry in record.get("rename_history") or []:
            edges.append({
                "edge_type": "renamed_from",
                "from_document_id": document_id,
                "to_path": entry.get("previous_human_source_path"),
                "basis": entry.get("reason") or "rename_history",
                "confidence": "recorded",
            })

    families: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in records:
        family, _ = issuance_family(record)
        if family:
            families[family].append(record)

    for family, members in sorted(families.items()):
        for member in members:
            edges.append({
                "edge_type": "same_issuance_family",
                "from_document_id": member["document_id"],
                "family": family,
                "basis": "issuance identifier extracted from title or document_id",
                "confidence": "derived",
            })
        if len(members) < 2:
            continue
        current = [item for item in members if _status(item) in CURRENT_STATUSES]
        superseded = [item for item in members if _status(item) in NON_CURRENT_STATUSES]
        for successor in current:
            for predecessor in superseded:
                edges.append({
                    "edge_type": "supersedes",
                    "from_document_id": successor["document_id"],
                    "to_document_id": predecessor["document_id"],
                    "family": family,
                    "basis": f"same issuance family; successor current, predecessor {predecessor.get('current_status')}",
                    "confidence": "derived",
                })
    return edges


def build_topics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cluster records onto the subject axis, ordered by authority priority within each."""
    buckets: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    bases: dict[str, set[str]] = collections.defaultdict(set)
    for record in records:
        family, _ = issuance_family(record)
        subject, basis = subject_for(record, family)
        buckets[subject].append(record)
        bases[subject].add(basis)

    topics: list[dict[str, Any]] = []
    for subject, members in sorted(buckets.items()):
        members.sort(key=lambda item: (item.get("authority_priority", 99), str(item.get("document_id"))))
        anchor = members[0]
        topics.append({
            "topic_id": subject,
            "membership_basis": sorted(bases[subject]),
            "documents": len(members),
            "roles": dict(collections.Counter(item.get("authority_role") for item in members)),
            "anchor_document_id": anchor["document_id"],
            "anchor_role": anchor.get("authority_role"),
            "anchor_status": anchor.get("current_status"),
            "anchor_eligibility": anchor.get("answer_eligibility"),
            "has_controlling_authority": any(item.get("authority_role") in CONTROLLING_ROLES for item in members),
            "current_documents": sum(1 for item in members if _status(item) in CURRENT_STATUSES),
            "document_ids": [item["document_id"] for item in members],
        })
    return topics


def build_graph(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build the derived graph. DOHA decisions are collapsed, not expanded.

    The DOHA set is ~92% of the manifest and is a single adjudicative-precedent subject
    with its own dedicated router and case index. Expanding 10k decisions into the topic
    graph would swamp every count without telling anyone anything DOHA_SEAD4_SEARCH_
    ROUTER.json does not already say, so it is excluded and reported as a count. This
    mirrors build_chunks, which skips the same collection.
    """
    graphed = [record for record in records if record.get("collection_id") != "doha_decisions"]
    edges = build_edges(graphed)
    topics = build_topics(graphed)
    return {
        "schema_version": "1.0",
        "generated_utc": utc_now(),
        "manifest_records": len(records),
        "graphed_records": len(graphed),
        "excluded_doha_records": len(records) - len(graphed),
        "topics": topics,
        "edges": edges,
        "edge_counts": dict(collections.Counter(edge["edge_type"] for edge in edges)),
    }


# --------------------------------------------------------------------------------------
# Lint
# --------------------------------------------------------------------------------------
# Priority follows the remediation-queue convention in release.py: lower is more urgent,
# and 10 means an invariant is being violated somewhere in the corpus.

def lint_graph(records: list[dict[str, Any]], graph: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    by_id = {record["document_id"]: record for record in records}
    graphed = [record for record in records if record.get("collection_id") != "doha_decisions"]

    # 1. Domain casing variants. Two spellings of one domain silently split every
    #    domain-keyed grouping, including this module's own fallback.
    domain_variants: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for record in records:
        raw = raw_domain(record)
        if raw:
            domain_variants[raw.casefold()][raw] += 1
    for normalized, counts in sorted(domain_variants.items()):
        if len(counts) > 1:
            findings.append({
                "check": "domain_case_variant",
                "priority": 10,
                "normalized_domain": normalized,
                "variants": dict(sorted(counts.items())),
                "detail": "One domain is stored under more than one casing; every domain-keyed grouping splits across the variants.",
                "required_resolution": "Normalise domain casing in the source manifest, then rebuild.",
            })

    # 2. Invariant 7 ("guidance cannot independently create an obligation") in its
    #    corpus-wide form. This only runs on subject-bearing collections: an issuance
    #    family is a single document's identity, not a subject, so a lone DoD directive
    #    trivially "containing no regulation" says nothing. The controlling authority for
    #    a subject usually sits in a different collection, so the link comes from the
    #    curated table, not from topic membership.
    for topic in graph["topics"]:
        if topic["membership_basis"] != ["subject_bearing_collection"]:
            continue
        dependents = [
            document_id for document_id in topic["document_ids"]
            if by_id[document_id].get("authority_role") in DEPENDENT_ROLES
            and by_id[document_id].get("answer_eligibility") == "answer_eligible"
        ]
        if not dependents:
            continue
        mapped = SUBJECT_CONTROLLING_AUTHORITY.get(topic["topic_id"])
        if mapped == []:
            findings.append({
                "check": "subject_has_no_contractor_controlling_authority",
                "priority": 20,
                "topic_id": topic["topic_id"],
                "answer_eligible_dependents": len(dependents),
                "example_document_ids": dependents[:5],
                "detail": "Reviewed and confirmed to have no contractor-controlling regulation or clause; its guidance is government direction that does not automatically bind a contractor.",
                "required_resolution": "None -- this is the settled state. Consumers must abstain or qualify rather than state a contractor obligation from this subject.",
            })
            continue
        if mapped is None:
            findings.append({
                "check": "subject_authority_unmapped",
                "priority": 20,
                "topic_id": topic["topic_id"],
                "answer_eligible_dependents": len(dependents),
                "holds_own_controlling_authority": topic["has_controlling_authority"],
                "detail": "No controlling authority is declared for this subject, so its guidance cannot be checked against invariant 7.",
                "required_resolution": "Add this subject to SUBJECT_CONTROLLING_AUTHORITY with the document_id values that govern it.",
            })
            continue
        missing = [document_id for document_id in mapped if document_id not in by_id]
        unusable = [
            document_id for document_id in mapped
            if document_id in by_id and by_id[document_id].get("answer_eligibility") != "answer_eligible"
        ]
        if missing or unusable:
            findings.append({
                "check": "subject_without_controlling_authority",
                "priority": 10,
                "topic_id": topic["topic_id"],
                "answer_eligible_dependents": len(dependents),
                "example_document_ids": dependents[:5],
                "declared_authority": mapped,
                "missing_from_corpus": missing,
                "present_but_not_answer_eligible": unusable,
                "detail": "Answer-eligible guidance depends on a subject whose declared controlling authority is absent or itself excluded from answer indexes; guidance cannot independently create an obligation.",
                "required_resolution": "Acquire or re-verify the controlling authority for this subject, or reclassify the guidance as context.",
            })

    # 3. Topic anchored on something no longer current while dependents are current.
    for topic in graph["topics"]:
        if str(topic.get("anchor_status") or "").lower() in NON_CURRENT_STATUSES and topic["current_documents"]:
            findings.append({
                "check": "stale_topic_anchor",
                "priority": 20,
                "topic_id": topic["topic_id"],
                "anchor_document_id": topic["anchor_document_id"],
                "anchor_role": topic["anchor_role"],
                "anchor_status": topic["anchor_status"],
                "current_dependents": topic["current_documents"],
                "detail": "The highest-authority document in this subject is not current, but current documents depend on the subject.",
                "required_resolution": "Verify whether a current successor exists and record it, or re-anchor the subject.",
            })

    # 4. Unresolved currency on the anchor of a subject that has dependents.
    for topic in graph["topics"]:
        if topic.get("anchor_eligibility") == "unresolved_currency" and topic["documents"] > 1:
            findings.append({
                "check": "unresolved_controlling_anchor",
                "priority": 20,
                "topic_id": topic["topic_id"],
                "anchor_document_id": topic["anchor_document_id"],
                "dependent_documents": topic["documents"] - 1,
                "detail": "The anchor of this subject is excluded from answer indexes pending currency verification, leaving its dependents unsupported.",
                "required_resolution": "Prioritise currency verification for this anchor; it gates a whole subject.",
            })

    family_members: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for record in graphed:
        family, _ = issuance_family(record)
        if family:
            family_members[family].append(record)

    for family, members in sorted(family_members.items()):
        collections_seen = {str(item.get("collection_id") or "") for item in members}

        # 5. Every edition superseded and nothing current holding the line. Families that
        #    live entirely in a historical-by-design collection are those collections
        #    doing their job, not a gap.
        statuses = {_status(item) for item in members if _status(item)}
        if (
            statuses
            and statuses <= NON_CURRENT_STATUSES
            and not collections_seen <= HISTORICAL_BY_DESIGN_COLLECTIONS
        ):
            findings.append({
                "check": "superseded_without_successor",
                "priority": 30,
                "family": family,
                "documents": len(members),
                "collections": sorted(collections_seen),
                "example_document_ids": [item["document_id"] for item in members[:5]],
                "detail": "Every edition of this issuance is superseded or historical and no current edition is held.",
                "required_resolution": "Confirm whether a current edition exists and acquire it, or record the issuance as cancelled.",
            })

        # 6. One issuance filed across multiple collections. Collections that reference an
        #    issuance rather than hold it are excluded first: a training deck named for a
        #    directive shares its family by design.
        holding = {
            str(item.get("collection_id") or "") for item in members
            if str(item.get("collection_id") or "") not in REFERENCING_COLLECTIONS
            and item.get("authority_role") != "training_or_context"
        }
        if len(holding) > 1:
            findings.append({
                "check": "family_split_across_collections",
                "priority": 30,
                "family": family,
                "holding_collections": sorted(holding),
                "all_collections": sorted(collections_seen),
                "documents": len(members),
                "detail": "Editions of one issuance are held under different collections, which splits it across retrieval routes.",
                "required_resolution": "Refile the outliers, or confirm the split is intentional.",
            })

        # 7. A current edition dated earlier than a superseded one in the same family.
        current_dated = [
            (item["document_id"], str(item["effective_date"]))
            for item in members if _status(item) in CURRENT_STATUSES and item.get("effective_date")
        ]
        stale_dated = [
            (item["document_id"], str(item["effective_date"]))
            for item in members if _status(item) in NON_CURRENT_STATUSES and item.get("effective_date")
        ]
        for current_id, current_date in current_dated:
            for stale_id, stale_date in stale_dated:
                if current_date < stale_date:
                    findings.append({
                        "check": "effective_date_inversion",
                        "priority": 30,
                        "family": family,
                        "current_document_id": current_id,
                        "current_effective_date": current_date,
                        "superseded_document_id": stale_id,
                        "superseded_effective_date": stale_date,
                        "detail": "A document marked current is dated earlier than one marked superseded in the same issuance family.",
                        "required_resolution": "Re-check which edition is actually current against the official source.",
                    })

    # 8. Subjects that exist only because nothing better was available to group on.
    for topic in graph["topics"]:
        if topic["documents"] == 1 and topic["membership_basis"] == ["domain_fallback"]:
            findings.append({
                "check": "orphan_document",
                "priority": 40,
                "topic_id": topic["topic_id"],
                "document_id": topic["anchor_document_id"],
                "detail": "This document carries no issuance identifier and no subject-bearing collection; it groups with nothing.",
                "required_resolution": "Add an issuance identifier to the title, or assign a subject-bearing collection.",
            })

    findings.sort(key=lambda item: (
        item["priority"],
        item["check"],
        str(item.get("topic_id") or item.get("family") or item.get("normalized_domain") or ""),
    ))
    return findings


def lint_report(records: list[dict[str, Any]], source: str) -> dict[str, Any]:
    """Build the graph and lint it, returning the report the CLI prints and writes."""
    graph = build_graph(records)
    findings = lint_graph(records, graph)
    return {
        "schema_version": "1.0",
        "linted_utc": utc_now(),
        "source": source,
        "manifest_records": graph["manifest_records"],
        "graphed_records": graph["graphed_records"],
        "excluded_doha_records": graph["excluded_doha_records"],
        "topics": len(graph["topics"]),
        "edges": len(graph["edges"]),
        "edge_counts": graph["edge_counts"],
        "findings": findings,
        "counts_by_check": dict(collections.Counter(item["check"] for item in findings)),
        "counts_by_priority": dict(collections.Counter(item["priority"] for item in findings)),
    }
