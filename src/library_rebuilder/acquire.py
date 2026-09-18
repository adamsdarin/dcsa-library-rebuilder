"""Independent acquisition: fetch official HTTPS sources into a run-owned quarantine.

Writes Archivist intake packages directly, so a rebuild needs no Librarian checkout.
It never guesses URLs, never reads an existing library, and reports every gap.
"""
from __future__ import annotations

from email.message import Message
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

from .common import read_json, sha256_file, utc_now, write_json

PRODUCER = "dcsa-library-rebuilder"
USER_AGENT = "dcsa-library-rebuilder/0.1 (official-source library reconstruction)"
CHUNK = 1 << 20
# Official-source hosts seen in DCSA Library provenance. Override in config/rebuilder.json.
DEFAULT_SETTINGS = {
    "allowed_domains": ["gov", "mil", "cdse.edu", "wbdg.org", "resources.sei.cmu.edu"],
    "max_bytes": 250 * 2**20,
    "delay_seconds": 1.0,
}


class Refused(Exception):
    """A source was deliberately not acquired; recorded as a gap."""


def host_allowed(url: str, allowed: list[str]) -> bool:
    parts = urllib.parse.urlsplit(url)
    host = (parts.hostname or "").casefold()
    return parts.scheme == "https" and any(host == d or host.endswith("." + d) for d in allowed)


class _Redirects(urllib.request.HTTPRedirectHandler):
    """Every hop must stay on HTTPS and the allowlist; the chain is kept as provenance."""

    def __init__(self, allowed):
        self.allowed, self.chain = allowed, []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        newurl = urllib.parse.urljoin(req.full_url, newurl)
        if not host_allowed(newurl, self.allowed):
            raise Refused(f"redirect leaves the HTTPS allowlist: {newurl}")
        self.chain.append({"status": code, "from": req.full_url, "to": newurl})
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _robots_allows(url: str, allowed: list[str], handlers, cache: dict) -> bool:
    parts = urllib.parse.urlsplit(url)
    origin = f"{parts.scheme}://{parts.netloc}"
    if origin not in cache:
        parser = urllib.robotparser.RobotFileParser()
        opener = urllib.request.build_opener(*handlers, _Redirects(allowed))
        request = urllib.request.Request(origin + "/robots.txt", headers={"User-Agent": USER_AGENT})
        # RFC 9309: 4xx means no restrictions; 5xx or unreachable means assume full disallow.
        try:
            with opener.open(request, timeout=30) as response:
                parser.parse(response.read(512_000).decode("utf-8", "replace").splitlines())
        except urllib.error.HTTPError as exc:
            parser.parse([])
            parser.disallow_all = exc.code >= 500
        except (urllib.error.URLError, OSError, Refused):
            parser.parse([])
            parser.disallow_all = True
        cache[origin] = parser
    return cache[origin].can_fetch(USER_AGENT, url)


def _filename(url: str, headers) -> str:
    message = Message()
    message["content-disposition"] = headers.get("Content-Disposition", "")
    name = message.get_filename() or Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name or "").strip(" .") or "source"
    return f"{hashlib.sha256(url.encode()).hexdigest()[:12]}-{name[-120:]}"


def fetch(url: str, out_dir: Path, allowed: list[str], max_bytes: int, hints: list[dict],
          handlers=(), robots: dict | None = None) -> dict:
    if not host_allowed(url, allowed):
        raise Refused("not an allowlisted HTTPS URL; no scheme or host substitution is attempted")
    if not _robots_allows(url, allowed, handlers, {} if robots is None else robots):
        raise Refused("robots.txt disallows this URL")
    redirects = _Redirects(allowed)
    opener = urllib.request.build_opener(*handlers, redirects)
    retrieved = utc_now()
    part = None
    try:
        with opener.open(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
            final = response.geturl()
            if not host_allowed(final, allowed):
                raise Refused(f"resolved outside the HTTPS allowlist: {final}")
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > max_bytes:
                raise Refused(f"declared size {declared} exceeds max_bytes")
            name = _filename(url, response.headers)
            target = out_dir / name
            part = target.with_name(name + ".part")
            digest, size = hashlib.sha256(), 0
            with part.open("wb") as handle:
                while chunk := response.read(CHUNK):
                    size += len(chunk)
                    if size > max_bytes:
                        raise Refused("download exceeds max_bytes")
                    digest.update(chunk)
                    handle.write(chunk)
            if not size:
                raise Refused("empty response body")
            status = getattr(response, "status", None)
            mime = response.headers.get_content_type()
            http = {key: response.headers.get(key, "") for key in ("Content-Type", "Content-Length", "ETag", "Last-Modified")}
        part.replace(target)
    finally:
        if part is not None and part.exists():
            part.unlink()
    sha = digest.hexdigest()
    recorded = {h.get("recorded_sha256") for h in hints if h.get("recorded_sha256")}
    package = {
        "submission_id": f"rebuild-{hashlib.sha256((url + sha).encode()).hexdigest()[:16]}",
        "producer_id": PRODUCER, "retrieved_at": retrieved,
        "requested_source_uri": url, "resolved_source_uri": final,
        "source_filename": name, "mime_type": mime, "source_sha256": sha, "source_bytes": size,
        "http_metadata": {"status": status, "final_url": final, **http},
        "redirect_chain": redirects.chain,
        "approval_state": "quarantined_unreviewed",
        "rebuild_hints": hints,
        "matches_recorded_bytes": (sha in recorded) if recorded else None,
        "producer_notes": "Hints come from the prior manifest and are leads, not identity evidence. "
                          "Review identity, taxonomy, lifecycle and extraction before intake.",
    }
    write_json(target.with_name(name + ".intake.json"), package)
    return package


def targets_from(census: Path | None = None, urls: Path | None = None,
                 collections: list[str] | None = None, limit: int | None = None) -> list[dict]:
    rows = []
    if census is not None:
        for doc in read_json(census)["documents"]:
            if doc.get("route") == "reacquire_from_official_url" and doc.get("official_url"):
                if not collections or doc.get("collection_id") in collections:
                    hint = {k: doc.get(k) for k in ("document_id", "collection_id", "current_status", "recorded_sha256")}
                    rows.append((doc["official_url"].strip(), hint))
    if urls is not None:
        for line in Path(urls).read_text(encoding="utf-8-sig").splitlines():
            if line.strip() and not line.lstrip().startswith("#"):
                rows.append((line.strip(), {}))
    merged: dict[str, list[dict]] = {}
    for url, hint in rows:
        merged.setdefault(url, [])
        if hint:
            merged[url].append(hint)
    targets = [{"url": url, "hints": hints} for url, hints in merged.items()]
    return targets[:limit] if limit else targets


def acquire(targets: list[dict], out_dir: Path, settings: dict, handlers=(), sleep=time.sleep) -> dict:
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    allowed = [d.casefold().strip(".") for d in settings.get("allowed_domains", [])]
    if not allowed:
        raise ValueError("acquisition.allowed_domains must list official domains")
    max_bytes, delay = int(settings.get("max_bytes", 250 * 2**20)), float(settings.get("delay_seconds", 1.0))
    present = {}
    for path in out_dir.glob("*.intake.json"):
        try:
            package = read_json(path)
            source = out_dir / package["source_filename"]
            if source.is_file() and sha256_file(source) == package["source_sha256"]:
                present[package["requested_source_uri"]] = package
        except (OSError, KeyError, ValueError, json.JSONDecodeError):
            continue  # a damaged package is simply refetched
    robots, results, touched_network = {}, [], False
    for target in targets:
        url, row = target["url"], {"url": target["url"], "hints": target["hints"]}
        if url in present:
            row.update(status="already_present", source_filename=present[url]["source_filename"])
        else:
            if touched_network and delay:
                sleep(delay)
            touched_network = True
            try:
                package = fetch(url, out_dir, allowed, max_bytes, target["hints"], handlers, robots)
                row.update(status="downloaded", source_filename=package["source_filename"],
                           mime_type=package["mime_type"], matches_recorded_bytes=package["matches_recorded_bytes"])
            except Refused as exc:
                row.update(status="refused", reason=str(exc))
            except (urllib.error.URLError, OSError, ValueError) as exc:
                row.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        results.append(row)
    counts = {s: sum(r["status"] == s for r in results) for s in ("downloaded", "already_present", "refused", "failed")}
    report = {
        "schema_version": "1.0", "generated_utc": utc_now(), "producer_id": PRODUCER,
        "requested": len(targets), "counts": counts,
        "complete": counts["refused"] == 0 and counts["failed"] == 0,
        "changed_since_recorded": sum(r.get("matches_recorded_bytes") is False for r in results),
        "note": "Incomplete acquisition is a gap to report, not a smaller library to call complete.",
        "results": results,
    }
    write_json(out_dir / "acquisition_report.json", report)
    return report
