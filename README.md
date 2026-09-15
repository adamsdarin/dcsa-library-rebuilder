# DCSA Library Rebuilder

> **Without the Librarian and the Archivist, a rebuilt library is NOT maintained
> autonomously.** It is a one-time snapshot: no discovery of new or changed
> DCSA, ODNI or eCFR sources, no lifecycle or supersession review, no governed
> re-publication, no release events to Guidance Watch. It goes stale from the day
> it is built. Every command prints this warning, and the library carries it.

A single-purpose, standalone agent: rebuild a DCSA Library into an explicit, empty
destination and prove the result. It needs no other repository. Python 3.11+,
standard library only (SQLite with FTS5).

It does not answer compliance questions, interpret guidance, maintain an existing
library, or switch consumers to the rebuilt copy.

```text
census (read-only) -> acquire -> review -> recipe -> preflight
    -> run: stage, enrich, chunk, index, validate, evaluate, publish -> verify
```

Agent entry point: [`agents/rebuilder.md`](agents/rebuilder.md).

## Setup

```powershell
Copy-Item config\rebuilder.example.json config\rebuilder.json   # then set real paths
python -m unittest discover -s tests
```

`config/rebuilder.json` is gitignored. `protected_libraries` must list the canonical
library; any destination or quarantine that equals, sits inside, or contains a
protected library is refused.

## Commands

| Command | Writes | Purpose |
|---|---|---|
| `census --library <root> --out <file>` | report only | Classify each document by rebuild route |
| `acquire (--census <file> [--collection <id>] \| --urls <file>) --out <dir>` | packages, `acquisition_report.json` | Fetch allowlisted HTTPS sources into a run-owned quarantine |
| `recipe --dir <recipe dir> --release-id <id> --scope "<text>"` | `recipe.json` | Hash-bind a reviewed intake plan and evaluations; refuse early |
| `preflight --destination <dir>` | nothing | FTS5 present, destination empty, not protected, no held lock |
| `run --recipe <file> --destination <dir>` | destination, `runs/` ledger | Build, validate, evaluate and publish |
| `verify --destination <dir> [--release-id <id>]` | nothing | Fail-closed consumer-contract and integrity check |

## What a build produces

The same layout and contract the Question Bot and Adverse Information Assistant
already read: `START_HERE_FOR_ROBOTS.json`, enriched manifest, citation-safe chunks,
six release-scoped FTS5 indexes by authority class, query and access policy,
retrieval config, release pointer and library state, a navigation graph, and empty
schema-compatible DOHA stores. Both consumers' real read-only code has been run
against a standalone build.

Consistency with the Custodian comes from byte-identical copies of Archivist modules
(`common`, `authority`, `enrich`, `chunks`, `indexes`, `release_contract`): the same
authority roles, answer eligibility, duplicate exclusion, chunk locators and index
schema. `../workspace_health.py check` reports drift; `sync` refreshes the copies.
Do not edit them here.

## Publication gates

Nothing reaches the destination unless all pass, in a sibling staging folder:

- every chunk found verbatim in its robot text with a matching hash; index integrity,
  counts and path boundaries; no current document with an unclassified role;
- at least one current controlling regulation or contract clause;
- every retrieval evaluation case;
- the consumer release contract (`approved_release`, integrity mode).

## Limits

- **Not maintained.** See the notice above.
- **Lexical retrieval only.** No semantic vectors; semantic evaluation cases are rejected.
- **No DOHA cases.** DOHA stores are empty; case reconstruction is unsupported.
- **No directive splits.** SEAD-3/SEAD-4 section files are not produced, so the
  Adverse Information Assistant reports `directive_quotations: false`.
- **Minimal navigation graph** (collections to documents), not the Archivist wiki.
- A rebuild from current websites is a new release, not a byte-for-byte copy.
- Source bytes, extractions, local paths and run ledgers never enter Git.
