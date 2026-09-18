# Reviewed DOHA reconstruction

DOHA cases use dedicated precedent indexes, not the current-guidance indexes.
Acquisition still requires official provenance and complete, hash-verified robot
extractions. No topic, outcome, era or eligibility is inferred from a filename.

The hash-bound intake plan contains `doha_taxonomy` with a `guidelines` object:
each reviewed A–M code maps to an object with a nonempty `aliases` array. Keep
the official taxonomy source and review basis alongside it. Every DOHA record
uses `collection_id: doha_decisions`, `current_status: historical_case_research`,
and a `doha_review` object containing:

| Field | Required review |
|---|---|
| `case_id` | Reviewed case number, e.g. `26-12345` |
| `decision_level` | `h1`–`h9` or `a1`–`a9`; hearing or appeal and revision |
| `decision_date` | Source-supported ISO date |
| `current_group` | `POST_SEAD_4`, `PRE_SEAD_4`, or `UNDETERMINED` |
| `outcome` | `approved`, `denied`, `remanded`, or `unknown` |
| `guidelines` | Unique reviewed codes present in the taxonomy |
| `answer_eligible` | Explicit boolean for default precedent retrieval |
| `reviewed_by`, `reviewed_utc` | Review attribution and timestamp with timezone |
| `metadata_basis` | Specific source evidence supporting the metadata |

Only tagged post-SEAD-4 hearings with approved/denied outcomes can be eligible
for default precedent retrieval. This does not make a decision controlling
guidance or predict an outcome. Appeals, older cases and unresolved cases remain
available only through the consumers' explicit research routes where supported.

The builder writes the two DOHA SQLite stores, topic relationships, exact robot
text, current-path manifest, taxonomy and router. It validates matching metadata,
coverage and content before publishing. Publication hashes bind the case indexes
and metadata; integrity verification refuses altered stores. Consumer integration
tests use the actual Question Bot and Adverse Information Assistant code.

The standalone output remains unmaintained. Case coverage is exactly the reviewed
recipe scope, not a claim that every decision on the official website was found.
Missing URLs or extraction evidence remain acquisition/review gaps. Existing
libraries are never overwritten, and changing an existing taxonomy requires a
separate reviewed migration.
