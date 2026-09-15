# HANDOFF — dcsa-library-rebuilder

Last updated: 2026-09-15T23:00:00Z by Claude

## Current State
Standalone, single-purpose rebuild agent: no runtime dependency on Librarian or
Archivist. Prompt `agents/rebuilder.md`; stdlib CLI `rebuilder.py` with `census`,
`acquire`, `recipe`, `preflight`, `run`, `verify`. `run` stages, enriches, chunks,
indexes (FTS5), validates, evaluates and publishes in a sibling staging folder and
moves the library into place only after `approved_release` passes on it.

Every command prints the "not maintained autonomously" banner (stderr) and returns
`maintenance_mode: standalone_unmaintained`; built libraries carry it in
`MAINTENANCE_NOTICE.md`, `START_HERE_FOR_HUMANS.md`, `AGENTS.md`, entry point,
pointer and state.

Byte-identical Archivist copies: `common`, `authority`, `enrich`, `chunks`,
`indexes`, `release_contract`; `workspace_health.py check` now reports drift
(probe confirmed). 37 offline tests pass, also from an isolated copy with no sibling
repos. Real consumer code against a synthetic standalone build: Question Bot
`doctor` healthy and `query_release` returned the CFR chunk with tier and locator;
Adverse Information Assistant `check_library` ready (doha_search and
directive_quotations false). No live download or real-library rebuild yet.

Live census of the canonical library (read-only): 11,622 records; 237 with an
official URL, 749 retained-bytes-only, 3 duplicates, 10,633 DOHA (unsupported).

## Next
1. First real run, with the user's go-ahead for downloads: one small collection that
   includes a current CFR source, into a scratch destination, then `verify`.
2. Limits to close if wanted: directive splits (SEAD-3/4 sections for AIA quotations),
   semantic vectors, DOHA reconstruction, richer navigation graph.
3. Provenance backfill for the 749 retained-bytes-only records blocks a complete rebuild.

## Open Questions
- `../dcsa-archivist/agents/library-regenerator.md` and `regenerate.py` (Codex,
  uncommitted) now duplicate this agent's purpose via a different engine. Keep both,
  or retire the Archivist regenerator? Left untouched pending that decision.

## Log
2026-09-15 23:00 Claude — User directed independence from Archivist too, with a
use-time warning that the result is not autonomously maintained. Chose byte-identical
copies of Archivist's rule modules over reimplementation so classification, eligibility,
chunk locators and index schema cannot silently diverge; added them to
workspace_health drift checks. Wrote the standalone build/validate/evaluate/publish
path around them and gated publication on the consumers' own `approved_release`.
Dropped semantic vectors (no embedding runtime in stdlib) and directive splits
(Archivist-specific, 17 KB of SEAD parsing); both recorded as limits. Warning is on
stderr so JSON stdout stays parseable, and in the library so later readers see it.
2026-09-15 21:00 Claude — User directed that the agent work independently of
Librarian. Added `acquire` (explicit official URLs, not a crawler). HTTPS-only, no
http upgrade or mirror substitution; robots per RFC 9309; `matches_recorded_bytes`
flags changed sources. `recipe` mirrors every Archivist intake check.
2026-09-15 19:30 Claude — Created the repository at the user's request for a
dedicated rebuild agent, initially orchestrating Archivist's `regenerate` engine.
Vendored `release_contract.py` byte-identically. Private GitHub repository.
