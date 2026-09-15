import email.message
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.request
import urllib.response

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from library_rebuilder.acquire import acquire, targets_from  # noqa: E402
from library_rebuilder.cli import main  # noqa: E402
from library_rebuilder.common import sha256_file, write_json  # noqa: E402
from library_rebuilder.recipe import build_recipe  # noqa: E402

PDF = b"%PDF-1.7 synthetic official source"
SETTINGS = {"allowed_domains": ["gov", "mil"], "max_bytes": 1024, "delay_seconds": 0}


class FakeWeb(urllib.request.HTTPSHandler):
    """In-memory HTTPS responses; replaces the real handler so tests never touch the network."""

    def __init__(self, routes):
        super().__init__()
        self.routes, self.requests = routes, []

    def https_open(self, req):
        self.requests.append(req.full_url)
        status, headers, body = self.routes.get(req.full_url, (404, {}, b""))
        message = email.message.Message()
        for key, value in headers.items():
            message[key] = value
        response = urllib.response.addinfourl(io.BytesIO(body), message, req.full_url, status)
        response.msg = "OK" if status < 400 else "Error"
        return response


def pdf(body=PDF):
    return (200, {"Content-Type": "application/pdf", "Content-Length": str(len(body))}, body)


class AcquireTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.out = self.root / "recipe" / "sources"

    def tearDown(self):
        self._tmp.cleanup()

    def run_acquire(self, routes, targets):
        web = FakeWeb(routes)
        return acquire(targets, self.out, SETTINGS, handlers=(web,), sleep=lambda _: None), web

    def test_download_writes_archivist_package_with_redirect_provenance(self):
        recorded = hashlib.sha256(PDF).hexdigest()
        routes = {"https://www.example.gov/old.pdf": (302, {"Location": "/files/new.pdf"}, b""),
                  "https://www.example.gov/files/new.pdf": pdf()}
        report, _ = self.run_acquire(routes, [{"url": "https://www.example.gov/old.pdf",
                                               "hints": [{"document_id": "doc-1", "recorded_sha256": recorded}]}])
        self.assertTrue(report["complete"], report)
        package = json.loads(next(self.out.glob("*.intake.json")).read_text())
        self.assertEqual(package["approval_state"], "quarantined_unreviewed")
        self.assertEqual(package["producer_id"], "dcsa-library-rebuilder")
        self.assertEqual(package["resolved_source_uri"], "https://www.example.gov/files/new.pdf")
        self.assertEqual(package["redirect_chain"][0]["status"], 302)
        self.assertEqual(package["mime_type"], "application/pdf")
        self.assertEqual(package["source_bytes"], len(PDF))
        self.assertEqual(sha256_file(self.out / package["source_filename"]), package["source_sha256"])
        self.assertTrue(package["matches_recorded_bytes"])

    def test_changed_source_is_flagged_not_hidden(self):
        report, _ = self.run_acquire({"https://www.example.gov/a.pdf": pdf()},
                                     [{"url": "https://www.example.gov/a.pdf", "hints": [{"recorded_sha256": "0" * 64}]}])
        self.assertEqual(report["changed_since_recorded"], 1)

    def test_refuses_http_and_unlisted_hosts_without_requesting(self):
        report, web = self.run_acquire({}, [{"url": "http://www.example.gov/a.pdf", "hints": []},
                                            {"url": "https://example.com/a.pdf", "hints": []}])
        self.assertEqual(report["counts"]["refused"], 2)
        self.assertFalse(report["complete"])
        self.assertEqual(web.requests, [])

    def test_refuses_redirect_off_allowlist_and_leaves_no_file(self):
        routes = {"https://www.example.gov/a.pdf": (301, {"Location": "https://mirror.example.com/a.pdf"}, b"")}
        report, _ = self.run_acquire(routes, [{"url": "https://www.example.gov/a.pdf", "hints": []}])
        self.assertIn("allowlist", report["results"][0]["reason"])
        self.assertEqual([p.name for p in self.out.iterdir()], ["acquisition_report.json"])

    def test_robots_disallow_and_server_error_both_refuse(self):
        routes = {"https://www.example.gov/robots.txt": (200, {}, b"User-agent: *\nDisallow: /private/\n"),
                  "https://down.example.mil/robots.txt": (503, {}, b"")}
        report, web = self.run_acquire(routes, [{"url": "https://www.example.gov/private/a.pdf", "hints": []},
                                                {"url": "https://down.example.mil/a.pdf", "hints": []}])
        self.assertEqual(report["counts"]["refused"], 2)
        self.assertNotIn("https://www.example.gov/private/a.pdf", web.requests)

    def test_oversize_is_refused_and_partial_removed(self):
        big = b"x" * 2048
        report, _ = self.run_acquire({"https://www.example.gov/big.pdf": (200, {}, big)},
                                     [{"url": "https://www.example.gov/big.pdf", "hints": []}])
        self.assertIn("max_bytes", report["results"][0]["reason"])
        self.assertFalse(list(self.out.glob("*.part")))

    def test_missing_source_is_a_failure_gap(self):
        report, _ = self.run_acquire({}, [{"url": "https://www.example.gov/gone.pdf", "hints": []}])
        self.assertEqual(report["counts"]["failed"], 1)
        self.assertFalse(report["complete"])

    def test_retry_reuses_verified_downloads(self):
        routes = {"https://www.example.gov/a.pdf": pdf()}
        target = [{"url": "https://www.example.gov/a.pdf", "hints": []}]
        self.run_acquire(routes, target)
        report, web = self.run_acquire(routes, target)
        self.assertEqual(report["counts"]["already_present"], 1)
        self.assertEqual(web.requests, [])

    def test_targets_from_census_filters_and_merges_shared_urls(self):
        census = self.root / "census.json"
        write_json(census, {"documents": [
            {"document_id": "a", "collection_id": "cfr", "route": "reacquire_from_official_url", "official_url": "https://x.gov/1.pdf"},
            {"document_id": "b", "collection_id": "cfr", "route": "reacquire_from_official_url", "official_url": "https://x.gov/1.pdf"},
            {"document_id": "c", "collection_id": "nist", "route": "reacquire_from_official_url", "official_url": "https://x.gov/2.pdf"},
            {"document_id": "d", "collection_id": "cfr", "route": "retained_bytes_only", "official_url": None}]})
        targets = targets_from(census, collections=["cfr"])
        self.assertEqual(len(targets), 1)
        self.assertEqual([h["document_id"] for h in targets[0]["hints"]], ["a", "b"])

    def test_acquired_package_passes_recipe_checks(self):
        self.run_acquire({"https://www.example.gov/a.pdf": pdf()}, [{"url": "https://www.example.gov/a.pdf", "hints": []}])
        recipe_dir = self.out.parent
        package = next(self.out.glob("*.intake.json"))
        (recipe_dir / "a.txt").write_text("page one text")
        review = {k: "synthetic" for k in ("reviewed_by", "reviewed_utc", "identity", "provenance",
                                           "extraction", "parity", "taxonomy", "lifecycle")}
        write_json(recipe_dir / "intake_plan.json", {"schema_version": "1.0", "items": [{
            "package": f"sources/{package.name}", "robot_file": "a.txt",
            "robot_sha256": sha256_file(recipe_dir / "a.txt"), "review": review,
            "record": {"document_id": "doc-1", "collection_id": "cfr", "domain": "REGULATIONS",
                       "authority_tier": 1, "current_status": "current",
                       "human_source_path": "HUMAN_READABLE_DIRECTORY/REGULATIONS/CFR/a.pdf",
                       "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/REGULATIONS/CFR/a.txt"}}]})
        write_json(recipe_dir / "golden_queries.json", {"cases": [
            {"id": "page-one", "query": "page one text", "require_hit": True, "require_locator": True,
             "expected_document_ids": ["doc-1"]}]})
        recipe = json.loads(build_recipe(recipe_dir, "rebuild-1", "scope").read_text())
        self.assertEqual(recipe["required_document_ids"], ["doc-1"])

    def test_cli_refuses_quarantine_inside_protected_library(self):
        library = self.root / "library"
        library.mkdir()
        urls = self.root / "urls.txt"
        urls.write_text("https://www.example.gov/a.pdf\n")
        config = self.root / "rebuilder.json"
        write_json(config, {"protected_libraries": [str(library)],
                            "acquisition": SETTINGS})
        code = main(["--config", str(config), "acquire", "--urls", str(urls), "--out", str(library / "q")])
        self.assertEqual(code, 2)
        self.assertFalse((library / "q").exists())


if __name__ == "__main__":
    unittest.main()
