# HANDOFF — dcsa-library-rebuilder

Last updated: 2026-09-15T19:30:00Z by Claude

## Current State
New single-purpose repository: an agent whose only job is rebuilding a DCSA
Library into an empty destination. Prompt `agents/rebuilder.md`; stdlib CLI
`rebuilder.py` with `census`, `recipe`, `preflight`, `run`, `verify`. The build is
delegated to `../dcsa-archivist/custodian.py regenerate`; nothing is reimplemented.
15 offline tests pass; Archivist `tests.test_regenerate` 7/7 pass.

Live read-only census of the canonical library (release
`dd254-dec1999-lifecycle-fix-20260915`, manifest hash unchanged): 11,622 records —
237 reacquirable from a recorded official URL, 749 retained-bytes-only (no official
origin on record), 3 declared duplicates, 10,633 DOHA (unsupported). Preflight
accepts an empty scratch destination and refuses the canonical library. Verify
against the canonical library passes all integrity checks and correctly refuses it
for lacking a regeneration marker. No acquisition, build or publication was run.

## Next
1. Commit Archivist's `regenerate.py`, `doha.py`, `docs/REGENERATION.md` and tests;
   they are untracked Codex work, so a fresh clone of `dcsa-archivist` lacks the
   engine this agent drives. `preflight` reports that case.
2. First real run: a small general-source scope (for example URL-backed records in
   one collection) into a scratch destination, then `verify`.
3. Provenance backfill for the 749 retained-bytes-only records is the largest
   blocker to a complete general-source rebuild; it is Archivist review work.

## Open Questions
- `../dcsa-archivist/agents/library-regenerator.md` is an overlapping role prompt
  (Codex, uncommitted). Keep it as the engine-level contract, or reduce it to a
  pointer here? Left untouched pending that decision.

## Log
2026-09-15 19:30 Claude — Created the repository at the user's request for a
dedicated rebuild agent. Chose orchestration over extraction: moving `regenerate.py`
out of Archivist would reorganize uncommitted Codex work and split the release code
path, so this repo calls the engine and adds census, early recipe checks, protected-
library refusal, a run ledger and fail-closed verify. Vendored `release_contract.py`
byte-identically and registered it with workspace_health. Private GitHub repository,
matching the other Custodian repositories.
