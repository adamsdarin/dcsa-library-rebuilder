# DCSA Library Rebuilder

A single-purpose agent: rebuild a DCSA Library into an explicit, empty destination
through the Custodian's normal validation, evaluation and publication gates, then
prove the result.

It does not answer compliance questions, interpret guidance, maintain an existing
library, or switch consumers to the rebuilt copy.

## How it fits

This repository is the operating agent and works without Librarian: it acquires
official sources itself and writes Archivist-format intake packages. The build is
performed by the Archivist's deterministic engine (`dcsa-archivist`,
`custodian.py regenerate`), which is not reimplemented here.

```text
census (read-only) -> acquire -> review -> recipe
    -> preflight -> engine regenerate -> verify -> release events to conductor
```

Agent entry point: [`agents/rebuilder.md`](agents/rebuilder.md).

## Setup

Python 3.11+, standard library only. Requires a sibling checkout of
`dcsa-archivist` (with the `regenerate` command and its embedding runtime) for
`preflight` and `run`. `census`, `acquire`, `recipe` and `verify` need no other
repository.

```powershell
Copy-Item config\rebuilder.example.json config\rebuilder.json   # then set real paths
python -m unittest discover -s tests
```

`config/rebuilder.json` is gitignored. Relative paths resolve against this
repository's root. `protected_libraries` must list the canonical library; every
destination that equals, sits inside, or contains a protected library is refused.

## Commands

| Command | Writes | Purpose |
|---|---|---|
| `census --library <root> --out <file>` | report only | Classify each document by rebuild route |
| `acquire (--census <file> [--collection <id>] \| --urls <file>) --out <dir>` | packages, `acquisition_report.json` | Fetch allowlisted HTTPS sources into a run-owned quarantine |
| `recipe --dir <recipe dir> --release-id <id> --scope "<text>"` | `recipe.json` | Hash-bind a reviewed intake plan and evaluations; refuse what Archivist intake would refuse |
| `preflight --destination <dir>` | nothing | Engine present, destination empty, not protected, no held lock |
| `run --recipe <file> --destination <dir>` | destination, `runs/` ledger | Preflight, then invoke the engine |
| `verify --destination <dir> [--release-id <id>]` | nothing | Fail-closed approved-release and integrity check |

## Census routes

| Route | Meaning |
|---|---|
| `reacquire_from_official_url` | An official URL is on record |
| `retained_bytes_only` | No official origin on record; needs provenance review |
| `source_missing` | Manifest says the source file is absent |
| `duplicate_skip` | Declared duplicate of another record |
| `doha_unsupported` | DOHA case reconstruction is not yet implemented |

## Limits

- DOHA case reconstruction is unsupported by the engine and refused here.
- A rebuild from current websites is a new release, not a byte-for-byte copy.
  Exact reproduction needs retained reviewed bytes and hashes.
- Source bytes, extractions, local paths and run ledgers never enter Git.

`src/library_rebuilder/release_contract.py` is a byte-identical copy of the
Custodian contract, checked by `../workspace_health.py check`.
