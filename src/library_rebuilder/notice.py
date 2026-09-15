"""The maintenance warning every command prints and every rebuilt library carries."""
from __future__ import annotations

import textwrap

MAINTENANCE_MODE = "standalone_unmaintained"

NOTICE = (
    "STANDALONE MODE - THIS LIBRARY WILL NOT BE MAINTAINED AUTONOMOUSLY. "
    "It is rebuilt without the Librarian and without the Archivist, so it is a one-time snapshot. "
    "Nothing will discover new or changed DCSA, ODNI or eCFR sources, review lifecycle or supersession, "
    "re-validate and re-publish updates, or send release events to Guidance Watch. "
    "It begins to go stale as soon as it is built. Keep it current only by rebuilding it, "
    "or by placing it under Librarian and Archivist maintenance."
)


def banner(width: int = 78) -> str:
    rule = "!" * width
    body = "\n".join(f"!! {line}" for line in textwrap.wrap(NOTICE, width - 3))
    return f"{rule}\n{body}\n{rule}"


def human_notice(release_id: str, built_utc: str, scope: str) -> str:
    return f"""# Maintenance notice: not autonomously maintained

**{NOTICE}**

| | |
|---|---|
| Release | `{release_id}` |
| Built | {built_utc} |
| Scope | {scope} |
| Maintenance mode | `{MAINTENANCE_MODE}` |

What is missing without the Librarian and the Archivist:

- **No source discovery.** New editions, rescissions and newly issued guidance are not found.
- **No lifecycle review.** A document marked current stays marked current after it is superseded.
- **No governed re-publication.** Corrections do not flow in through validation and approval gates.
- **No release events.** Guidance Watch and comparison are never told anything changed.
- **No semantic retrieval.** Indexes are lexical (full-text) only.

Treat answers from this library as current only as of the build date above.
"""
