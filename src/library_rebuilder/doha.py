"""Build dedicated precedent stores from reviewed metadata and exact robot text.

Portable stdlib code. Call only on an isolated candidate, never a live library.
Source identity, era, outcome and topics require review; filenames prove none of them.
"""
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
import re
import sqlite3

from .common import iter_jsonl, read_json, sha256_file, write_json, write_jsonl
from .release_contract import bounded_path

CONTENT = 'LOCAL_INDEXES/DOHA_CASE_TOPICS_FTS.sqlite'
PATHS = 'LOCAL_INDEXES/DOHA_CURRENT_PATHS.sqlite'
MANIFEST = 'ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_CURRENT_PATHS.jsonl'
TAXONOMY = 'ROBOT_READABLE_DIRECTORY/RETRIEVAL/DOHA_TOPIC_TAXONOMY.json'
ROUTER = 'ROBOT_READABLE_DIRECTORY/MANIFESTS/DOHA_SEAD4_SEARCH_ROUTER.json'
ARTIFACTS = (CONTENT, PATHS, MANIFEST, TAXONOMY, ROUTER)

SCHEMA = {
    CONTENT: {
        'decisions': '''CREATE TABLE decisions(document_id TEXT PRIMARY KEY,case_id TEXT,case_year INTEGER,
            decision_level TEXT,decision_family TEXT,level_rank INTEGER,outcome TEXT,guideline_codes TEXT,
            current_group TEXT,retrieval_priority INTEGER,answer_eligible INTEGER,eligibility_reason TEXT,
            human_source_path TEXT,robot_text_path TEXT,canonical_name TEXT,content_sha256 TEXT,content_bytes INTEGER)''',
        'decision_topics': 'CREATE TABLE decision_topics(document_id TEXT,guideline_code TEXT)',
        'corpus': '''CREATE VIRTUAL TABLE corpus USING fts5(document_id UNINDEXED,case_id UNINDEXED,
            guideline_codes UNINDEXED,current_group UNINDEXED,decision_family UNINDEXED,outcome UNINDEXED,
            human_source_path UNINDEXED,robot_text_path UNINDEXED,content)''',
    },
    PATHS: {'current_paths': '''CREATE TABLE current_paths(document_id TEXT PRIMARY KEY,case_stem TEXT,
        current_group TEXT,human_source_path TEXT,robot_text_path TEXT,authority_priority INTEGER)'''},
}
FTS_COLUMNS = ('document_id', 'case_id', 'guideline_codes', 'current_group', 'decision_family',
               'outcome', 'human_source_path', 'robot_text_path')
PATH_COLUMNS = ('document_id', 'case_stem', 'current_group', 'human_source_path', 'robot_text_path', 'authority_priority')


def validate_taxonomy(taxonomy):
    guidelines = taxonomy.get('guidelines') if isinstance(taxonomy, dict) else None
    if not isinstance(guidelines, dict) or not guidelines:
        raise ValueError('DOHA requires a reviewed guideline taxonomy')
    for code, item in guidelines.items():
        aliases = item.get('aliases') if isinstance(item, dict) else None
        if not re.fullmatch('[A-M]', code) or not isinstance(aliases, list) or not aliases:
            raise ValueError('Invalid DOHA guideline or aliases')
        if any(not isinstance(alias, str) or not alias.strip() for alias in aliases):
            raise ValueError('DOHA aliases must be nonempty text')
    return guidelines


def review_metadata(record, taxonomy):
    guidelines = validate_taxonomy(taxonomy)
    meta = record.get('doha_review')
    if not isinstance(meta, dict):
        raise ValueError('DOHA requires attributable doha_review metadata')
    for key in ('case_id', 'decision_level', 'decision_date', 'current_group', 'outcome',
                'reviewed_by', 'reviewed_utc', 'metadata_basis'):
        if not isinstance(meta.get(key), str) or not meta[key].strip():
            raise ValueError(f'DOHA review requires {key}')
    if not re.fullmatch(r'\d{2}-\d{4,5}', meta['case_id']) or not re.fullmatch(r'[ha][1-9]', meta['decision_level']):
        raise ValueError('Invalid reviewed DOHA case identity')
    date.fromisoformat(meta['decision_date'])
    if datetime.fromisoformat(meta['reviewed_utc'].replace('Z', '+00:00')).tzinfo is None:
        raise ValueError('DOHA review timestamp needs a timezone')
    if meta['current_group'] not in ('POST_SEAD_4', 'PRE_SEAD_4', 'UNDETERMINED'):
        raise ValueError('Invalid reviewed DOHA era')
    if meta['outcome'] not in ('approved', 'denied', 'remanded', 'unknown'):
        raise ValueError('Invalid reviewed DOHA outcome')
    topics = meta.get('guidelines')
    if not isinstance(topics, list) or any(not isinstance(t, str) or t not in guidelines for t in topics) or len(set(topics)) != len(topics):
        raise ValueError('DOHA topics must be unique reviewed guideline codes')
    if record.get('current_status') != 'historical_case_research':
        raise ValueError('DOHA retains historical_case_research lifecycle, never current guidance')
    eligible = meta.get('answer_eligible')
    if not isinstance(eligible, bool):
        raise ValueError('DOHA requires explicit boolean answer_eligible')
    if eligible and (meta['current_group'] != 'POST_SEAD_4' or not meta['decision_level'].startswith('h')
                     or meta['outcome'] not in ('approved', 'denied') or not topics):
        raise ValueError('Only tagged post-SEAD-4 approved/denied hearings qualify for default precedent retrieval')
    return meta


def case_row(root, record, taxonomy):
    meta = review_metadata(record, taxonomy)
    robot = bounded_path(root, record['robot_text_path'], 'ROBOT_READABLE_DIRECTORY/TEXT/')
    if not robot.is_relative_to(Path(root).resolve()):
        raise ValueError('DOHA robot path escapes library')
    bounded_path(root, record['human_source_path'], 'HUMAN_READABLE_DIRECTORY/')
    content = robot.read_text(encoding='utf-8')
    if not content.strip() or sha256_file(robot) != record.get('robot_sha256'):
        raise ValueError('DOHA robot hash mismatch or empty extraction')
    topics = sorted(meta['guidelines'])
    stem = f"{meta['case_id']}.{meta['decision_level']}_{meta['outcome']}" + ''.join('_' + t.lower() for t in topics)
    row = dict(document_id=record['document_id'], case_id=meta['case_id'],
        case_year=date.fromisoformat(meta['decision_date']).year, decision_level=meta['decision_level'],
        decision_family='hearing' if meta['decision_level'][0] == 'h' else 'appeal',
        level_rank=int(meta['decision_level'][1:]), outcome=meta['outcome'], guideline_codes=','.join(topics),
        current_group=meta['current_group'], retrieval_priority=0, answer_eligible=int(meta['answer_eligible']),
        eligibility_reason=meta['metadata_basis'], human_source_path=record['human_source_path'],
        robot_text_path=record['robot_text_path'], canonical_name=stem,
        content_sha256=record['robot_sha256'], content_bytes=robot.stat().st_size)
    path = dict(document_id=row['document_id'], case_stem=stem, current_group=meta['current_group'],
        human_source_path=row['human_source_path'], robot_text_path=row['robot_text_path'],
        authority_priority=record['authority_tier'], sead4_era=meta['current_group'],
        answer_eligible=meta['answer_eligible'], decision_date=meta['decision_date'])
    return row, path, content, topics


def initialize_indexes(root):
    for relative, tables in SCHEMA.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(target)) as db, db:
            for name, sql in tables.items():
                exists = db.execute('SELECT 1 FROM sqlite_master WHERE name=?', (name,)).fetchone()
                if exists:
                    with closing(sqlite3.connect(':memory:')) as schema:
                        schema.execute(sql)
                        expected = [r[1] for r in schema.execute(f'PRAGMA table_info({name})')]
                    actual = [r[1] for r in db.execute(f'PRAGMA table_info({name})')]
                    if actual != expected:
                        if db.execute(f'SELECT count(*) FROM {name}').fetchone()[0]:
                            raise ValueError(f'Nonempty DOHA table requires explicit schema migration: {name}')
                        db.execute(f'DROP TABLE {name}')
                        exists = False
                if not exists:
                    db.execute(sql)


def append_cases(root, records, taxonomy):
    """Preserve existing reviewed cases; refuse duplicate IDs and changed taxonomies."""
    root = Path(root).resolve()
    cases = [r for r in records if r.get('collection_id') == 'doha_decisions']
    if not cases:
        return []
    rows = [case_row(root, r, taxonomy) for r in cases]
    ids = [row[0]['document_id'] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate DOHA document IDs')
    if (root / TAXONOMY).exists() and read_json(root / TAXONOMY) != taxonomy:
        raise ValueError('Changing an existing DOHA taxonomy requires a separate reviewed migration')
    existing = [r for _, r in iter_jsonl(root / MANIFEST)] if (root / MANIFEST).exists() else []
    if set(ids) & {r['document_id'] for r in existing}:
        raise ValueError('DOHA intake cannot replace existing case IDs')
    initialize_indexes(root)
    with closing(sqlite3.connect(root / CONTENT)) as db, db, closing(sqlite3.connect(root / PATHS)) as paths, paths:
        for row, path, content, topics in rows:
            columns = ','.join(row)
            db.execute(f"INSERT INTO decisions({columns}) VALUES({','.join('?' for _ in row)})", tuple(row.values()))
            db.executemany('INSERT INTO decision_topics VALUES(?,?)', [(row['document_id'], t) for t in topics])
            db.execute(f"INSERT INTO corpus({','.join(FTS_COLUMNS)},content) VALUES(?,?,?,?,?,?,?,?,?)",
                       tuple(row[k] for k in FTS_COLUMNS) + (content,))
            paths.execute(f"INSERT INTO current_paths({','.join(PATH_COLUMNS)}) VALUES(?,?,?,?,?,?)", tuple(path[k] for k in PATH_COLUMNS))
            existing.append(path)
    write_jsonl(root / MANIFEST, existing)
    write_json(root / TAXONOMY, taxonomy)
    router = read_json(root / ROUTER) if (root / ROUTER).exists() else {}
    router.update(doha_content_index=CONTENT, current_doha_path_index=PATHS,
        case_manifest=MANIFEST, taxonomy=TAXONOMY, coverage='Reviewed cases only; not complete website coverage')
    write_json(root / ROUTER, router)
    return list(ARTIFACTS)


def validate_cases(root, records, taxonomy):
    """Verify every supplied reviewed case against both stores, routing and exact text."""
    root = Path(root).resolve()
    errors = []
    expected = [case_row(root, r, taxonomy) for r in records if r.get('collection_id') == 'doha_decisions']
    manifest = [r for _, r in iter_jsonl(root / MANIFEST)]
    manifest_ids = [r['document_id'] for r in manifest]
    if len(set(manifest_ids)) != len(manifest_ids):
        errors.append('Duplicate DOHA manifest IDs')
    with closing(sqlite3.connect((root / CONTENT).as_uri() + '?mode=ro', uri=True)) as db, closing(sqlite3.connect((root / PATHS).as_uri() + '?mode=ro', uri=True)) as paths:
        db.row_factory = paths.row_factory = sqlite3.Row
        for connection in (db, paths):
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                errors.append('DOHA index integrity failure')
        for connection, table in ((db, 'decisions'), (db, 'corpus'), (paths, 'current_paths')):
            ids = [r[0] for r in connection.execute(f'SELECT document_id FROM {table}')]
            if len(set(ids)) != len(ids) or set(ids) != set(manifest_ids):
                errors.append(f'DOHA {table} coverage mismatch')
        for row, path, content, topics in expected:
            identity = (row['document_id'],)
            actual = db.execute('SELECT * FROM decisions WHERE document_id=?', identity).fetchone()
            if actual is None or any(actual[k] != v for k, v in row.items()):
                errors.append('DOHA reviewed decision metadata mismatch')
            bodies = db.execute('SELECT * FROM corpus WHERE document_id=?', identity).fetchall()
            if len(bodies) != 1 or bodies[0]['content'] != content or any(bodies[0][k] != row[k] for k in FTS_COLUMNS):
                errors.append('DOHA indexed evidence mismatch')
            actual_topics = sorted(r[0] for r in db.execute('SELECT guideline_code FROM decision_topics WHERE document_id=?', identity))
            if actual_topics != topics:
                errors.append('DOHA topic routing mismatch')
            actual_path = paths.execute('SELECT * FROM current_paths WHERE document_id=?', identity).fetchone()
            if actual_path is None or any(actual_path[k] != path[k] for k in PATH_COLUMNS):
                errors.append('DOHA indexed path mismatch')
            matching = [r for r in manifest if r['document_id'] == identity[0]]
            if len(matching) != 1 or any(matching[0].get(k) != v for k, v in path.items()):
                errors.append('DOHA path manifest metadata mismatch')
    return errors
