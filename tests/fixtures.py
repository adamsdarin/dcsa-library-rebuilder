"""Synthetic, reviewed recipe inputs shared by the tests. No real library data."""
from pathlib import Path

from library_rebuilder.common import sha256_file, write_json

REVIEW = {k: "synthetic evidence" for k in ("reviewed_by", "reviewed_utc", "identity", "provenance",
                                              "extraction", "parity", "taxonomy", "lifecycle")}

CFR_TEXT = ("32 CFR Part 117 National Industrial Security Program Operating Manual\n\n117.7 Procedures\f"
            "(b) Insider threat program. The contractor must designate an insider threat program senior "
            "official who is cleared in connection with the facility clearance.\n")

DOCS = {
    "cfr-117": {"collection_id": "cfr", "domain": "REGULATIONS", "authority_tier": 1, "current_status": "current",
                "folder": "REGULATIONS/CFR", "text": CFR_TEXT, "source": b"%PDF synthetic 32 CFR 117"},
    "voi-2026-01": {"collection_id": "voi", "domain": "TRAINING_AND_AWARENESS", "authority_tier": 7, "current_status": "current",
                    "folder": "TRAINING_AND_AWARENESS/VOI", "text": "Voice of Industry: insider threat awareness reminders for FSOs.\n",
                    "source": b"%PDF synthetic VOI"},
    "isl-2011-02": {"collection_id": "isl_legacy", "domain": "INDUSTRIAL_SECURITY", "authority_tier": 3, "current_status": "historical",
                    "folder": "INDUSTRIAL_SECURITY/ISL_LEGACY", "text": "ISL 2011-02 legacy insider threat guidance, rescinded.\n",
                    "source": b"%PDF synthetic ISL"},
    "cfr-117-copy": {"collection_id": "cfr", "domain": "REGULATIONS", "authority_tier": 1, "current_status": "current",
                     "folder": "REGULATIONS/CFR/DUPLICATE_UPLOADS", "text": CFR_TEXT, "source": b"%PDF synthetic 32 CFR 117"},
}

POSITIVE_CASE = {"id": "insider-threat-official", "query": "insider threat program senior official",
                 "intent": "contractor_or_fso_obligation", "require_hit": True, "require_locator": True,
                 "expected_document_ids": ["cfr-117"], "expected_passages": ["insider threat program senior official"],
                 "expected_first_roles": ["controlling_regulation"]}


def make_recipe_dir(directory: Path, doc_ids=None, cases=None) -> Path:
    directory = Path(directory)
    (directory / "sources").mkdir(parents=True, exist_ok=True)
    items = []
    for doc_id in doc_ids or list(DOCS):
        spec = DOCS[doc_id]
        source = directory / "sources" / f"{doc_id}.pdf"
        source.write_bytes(spec["source"])
        write_json(directory / "sources" / f"{doc_id}.pdf.intake.json", {
            "producer_id": "dcsa-library-rebuilder", "approval_state": "quarantined_unreviewed",
            "requested_source_uri": f"https://www.example.gov/{doc_id}.pdf",
            "resolved_source_uri": f"https://www.example.gov/{doc_id}.pdf",
            "retrieved_at": "2026-01-01T00:00:00+00:00", "mime_type": "application/pdf",
            "source_filename": source.name, "source_sha256": sha256_file(source), "source_bytes": source.stat().st_size})
        robot = directory / f"{doc_id}.txt"
        robot.write_text(spec["text"], encoding="utf-8", newline="\n")
        items.append({"package": f"sources/{doc_id}.pdf.intake.json", "robot_file": robot.name,
                      "robot_sha256": sha256_file(robot), "review": REVIEW,
                      "record": {"document_id": doc_id, "collection_id": spec["collection_id"], "domain": spec["domain"],
                                 "authority_tier": spec["authority_tier"], "current_status": spec["current_status"],
                                 "title": doc_id.upper(),
                                 "human_source_path": f"HUMAN_READABLE_DIRECTORY/{spec['folder']}/{doc_id}.pdf",
                                 "robot_text_path": f"ROBOT_READABLE_DIRECTORY/TEXT/{spec['folder']}/{doc_id}.txt"}})
    write_json(directory / "intake_plan.json", {"schema_version": "1.0", "items": items})
    write_json(directory / "golden_queries.json", {"cases": cases if cases is not None else [POSITIVE_CASE]})
    return directory
