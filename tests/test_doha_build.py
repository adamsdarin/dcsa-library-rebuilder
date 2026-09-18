"""Standalone reviewed-case reconstruction through the actual publication gate."""
from contextlib import closing
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_recipe_dir, REVIEW
from library_rebuilder.build import build
from library_rebuilder.common import read_json, sha256_file, write_json
from library_rebuilder.doha import CONTENT, MANIFEST
from library_rebuilder.recipe import build_recipe
from library_rebuilder.release_contract import approved_release, readiness


def add_cases(directory):
    plan = read_json(directory / 'intake_plan.json')
    plan['doha_taxonomy'] = {'schema_version': '1.0', 'guidelines': {'F': {'aliases': ['financial considerations']}}}
    for identity, level, group, eligible in [('hearing', 'h1', 'POST_SEAD_4', True),
            ('appeal', 'a1', 'POST_SEAD_4', False), ('old', 'h1', 'PRE_SEAD_4', False)]:
        source = directory / f'{identity}.pdf'
        source.write_bytes(b'%PDF-synthetic-' + identity.encode())
        robot = directory / f'{identity}.txt'
        robot.write_text(f'Synthetic {identity} financial considerations evidence.', encoding='utf-8')
        write_json(directory / f'{identity}.intake.json', dict(approval_state='quarantined_unreviewed',
            requested_source_uri=f'https://example.gov/{identity}.pdf', resolved_source_uri=f'https://example.gov/{identity}.pdf',
            retrieved_at='2026-09-16T00:00:00Z', mime_type='application/pdf', source_filename=source.name,
            source_sha256=sha256_file(source), source_bytes=source.stat().st_size))
        record = dict(document_id=identity, collection_id='doha_decisions', domain='personnel_vetting', authority_tier=5,
            current_status='historical_case_research', human_source_path=f'HUMAN_READABLE_DIRECTORY/DOHA/{identity}.pdf',
            robot_text_path=f'ROBOT_READABLE_DIRECTORY/TEXT/DOHA/{identity}.txt',
            doha_review=dict(case_id='26-12345' if identity!='old' else '10-1234', decision_level=level,
                decision_date='2026-08-01' if identity!='old' else '2010-08-01', current_group=group,
                outcome='approved', guidelines=['F'], answer_eligible=eligible, reviewed_by='synthetic reviewer',
                reviewed_utc='2026-09-16T00:00:00Z', metadata_basis='Reviewed synthetic test metadata'))
        plan['items'].append(dict(package=f'{identity}.intake.json', robot_file=robot.name,
            robot_sha256=sha256_file(robot), record=record, review=REVIEW))
    write_json(directory / 'intake_plan.json', plan)
    return directory


class DohaBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = add_cases(make_recipe_dir(self.root / 'recipe', doc_ids=['cfr-117']))
        self.dest = self.root / 'library'

    def test_cases_publish_with_default_filters_and_metadata_hashes(self):
        recipe = build_recipe(self.directory, 'doha-test', 'Synthetic regulation and reviewed precedent cases')
        result = build(recipe, self.dest)
        self.assertEqual(result['status'], 'published')
        health = readiness(self.dest, check_integrity=True)
        self.assertTrue(health['ready'], health)
        self.assertTrue(health['capabilities']['doha_search'])
        with closing(sqlite3.connect(self.dest / CONTENT)) as db:
            hits = db.execute("SELECT d.document_id FROM corpus c JOIN decisions d ON d.document_id=c.document_id WHERE d.answer_eligible=1 AND d.current_group='POST_SEAD_4' AND d.decision_family='hearing' AND c.content MATCH 'financial'").fetchall()
        self.assertEqual(hits, [('hearing',)])
        (self.dest / MANIFEST).write_text('{}\n')
        with self.assertRaisesRegex(ValueError, 'metadata hash mismatch'):
            approved_release(self.dest, check_integrity=True)

    def test_index_tampering_fails_published_verification(self):
        recipe = build_recipe(self.directory, 'doha-test', 'Synthetic reviewed cases')
        build(recipe, self.dest)
        with closing(sqlite3.connect(self.dest / CONTENT)) as db, db:
            db.execute("UPDATE decisions SET answer_eligible=1 WHERE document_id='appeal'")
        with self.assertRaisesRegex(ValueError, 'DOHA index hash mismatch'):
            approved_release(self.dest, check_integrity=True)

    def test_unreviewed_case_metadata_never_creates_destination(self):
        plan = read_json(self.directory / 'intake_plan.json')
        plan['items'][-1]['record'].pop('doha_review')
        write_json(self.directory / 'intake_plan.json', plan)
        with self.assertRaisesRegex(ValueError, 'doha_review'):
            build_recipe(self.directory, 'doha-test', 'Synthetic reviewed cases')
        self.assertFalse(self.dest.exists())


if __name__ == '__main__':
    unittest.main()
