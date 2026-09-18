# dcsa-library-rebuilder

Single job: rebuild a DCSA Library into an explicit, empty destination, standalone,
and verify it. Entry point: `agents/rebuilder.md`.

**Standalone means unmaintained.** Without the Librarian and the Archivist the
rebuilt library is not maintained autonomously. Tell the user before starting and
when handing off. Never remove or soften the banner, the `maintenance_notice`
fields, or `MAINTENANCE_NOTICE.md`.

## Start

1. Read `HANDOFF.md`, then check `git status --short` and Codex session records
   newer than its watermark (see `../HANDOFF-PROTOCOL.md`).
2. Read `agents/rebuilder.md` and `README.md`.
3. Confirm `config/rebuilder.json` lists the canonical library under `protected_libraries`.

## Invariants

1. No runtime dependency on any other repository. Do not import `dcsa_custodian` or
   shell out to Librarian or Archivist.
2. Never write into a protected library, inside one, or into a directory that
   contains one. Existing libraries are never replaced.
3. `common.py`, `authority.py`, `enrich.py`, `chunks.py`, `indexes.py`, `doha.py`, `directive_splits.py`, `wiki.py` and
   `release_contract.py` are byte-identical Archivist copies. Change them in
   `dcsa-archivist`, then `python ../workspace_health.py sync`; never edit here.
4. Sources come only from `acquire` and are reviewed before a recipe is written. No
   guessed URLs; refused and failed acquisitions stay reported gaps.
5. Publication requires validation, a controlling-authority index, every evaluation
   case, and `approved_release` on the staged library. Never weaken a gate or case.
6. DOHA reconstruction requires reviewed case metadata and taxonomy; follow
   `docs/DOHA-RECONSTRUCTION.md`. Semantic retrieval remains unavailable standalone.
7. A rebuild is not done until `verify` passes. Pointing consumers at it is the user's call.
8. No source bytes, extractions, local paths, personal data or run ledgers in Git.
9. Out of scope: compliance answers, guidance interpretation, maintaining an existing
   library. Route those per `../WORKFLOWS.md`.

## Tests

`python -m unittest discover -s tests` (offline, synthetic data, no sibling repos).

Update `HANDOFF.md` at checkpoints per `../HANDOFF-PROTOCOL.md`.

<!-- SHARED-POLICY:BEGIN -->
The Custodian publishes autonomously after validation and retrieval evaluation pass. Guidance Watch writes findings and catalog entries autonomously after citation and coverage checks pass. Automated consumers read approved robot content only; human paths are citation/navigation metadata. Consumers never promote their own answers into the governed library.
<!-- SHARED-POLICY:END -->
