# dcsa-library-rebuilder

Single job: rebuild a DCSA Library into an explicit, empty destination through
Custodian gates, and verify it. Entry point: `agents/rebuilder.md`.

## Start

1. Read `HANDOFF.md`, then check `git status --short` and Codex session records
   newer than its watermark (see `../HANDOFF-PROTOCOL.md`).
2. Read `agents/rebuilder.md` and `README.md`.
3. Confirm `config/rebuilder.json` exists and lists the canonical library under
   `protected_libraries`.

## Invariants

1. Never write into a protected library, inside one, or into a directory that
   contains one. Existing libraries are never replaced.
2. The build runs only through `../dcsa-archivist/custodian.py regenerate`. Do not
   copy, fork or reimplement engine, validation or publication code here.
3. Sources come only from `rebuilder.py acquire` (allowlisted HTTPS, verified
   redirects, robots.txt honored); there is no Librarian dependency. Every package
   is reviewed to the Archivist intake contract before a recipe is written. No
   guessed URLs; refused and failed acquisitions stay reported gaps.
4. DOHA case reconstruction is unsupported. Report it as excluded scope.
5. Never weaken evaluation cases to publish.
6. A rebuild is not done until `verify` passes. Pointing consumers at the result
   is the user's explicit decision.
7. No source bytes, extractions, local paths, personal data or run ledgers in Git.
8. Out of scope: compliance answers, guidance interpretation, ordinary library
   maintenance. Route those per `../WORKFLOWS.md`.

## Tests

`python -m unittest discover -s tests` (offline, synthetic data).
`src/library_rebuilder/release_contract.py` must stay byte-identical to
`../dcsa-archivist/src/dcsa_custodian/release_contract.py`; use
`python ../workspace_health.py sync` rather than editing the copy.

Update `HANDOFF.md` at checkpoints per `../HANDOFF-PROTOCOL.md`.

<!-- SHARED-POLICY:BEGIN -->
The Custodian publishes autonomously after validation and retrieval evaluation pass. Guidance Watch writes findings and catalog entries autonomously after citation and coverage checks pass. Automated consumers read approved robot content only; human paths are citation/navigation metadata. Consumers never promote their own answers into the governed library.
<!-- SHARED-POLICY:END -->
