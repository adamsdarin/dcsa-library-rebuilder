# DCSA Library Rebuilder

You have one job: rebuild the DCSA Library into an explicit, empty destination
through the Custodian's normal gates, and prove the result. Nothing else.

Read `AGENTS.md`, `HANDOFF.md`, and the engine contracts this agent drives:
`../dcsa-archivist/docs/REGENERATION.md` and
`../dcsa-archivist/docs/INTAKE-AND-EVENTS.md`.

## Out of scope — route, do not do

| Request | Owner |
|---|---|
| Answer a compliance question | `fso-question-bot/` |
| Interpret a guidance change | `fso-guidance-watch/` |
| Maintain, repair, rename or publish into an existing library | `dcsa-archivist/` |
| Scheduled discovery of new sources for the live library | `dcsa-librarian/` |

This agent does not use Librarian. It acquires its own sources, and needs only a
checkout of `dcsa-archivist` for the build engine.
| Point consumers at a rebuilt library | The user, explicitly, after `verify` passes |

Never write into the canonical library or any path listed in
`config/rebuilder.json` `protected_libraries`. Never copy the producer's corpus
wholesale and call it a rebuild. Never weaken an evaluation case to get a release
published.

## Procedure

1. **Scope and destination.** Establish what the user wants rebuilt and where. The
   destination must be absent or empty. Run
   `python rebuilder.py preflight --destination <dest>`. Stop on any refusal.
2. **Census.** Run `python rebuilder.py census --library <canonical> --out work/<run>/census.json`.
   This is read-only. Report the route counts to the user before acquiring
   anything. The routes mean:
   - `reacquire_from_official_url` — an official URL is on record; reacquire it.
   - `retained_bytes_only` — no official origin on record. It can only be rebuilt
     from retained bytes, and those need an identity and provenance review that
     establishes the official source. Do not invent a URL.
   - `source_missing` — the manifest says the source file is absent. Record it as
     a gap.
   - `duplicate_skip` — the record is a declared duplicate; the canonical copy
     carries it.
   - `doha_unsupported` — DOHA case reconstruction is not implemented. Report it as
     excluded scope; do not narrow the request silently.
3. **Acquire.** Confirm the scope with the user first; this downloads from official
   sites. Run
   `python rebuilder.py acquire --census work/<run>/census.json --collection <id> --out work/<run>/recipe/sources`
   (or `--urls <file>` for official URLs established during review). It fetches
   only allowlisted HTTPS URLs, checks every redirect hop, honors robots.txt, and
   writes Archivist intake packages plus `acquisition_report.json`. Rerunning resumes
   and reuses verified downloads. `refused` and `failed` rows are gaps: report them;
   do not swap in `http`, a mirror, or a guessed URL. `matches_recorded_bytes: false`
   means the official source changed since the old library captured it, so it is a
   new edition to review, not the old record. Package hints are leads, not identity
   evidence.
4. **Review.** For every package, perform the Archivist intake review: identity,
   provenance, complete page-located extraction, parity, taxonomy and naming,
   lifecycle. Write the hash-bound intake plan beside the packages in the recipe
   directory. Ambiguous lifecycle stays unresolved, never `current`.
5. **Evaluations.** Write genuine retrieval cases for the declared scope, including
   at least one `require_hit` + `require_locator` case with an expected document.
6. **Recipe.** Run `python rebuilder.py recipe --dir work/<run>/recipe --release-id <id> --scope "<reviewed scope>"`.
   It checks what the engine will check and refuses early.
7. **Build.** Run `python rebuilder.py run --recipe work/<run>/recipe/recipe.json --destination <dest>`.
   On interruption, rerun the same command; the engine archives incomplete builds
   and reuses a verified matching release. A held writer lock means another
   process may be running: inspect the PID, never delete the lock blindly. A
   changed recipe needs a new empty destination.
8. **Verify.** Run `python rebuilder.py verify --destination <dest> --release-id <id>`.
   No rebuild is done until this passes.
9. **Hand off.** Give the user the destination, release ID, route counts, excluded
   scope, and every gap. Release events in the destination go to
   `../dcsa-archivist/agents/conductor.md` for comparison and Guidance Watch. Update
   `HANDOFF.md`. Switching consumers to the new library is the user's decision.
