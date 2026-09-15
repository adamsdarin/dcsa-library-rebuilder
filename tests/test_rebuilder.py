import json
from pathlib import Path
import sys
import tempfile
import textwrap
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from library_rebuilder.census import census, route  # noqa: E402
from library_rebuilder.common import sha256_file, write_json  # noqa: E402
from library_rebuilder.engine import MARKER, load_config, preflight, run, verify  # noqa: E402
from library_rebuilder.recipe import build_recipe  # noqa: E402

REVIEW = {k: "synthetic evidence" for k in ("reviewed_by", "reviewed_utc", "identity", "provenance",
                                              "extraction", "parity", "taxonomy", "lifecycle")}

FAKE_ENGINE = textwrap.dedent('''
    import json, sys
    from pathlib import Path
    args = sys.argv[1:]
    if args[:2] == ["regenerate", "--help"]:
        raise SystemExit(0)
    recipe = json.loads(Path(args[args.index("--recipe") + 1]).read_text())
    dest = Path(args[args.index("--destination") + 1])
    dest.mkdir(parents=True, exist_ok=True)
    print(json.dumps({"status": "published", "release_id": recipe["release_id"], "destination": str(dest)}))
''')


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self, engine=FAKE_ENGINE):
        archivist, library = self.root / "archivist", self.root / "library"
        for path in (archivist, library):
            path.mkdir(exist_ok=True)
        (archivist / "custodian.py").write_text(engine)
        (library / "START_HERE_FOR_ROBOTS.json").write_text("{}")
        return {"archivist_root": str(archivist), "protected_libraries": [str(library.resolve())]}

    def recipe_dir(self, cases=None, collection="cfr"):
        directory = self.root / "recipe"
        directory.mkdir()
        (directory / "source.pdf").write_bytes(b"%PDF synthetic")
        (directory / "source.txt").write_text("page one")
        write_json(directory / "source.pdf.intake.json", {
            "source_filename": "source.pdf", "source_sha256": sha256_file(directory / "source.pdf"),
            "source_bytes": (directory / "source.pdf").stat().st_size, "approval_state": "quarantined_unreviewed",
            "requested_source_uri": "https://example.gov/a.pdf", "resolved_source_uri": "https://example.gov/a.pdf",
            "retrieved_at": "2026-01-01T00:00:00Z", "mime_type": "application/pdf"})
        record = {"document_id": "doc-1", "collection_id": collection, "domain": "REGULATIONS",
                  "authority_tier": 1, "current_status": "current",
                  "human_source_path": "HUMAN_READABLE_DIRECTORY/REGULATIONS/CFR/a.pdf",
                  "robot_text_path": "ROBOT_READABLE_DIRECTORY/TEXT/REGULATIONS/CFR/a.txt"}
        write_json(directory / "intake_plan.json", {"schema_version": "1.0", "items": [{
            "package": "source.pdf.intake.json", "robot_file": "source.txt",
            "robot_sha256": sha256_file(directory / "source.txt"), "record": record, "review": REVIEW}]})
        write_json(directory / "golden_queries.json", {"cases": cases if cases is not None else [
            {"require_hit": True, "require_locator": True, "expected_document_ids": ["doc-1"]}]})
        return directory


class CensusTests(Workspace):
    def test_routes(self):
        self.assertEqual(route({"collection_id": "doha_decisions", "source_url": "x"}), "doha_unsupported")
        self.assertEqual(route({"duplicate_of": "a", "source_url": "x"}), "duplicate_skip")
        self.assertEqual(route({"source_exists": False, "source_url": "x"}), "source_missing")
        self.assertEqual(route({"canonical_source_url": "x"}), "reacquire_from_official_url")
        self.assertEqual(route({"source_exists": True}), "retained_bytes_only")

    def test_census_is_read_only_and_counts(self):
        manifest = self.root / "lib/ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        manifest.parent.mkdir(parents=True)
        rows = [{"document_id": "a", "collection_id": "cfr", "source_url": "https://example.gov/a.pdf"},
                {"document_id": "b", "collection_id": "cfr"},
                {"document_id": "c", "collection_id": "doha_decisions"}]
        manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        before = sha256_file(manifest)
        report = census(self.root / "lib")
        self.assertEqual(sha256_file(manifest), before)
        self.assertEqual(report["total_documents"], 3)
        self.assertEqual(report["by_route"]["reacquire_from_official_url"], 1)
        self.assertEqual(report["by_route"]["retained_bytes_only"], 1)
        self.assertEqual(report["by_route"]["doha_unsupported"], 1)
        self.assertIsNone(report["source_release_id"])


class RecipeTests(Workspace):
    def test_builds_hash_bound_recipe(self):
        directory = self.recipe_dir()
        recipe = json.loads(build_recipe(directory, "rebuild-1", "CFR test scope").read_text())
        self.assertEqual(recipe["required_document_ids"], ["doc-1"])
        self.assertEqual(recipe["intake_plan"]["sha256"], sha256_file(directory / "intake_plan.json"))

    def test_rejects_negative_only_evaluations(self):
        directory = self.recipe_dir(cases=[{"require_hit": False}])
        with self.assertRaisesRegex(ValueError, "positive"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_doha(self):
        with self.assertRaisesRegex(ValueError, "DOHA"):
            build_recipe(self.recipe_dir(collection="doha_decisions"), "rebuild-1", "scope")

    def test_rejects_tampered_extraction(self):
        directory = self.recipe_dir()
        (directory / "source.txt").write_text("changed after review")
        with self.assertRaisesRegex(ValueError, "robot_sha256"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_path_escape(self):
        directory = self.recipe_dir()
        with self.assertRaisesRegex(ValueError, "inside"):
            build_recipe(directory, "rebuild-1", "scope", intake_plan="../intake_plan.json")


class EngineTests(Workspace):
    def test_config_resolves_against_repo_root_and_rejects_placeholder(self):
        repo = self.root / "repo"
        write_json(repo / "config/rebuilder.json", {"archivist_root": "../archivist", "protected_libraries": ["../library"]})
        config = load_config(repo / "config/rebuilder.json", repo)
        self.assertEqual(Path(config["archivist_root"]), (self.root / "archivist").resolve())
        self.assertEqual(Path(config["protected_libraries"][0]), (self.root / "library").resolve())
        write_json(repo / "config/example.json", {"archivist_root": "a", "protected_libraries": ["<absolute path>"]})
        with self.assertRaisesRegex(ValueError, "protected_libraries"):
            load_config(repo / "config/example.json", repo)

    def test_refuses_protected_library_and_its_children(self):
        config = self.config()
        library = Path(config["protected_libraries"][0])
        for target in (library, library / "nested", library.parent):
            self.assertFalse(preflight(config, target)["ok"], target)

    def test_refuses_nonempty_destination_and_held_lock(self):
        config = self.config()
        dest = self.root / "out"
        dest.mkdir()
        (dest / "stray.txt").write_text("x")
        self.assertIn("not empty", " ".join(preflight(config, dest)["errors"]))
        fresh = self.root / "fresh"
        (self.root / ".fresh.regeneration.lock").write_text("4242")
        self.assertIn("4242", " ".join(preflight(config, fresh)["errors"]))

    def test_allows_retry_of_same_recipe_destination(self):
        config = self.config()
        dest = self.root / "retry"
        (dest / MARKER).parent.mkdir(parents=True)
        (dest / MARKER).write_text("{}")
        self.assertTrue(preflight(config, dest)["ok"])

    def test_refuses_engine_without_regenerate(self):
        config = self.config(engine="raise SystemExit(2)\n")
        self.assertIn("regenerate", " ".join(preflight(config, self.root / "out")["errors"]))

    def test_run_invokes_engine_and_writes_ledger(self):
        config = self.config()
        recipe = build_recipe(self.recipe_dir(), "rebuild-1", "scope")
        entry = run(config, recipe, self.root / "out", self.root / "runs")
        self.assertTrue(entry["ok"], entry)
        self.assertEqual(entry["result"]["release_id"], "rebuild-1")
        self.assertEqual(len(list((self.root / "runs").glob("*.json"))), 1)

    def test_run_does_not_invoke_engine_when_preflight_fails(self):
        config = self.config()
        recipe = build_recipe(self.recipe_dir(), "rebuild-1", "scope")
        entry = run(config, recipe, Path(config["protected_libraries"][0]), self.root / "runs")
        self.assertFalse(entry["ok"])
        self.assertIsNone(entry["exit_code"])

    def test_verify_fails_closed_on_unpublished_destination(self):
        (self.root / "empty").mkdir()
        result = verify(self.root / "empty", "rebuild-1")
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
