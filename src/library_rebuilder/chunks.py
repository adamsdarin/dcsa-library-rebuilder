from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from .common import sha256_text


def _page_chunks(text: str, target: int, maximum: int, overlap: int) -> Iterable[tuple[int, int, str]]:
    start = 0
    length = len(text)
    while start < length:
        hard_end = min(start + maximum, length)
        preferred_end = min(start + target, length)
        end = hard_end
        if hard_end < length:
            paragraph = text.rfind("\n\n", preferred_end, hard_end)
            line = text.rfind("\n", preferred_end, hard_end)
            boundary = max(paragraph + 2 if paragraph >= 0 else -1, line + 1 if line >= 0 else -1)
            if boundary > start:
                end = boundary
        chunk = text[start:end]
        if chunk.strip():
            yield start, end, chunk
        if end >= length:
            break
        next_start = max(end - overlap, start + 1)
        newline = text.find("\n", next_start, end)
        start = newline + 1 if newline >= 0 else next_start


def build_chunks(root: Path, records: list[dict[str, Any]], target: int, maximum: int, overlap: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for record in records:
        if record.get("collection_id") == "doha_decisions" or record.get("duplicate_of"):
            continue
        robot_rel = record["robot_text_path"]
        text = (root / robot_rel).read_text(encoding="utf-8", errors="replace")
        pages = text.split("\f")
        has_page_markers = len(pages) > 1
        for page_number, page in enumerate(pages, 1):
            for start, end, content in _page_chunks(page, target, maximum, overlap):
                locator = f"page:{page_number};chars:{start}-{end}" if has_page_markers else f"block:1;chars:{start}-{end}"
                chunk_id = f"{record['document_id']}:{sha256_text(locator + '|' + content)[:16]}"
                chunks.append({
                    "chunk_id": chunk_id,
                    "document_id": record["document_id"],
                    "canonical_document_id": record["canonical_document_id"],
                    "collection_id": record.get("collection_id"),
                    "domain": record.get("domain"),
                    "title": record.get("title") or record["document_id"],
                    "authority_role": record["authority_role"],
                    "authority_priority": record["authority_priority"],
                    "manifest_authority_tier": record.get("authority_tier"),
                    "current_status": record.get("current_status"),
                    "answer_eligibility": record["answer_eligibility"],
                    "contractor_binding": record["contractor_binding"],
                    "effective_date": record.get("effective_date"),
                    "locator": locator,
                    "human_source_path": record["human_source_path"],
                    "robot_text_path": robot_rel,
                    "content_sha256": sha256_text(content),
                    "content": content,
                })
    return chunks

