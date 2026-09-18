"""Section extraction is a publication gate, tested with synthetic directives."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from fixtures import make_recipe_dir, REVIEW
from library_rebuilder.build import build, BuildRefused
from library_rebuilder.common import read_json, sha256_file, write_json
from library_rebuilder.recipe import build_recipe
from library_rebuilder.directive_splits import DIRECTIVE_DOC_IDS, SPLIT_FOLDERS
from library_rebuilder.release_contract import approved_release

HEADINGS = {
    'SEAD-3': ['A. AUTHORITY', 'F. REPORTABLE ACTIVITIES FOR ALL COVERED INDIVIDUALS',
        'G. REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO SECRET',
        'H. REPORTABLE ACTIVITIES FOR INDIVIDUALS WITH ACCESS TO TOP SECRET',
        'I. RESPONSIBILITIES', 'APPENDIX A'],
    'SEAD-4': ['A. AUTHORITY', 'APPENDIX A', *[f'GUIDELINE {x}: synthetic heading' for x in 'ABCDEFGHIJKLM'], 'APPENDIX B', 'APPENDIX C'],
    'ISL-2021-02': ['CLARIFICATION AND GUIDANCE ON REPORTABLE ACTIVITIES', 'TABLE 1:', 'TABLE 2:', 'TABLE 3:', 'TABLE 4:'],
}


def add_directives(directory):
    plan = read_json(directory / 'intake_plan.json')
    for name, headings in HEADINGS.items():
        source = directory / f'{name}.pdf'
        source.write_bytes(b'%PDF-synthetic-' + name.encode())
        robot = directory / f'{name}.txt'
        robot.write_text('\n\n'.join(h + f'\nSynthetic section {i} evidence for {name}.' for i,h in enumerate(headings)), encoding='utf-8')
        write_json(directory / f'{name}.intake.json', dict(approval_state='quarantined_unreviewed',
            requested_source_uri=f'https://example.gov/{name}.pdf', resolved_source_uri=f'https://example.gov/{name}.pdf',
            retrieved_at='2026-09-16T00:00:00Z', mime_type='application/pdf', source_filename=source.name,
            source_sha256=sha256_file(source), source_bytes=source.stat().st_size))
        record = dict(document_id=DIRECTIVE_DOC_IDS[name], collection_id='sead' if name.startswith('SEAD') else 'isl_current',
            domain='personnel_vetting', authority_tier=1 if name.startswith('SEAD') else 3, current_status='current',
            human_source_path=f'HUMAN_READABLE_DIRECTORY/DIRECTIVES/{name}.pdf',
            robot_text_path=f'ROBOT_READABLE_DIRECTORY/TEXT/DIRECTIVES/{name}.txt')
        plan['items'].append(dict(package=f'{name}.intake.json', robot_file=robot.name,
            robot_sha256=sha256_file(robot), record=record, review=REVIEW))
    write_json(directory / 'intake_plan.json', plan)
    return directory


class DirectiveBuildTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.directory = add_directives(make_recipe_dir(self.root/'recipe', doc_ids=['cfr-117']))
        self.dest = self.root/'library'

    def test_split_sections_preserve_source_and_are_bound_to_publication(self):
        build(build_recipe(self.directory, 'directive-test', 'Synthetic reviewed directives'), self.dest)
        approved_release(self.dest, check_integrity=True)
        for name, folder in SPLIT_FOLDERS.items():
            manifest = read_json(self.dest/folder/'manifest.json')
            self.assertEqual(manifest['generated_by'], 'dcsa-library-rebuilder')
            self.assertEqual(len(manifest['sections']), len(HEADINGS[name]))
            bodies = [(self.dest/folder/s['file']).read_text(encoding='utf-8').split('---\n\n',1)[1].strip()
                      for s in manifest['sections']]
            self.assertEqual('\n\n'.join(bodies), (self.directory/f'{name}.txt').read_text(encoding='utf-8'))
        target = self.dest/SPLIT_FOLDERS['SEAD-4']/'02_Appendix_A_Introduction_and_Adjudicative_Process.md'
        target.write_text('Changed section')
        with self.assertRaisesRegex(ValueError, 'metadata hash mismatch'):
            approved_release(self.dest)

    def test_historical_directive_cannot_be_published_as_current_sections(self):
        plan = read_json(self.directory/'intake_plan.json')
        for item in plan['items']:
            if item['record']['document_id'] == DIRECTIVE_DOC_IDS['SEAD-3']:
                item['record']['current_status'] = 'historical'
        write_json(self.directory/'intake_plan.json', plan)
        with self.assertRaisesRegex(BuildRefused, 'not current and answer-eligible'):
            build(build_recipe(self.directory, 'directive-test', 'Synthetic historical directive'), self.dest)
        self.assertFalse(self.dest.exists())

    def test_broken_present_directive_blocks_publication(self):
        robot = self.directory/'SEAD-4.txt'
        robot.write_text(robot.read_text(encoding='utf-8').replace('GUIDELINE F:', 'MISSING F:'), encoding='utf-8')
        plan = read_json(self.directory/'intake_plan.json')
        for item in plan['items']:
            if item['robot_file'] == 'SEAD-4.txt':
                item['robot_sha256'] = sha256_file(robot)
        write_json(self.directory/'intake_plan.json', plan)
        with self.assertRaisesRegex(BuildRefused, 'Directive splitting failed'):
            build(build_recipe(self.directory, 'directive-test', 'Synthetic broken directive'), self.dest)
        self.assertFalse(self.dest.exists())
