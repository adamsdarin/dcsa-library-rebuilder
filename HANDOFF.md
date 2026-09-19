# HANDOFF — dcsa-library-rebuilder

Last updated: 2026-09-18 by Claude

## Current State
2026-09-18: census also reads official URLs the Custodian published after a byte-match
provenance decision (DOCUMENTS_ENRICHED.jsonl, source_url_basis
reacquired_bytes_identical) and reports provenance_recovered. Nothing else in the
enriched manifest is trusted as provenance. 44 tests pass.

Canonical standalone empty-destination Rebuilder. No runtime dependency on
Librarian/Archivist. Mandatory unmaintained-snapshot notice remains on every
command and generated library. Existing source acquisition/config/template edits
from the previous assistant were preserved.

Reviewed DOHA reconstruction is now supported: case metadata and taxonomy are
required, case/topic/path stores preserve exact robot text, and release integrity
binds stores and metadata. Cases remain precedent, never current guidance.
Shared doha.py joins the byte-identical Archivist modules checked by workspace_health.
43 offline tests pass, including from an isolated copy without sibling repositories. A separate workspace integration runs actual Question Bot
and Adverse Assistant retrieval against a synthetic standalone build, verifying
default hearing filters and explicit historical/exact-case access.
No real-network download or full-library rebuild was performed.

Verified SEAD/ISL section splitting and the shared robot-wiki graph/lint rules
are included. Broken or noncurrent directives cannot publish current sections.
Retrieval remains lexical-only. Historical census totals belong to the prior run; DOHA is no
longer an unsupported route. Sources without provenance still need review.

## Next
1. Use a confirmed destination and bounded source scope for a real rebuild.
2. Preserve the unmaintained-snapshot notice and all source-review gates.
3. Keep shared rule modules synchronized through workspace_health.

## Open Questions
No new implementation decision is needed. A live rebuild still needs a confirmed
destination and bounded acquisition scope; no live rebuild is claimed here.

## Log
2026-09-18 Claude — Wired census to Librarian/Archivist byte-verified provenance, the
route for the 749 retained-bytes-only records to become rebuildable from official URLs.
2026-09-16 Codex — Closed directive-section and robot-navigation gaps; verified consumer section
selection, isolated standalone execution, metadata tamper rejection and all 43 tests.
2026-09-16 Codex — Added reviewed DOHA recipe/build support, publication integrity, census
routing and real-consumer verification. The separate legacy-regenerator ownership
question is resolved by workspace routing; new rebuilds come here.
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
