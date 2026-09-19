import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import POSITIVE_CASE, make_recipe_dir  # noqa: E402
from library_rebuilder.build import MARKER  # noqa: E402
from library_rebuilder.census import census, route  # noqa: E402
from library_rebuilder.common import read_json, sha256_file, write_json  # noqa: E402
from library_rebuilder.engine import load_config, preflight, run, verify  # noqa: E402
from library_rebuilder.recipe import build_recipe  # noqa: E402


class Workspace(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def config(self):
        library = self.root / "library"
        library.mkdir(exist_ok=True)
        (library / "START_HERE_FOR_ROBOTS.json").write_text("{}")
        return {"protected_libraries": [str(library.resolve())]}

    def recipe_dir(self, **kwargs):
        return make_recipe_dir(self.root / "recipe", doc_ids=["cfr-117"], **kwargs)


class CensusTests(Workspace):
    def test_routes(self):
        self.assertEqual(route({"collection_id": "doha_decisions", "source_url": "x"}), "reacquire_from_official_url")
        self.assertEqual(route({"duplicate_of": "a", "source_url": "x"}), "duplicate_skip")
        self.assertEqual(route({"source_exists": False, "source_url": "x"}), "source_missing")
        self.assertEqual(route({"canonical_source_url": "x"}), "reacquire_from_official_url")
        self.assertEqual(route({"source_exists": True}), "retained_bytes_only")

    def test_census_is_read_only_and_counts(self):
        manifest = self.root / "lib/ROBOT_READABLE_DIRECTORY/MANIFESTS/documents.jsonl"
        manifest.parent.mkdir(parents=True)
        rows = [{"document_id": "a", "collection_id": "cfr", "source_url": "https://example.gov/a.pdf", "source_sha256": "ab" * 32},
                {"document_id": "b", "collection_id": "cfr"},
                {"document_id": "c", "collection_id": "doha_decisions"}]
        manifest.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        before = sha256_file(manifest)
        report = census(self.root / "lib")
        self.assertEqual(sha256_file(manifest), before)
        self.assertEqual(report["total_documents"], 3)
        self.assertEqual(report["by_route"]["reacquire_from_official_url"], 1)
        self.assertEqual(report["by_route"]["retained_bytes_only"], 2)
        self.assertTrue(report["documents"][2]["requires_case_metadata_review"])
        self.assertEqual(report["documents"][0]["recorded_sha256"], "ab" * 32)
        self.assertIsNone(report["source_release_id"])


    def test_census_uses_only_byte_verified_published_provenance(self):
        manifests = self.root / "lib/ROBOT_READABLE_DIRECTORY/MANIFESTS"
        manifests.mkdir(parents=True)
        rows = [{"document_id": "b", "collection_id": "cfr"}, {"document_id": "d", "collection_id": "cfr"}]
        (manifests / "documents.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        enriched = [
            {"document_id": "b", "source_document_id": "b", "source_url": "https://example.gov/b.pdf",
             "source_url_basis": "reacquired_bytes_identical", "human_artifact_sha256": "cd" * 32},
            # a URL without the byte-match basis is not provenance
            {"document_id": "d", "source_document_id": "d", "source_url": "https://example.gov/d.pdf"},
        ]
        (manifests / "DOCUMENTS_ENRICHED.jsonl").write_text("\n".join(json.dumps(r) for r in enriched) + "\n")
        report = census(self.root / "lib")
        self.assertEqual(report["provenance_recovered"], 1)
        self.assertEqual(report["documents"][0]["route"], "reacquire_from_official_url")
        self.assertEqual(report["documents"][0]["recorded_sha256"], "cd" * 32)
        self.assertEqual(report["documents"][1]["route"], "retained_bytes_only")

class RecipeTests(Workspace):
    def test_builds_hash_bound_recipe(self):
        directory = self.recipe_dir()
        recipe = read_json(build_recipe(directory, "rebuild-1", "CFR test scope"))
        self.assertEqual(recipe["required_document_ids"], ["cfr-117"])
        self.assertEqual(recipe["intake_plan"]["sha256"], sha256_file(directory / "intake_plan.json"))

    def test_rejects_negative_only_evaluations(self):
        directory = self.recipe_dir(cases=[{"id": "x", "query": "insider threat", "require_hit": False}])
        with self.assertRaisesRegex(ValueError, "positive"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_unidentified_cases(self):
        directory = self.recipe_dir(cases=[dict(POSITIVE_CASE, id=""), POSITIVE_CASE])
        with self.assertRaisesRegex(ValueError, "uniquely identified"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_doha(self):
        directory = self.recipe_dir()
        plan = read_json(directory / "intake_plan.json")
        plan["items"][0]["record"]["collection_id"] = "doha_decisions"
        write_json(directory / "intake_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "DOHA"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_library_path_outside_directories(self):
        directory = self.recipe_dir()
        plan = read_json(directory / "intake_plan.json")
        plan["items"][0]["record"]["human_source_path"] = "OPERATIONS/cfr.pdf"
        write_json(directory / "intake_plan.json", plan)
        with self.assertRaisesRegex(ValueError, "HUMAN_READABLE_DIRECTORY"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_tampered_extraction(self):
        directory = self.recipe_dir()
        (directory / "cfr-117.txt").write_text("changed after review")
        with self.assertRaisesRegex(ValueError, "robot_sha256"):
            build_recipe(directory, "rebuild-1", "scope")

    def test_rejects_path_escape(self):
        directory = self.recipe_dir()
        with self.assertRaisesRegex(ValueError, "inside"):
            build_recipe(directory, "rebuild-1", "scope", intake_plan="../intake_plan.json")


class EngineTests(Workspace):
    def test_config_needs_no_sibling_repositories(self):
        repo = self.root / "repo"
        write_json(repo / "config/rebuilder.json", {"protected_libraries": ["../library"]})
        config = load_config(repo / "config/rebuilder.json", repo)
        self.assertEqual(Path(config["protected_libraries"][0]), (self.root / "library").resolve())
        write_json(repo / "config/example.json", {"protected_libraries": ["<absolute path>"]})
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
        (self.root / ".fresh.rebuild.lock").write_text("4242")
        self.assertIn("4242", " ".join(preflight(config, self.root / "fresh")["errors"]))

    def test_allows_retry_of_earlier_rebuild_destination(self):
        dest = self.root / "retry"
        write_json(dest / MARKER, {})
        self.assertTrue(preflight(self.config(), dest)["ok"])

    def test_run_never_builds_when_preflight_fails(self):
        config = self.config()
        recipe = build_recipe(self.recipe_dir(), "rebuild-1", "scope")
        entry = run(config, recipe, Path(config["protected_libraries"][0]), self.root / "runs")
        self.assertFalse(entry["ok"])
        self.assertEqual(entry["status"], "preflight_failed")
        self.assertNotIn("result", entry)

    def test_verify_fails_closed_on_unpublished_destination(self):
        (self.root / "empty").mkdir()
        result = verify(self.root / "empty", "rebuild-1")
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"])


if __name__ == "__main__":
    unittest.main()
