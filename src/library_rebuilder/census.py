"""Read-only census: what in an existing library can actually be rebuilt, and how."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from .common import read_json, sha256_file, utc_now

MANIFEST = "ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
POINTER = "ROBOT_READABLE_DIRECTORY/STATE/CURRENT_CUSTODIAN_RELEASE.json"
URL_FIELDS = ("source_url", "canonical_source_url", "canonical_source_uri")
ROUTES = ("reacquire_from_official_url", "retained_bytes_only", "source_missing",
          "duplicate_skip", "doha_unsupported")


def route(record: dict) -> str:
    # Order matters: DOHA scope is excluded before any per-source judgment.
    if record.get("collection_id") == "doha_decisions":
        return "doha_unsupported"
    if record.get("duplicate_of"):
        return "duplicate_skip"
    if record.get("source_exists") is False:
        return "source_missing"
    if any(record.get(field) for field in URL_FIELDS):
        return "reacquire_from_official_url"
    return "retained_bytes_only"


def census(library: Path) -> dict:
    library = Path(library).resolve()
    manifest = library / MANIFEST
    documents = []
    with manifest.open(encoding="utf-8-sig") as handle:
        for number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{MANIFEST} line {number} is not JSON: {exc}") from exc
            documents.append({
                "document_id": record.get("document_id"),
                "collection_id": record.get("collection_id"),
                "current_status": record.get("current_status"),
                "route": route(record),
                "official_url": next((record[f] for f in URL_FIELDS if record.get(f)), None),
                # Lets acquisition report whether the official source changed since capture.
                "recorded_sha256": record.get("source_sha256"),
            })
    pointer = library / POINTER
    by_route = Counter(item["route"] for item in documents)
    by_collection: dict[str, Counter] = {}
    for item in documents:
        by_collection.setdefault(item["collection_id"] or "<none>", Counter())[item["route"]] += 1
    return {
        "schema_version": "1.0",
        "generated_utc": utc_now(),
        "source_release_id": read_json(pointer).get("release_id") if pointer.is_file() else None,
        "manifest_sha256": sha256_file(manifest),
        "total_documents": len(documents),
        "by_route": {name: by_route.get(name, 0) for name in ROUTES},
        "by_collection": {name: dict(counts) for name, counts in sorted(by_collection.items())},
        "notes": [
            "Read-only. The library was not modified.",
            "retained_bytes_only records have no official origin on record; rebuilding them needs provenance review, not a guessed URL.",
            "doha_unsupported records are excluded until portable DOHA reconstruction exists.",
        ],
        "documents": documents,
    }
