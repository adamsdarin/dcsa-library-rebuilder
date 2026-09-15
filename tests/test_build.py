import contextlib
import io
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import POSITIVE_CASE, make_recipe_dir  # noqa: E402
from library_rebuilder.build import BuildRefused, build  # noqa: E402
from library_rebuilder.cli import main  # noqa: E402
from library_rebuilder.common import write_json  # noqa: E402
from library_rebuilder.engine import run, verify  # noqa: E402
from library_rebuilder.notice import MAINTENANCE_MODE, NOTICE  # noqa: E402
from library_rebuilder.recipe import build_recipe  # noqa: E402
from library_rebuilder.release_contract import POINTER, STATE, approved_release  # noqa: E402


def corpus_rows(library: Path, index_name: str):
    state = json.loads((library / STATE).read_text())
    path = next(i["production_path"] for i in state["approved_indexes"] if i["production_path"].endswith(index_name))
    with contextlib.closing(sqlite3.connect((library / path).as_uri() + "?mode=ro", uri=True)) as conn:
        return conn.execute("SELECT document_id, authority_role, answer_eligibility FROM corpus").fetchall()


class BuildTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.dest = self.root / "rebuilt"

    def tearDown(self):
        self._tmp.cleanup()

    def recipe(self, release_id="standalone-1", **kwargs):
        return build_recipe(make_recipe_dir(self.root / f"recipe-{release_id}", **kwargs), release_id, "Synthetic CFR, VOI and ISL scope")

    def test_publishes_contract_valid_library_without_archivist(self):
        result = build(self.recipe(), self.dest)
        self.assertEqual(result["status"], "published", result)
        self.assertNotIn("dcsa_custodian", " ".join(sys.modules))
        health = approved_release(self.dest, check_integrity=True)
        self.assertEqual(health["release_id"], "standalone-1")
        self.assertEqual(result["answer_eligibility_counts"],
                         {"answer_eligible": 2, "historical_only": 1, "excluded_duplicate": 1})
        checked = verify(self.dest, "standalone-1")
        self.assertTrue(checked["ok"], checked)
        self.assertEqual(checked["maintenance_mode"], MAINTENANCE_MODE)
        self.assertEqual(checked["warning"], NOTICE)
        self.assertFalse(list(self.root.glob(".rebuilt.*")), "staging, failed or lock files left behind")

    def test_authority_routing_matches_archivist_rules(self):
        build(self.recipe(), self.dest)
        controlling = corpus_rows(self.dest, "DCSA_CONTROLLING_AUTHORITY_CHUNKS_FTS.sqlite")
        self.assertTrue(controlling)
        self.assertEqual({r[0] for r in controlling}, {"cfr-117"})
        self.assertEqual({r[0] for r in corpus_rows(self.dest, "DCSA_CONTEXT_CHUNKS_FTS.sqlite")}, {"voi-2026-01"})
        self.assertEqual({r[0] for r in corpus_rows(self.dest, "DCSA_HISTORICAL_RESEARCH_CHUNKS_FTS.sqlite")}, {"isl-2011-02"})
        everywhere = [row[0] for name in ("CONTROLLING_AUTHORITY", "GOVERNMENT_ISSUANCE", "CURRENT_GUIDANCE", "CONTEXT",
                                          "UNRESOLVED_RESEARCH", "HISTORICAL_RESEARCH")
                      for row in corpus_rows(self.dest, f"DCSA_{name}_CHUNKS_FTS.sqlite")]
        self.assertNotIn("cfr-117-copy", everywhere)

    def test_question_bot_style_query_returns_citable_chunk(self):
        build(self.recipe(), self.dest)
        state = json.loads((self.dest / STATE).read_text())
        path = next(i["production_path"] for i in state["approved_indexes"] if "contractor_or_fso_obligation" in i["allowed_intents"])
        with contextlib.closing(sqlite3.connect((self.dest / path).as_uri() + "?mode=ro", uri=True)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(corpus)")}
            row = conn.execute("SELECT chunk_id, locator, human_source_path, content FROM corpus WHERE corpus MATCH ?",
                               ('"insider" AND "official"',)).fetchone()
        self.assertTrue({"document_id", "collection_id", "domain", "current_status", "human_source_path",
                         "robot_text_path", "content", "chunk_id", "answer_eligibility"} <= columns)
        self.assertTrue(row[0].startswith("cfr-117:"))
        self.assertEqual(row[1].split(";")[0], "page:2")
        enriched = self.dest / "ROBOT_READABLE_DIRECTORY/MANIFESTS/DOCUMENTS_ENRICHED.jsonl"
        tiers = {json.loads(line)["document_id"]: json.loads(line)["authority_tier"] for line in enriched.read_text().splitlines()}
        self.assertEqual(tiers["cfr-117"], 1)

    def test_maintenance_notice_is_carried_by_the_library(self):
        build(self.recipe(), self.dest)
        state = json.loads((self.dest / STATE).read_text())
        entry = json.loads((self.dest / "START_HERE_FOR_ROBOTS.json").read_text())
        self.assertEqual(state["maintenance_mode"], MAINTENANCE_MODE)
        self.assertEqual(entry["maintenance_notice"], NOTICE)
        self.assertEqual(json.loads((self.dest / POINTER).read_text())["maintenance_mode"], MAINTENANCE_MODE)
        self.assertIn(NOTICE, (self.dest / "AGENTS.md").read_text())
        for name in ("MAINTENANCE_NOTICE.md", "START_HERE_FOR_HUMANS.md"):
            text = (self.dest / name).read_text()
            self.assertIn("WILL NOT BE MAINTAINED AUTONOMOUSLY", text)
            self.assertIn("No source discovery", text)

    def test_retry_of_same_recipe_verifies_and_different_recipe_is_refused(self):
        recipe = self.recipe()
        build(recipe, self.dest)
        again = build(recipe, self.dest)
        self.assertEqual(again["status"], "already_published")
        with self.assertRaisesRegex(ValueError, "different rebuild"):
            build(self.recipe(release_id="standalone-2"), self.dest)

    def test_failed_evaluation_refuses_and_never_touches_destination(self):
        case = dict(POSITIVE_CASE, expected_passages=["a passage that does not exist"])
        with self.assertRaisesRegex(BuildRefused, "retrieval evaluation failed"):
            build(self.recipe(cases=[case]), self.dest)
        self.assertFalse(self.dest.exists())
        failed = list(self.root.glob(".rebuilt.failed-*"))
        self.assertEqual(len(failed), 1)
        self.assertTrue((failed[0] / ".rebuilder/reports/RETRIEVAL_EVALUATION.json").is_file())
        self.assertFalse(list(self.root.glob(".rebuilt.rebuild.lock")))

    def test_scope_without_controlling_authority_is_blocked(self):
        case = {"id": "voi", "query": "insider threat awareness", "require_hit": True, "require_locator": True,
                "expected_document_ids": ["voi-2026-01"], "intent": "training_or_context"}
        with self.assertRaisesRegex(BuildRefused, "controlling"):
            build(self.recipe(doc_ids=["voi-2026-01"], cases=[case]), self.dest)
        self.assertFalse(self.dest.exists())

    def test_nonempty_destination_is_never_replaced(self):
        self.dest.mkdir()
        (self.dest / "existing.txt").write_text("keep me")
        with self.assertRaisesRegex(ValueError, "not empty"):
            build(self.recipe(), self.dest)
        self.assertEqual((self.dest / "existing.txt").read_text(), "keep me")

    def test_semantic_evaluation_is_rejected_up_front(self):
        with self.assertRaisesRegex(ValueError, "lexical"):
            self.recipe(cases=[dict(POSITIVE_CASE, retrieval_mode="semantic")])

    def test_run_writes_ledger(self):
        library = self.root / "canonical"
        library.mkdir()
        entry = run({"protected_libraries": [str(library)]}, self.recipe(), self.dest, self.root / "runs")
        self.assertTrue(entry["ok"], entry)
        self.assertEqual(entry["status"], "published")
        self.assertEqual(entry["maintenance_mode"], MAINTENANCE_MODE)
        self.assertEqual(len(list((self.root / "runs").glob("*.json"))), 1)

    def test_every_cli_command_highlights_the_notice(self):
        build(self.recipe(), self.dest)
        config = self.root / "rebuilder.json"
        write_json(config, {"protected_libraries": [str(self.root / "canonical")]})
        for argv in (["verify", "--destination", str(self.dest)],
                     ["preflight", "--destination", str(self.root / "elsewhere")],
                     ["census", "--library", str(self.dest), "--out", str(self.root / "census.json")]):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(["--config", str(config), *argv])
            self.assertEqual(code, 0, (argv, out.getvalue()))
            self.assertIn("WILL NOT BE MAINTAINED AUTONOMOUSLY", err.getvalue(), argv)
            self.assertEqual(json.loads(out.getvalue())["maintenance_mode"], MAINTENANCE_MODE, argv)


if __name__ == "__main__":
    unittest.main()
