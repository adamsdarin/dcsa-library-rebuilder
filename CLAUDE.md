# dcsa-library-rebuilder

Follow `AGENTS.md` in this directory; it is the operating contract for both Claude
and Codex. Keep the two files consistent.

## Session handoff — read this first

This project is worked on by both Claude and Codex, which cannot see each
other's conversations. **`HANDOFF.md` in this directory is the shared state.**

- **At the start of a session:** read `HANDOFF.md`. Take its `Last updated`
  timestamp as a watermark and check what changed since — `git log --since=`,
  `git status --short`, and Codex session files under `~/.codex/sessions`
  newer than that watermark. Record anything you find that is not already in
  the log, then begin.
- **While working:** append a log entry after each meaningful unit of work, not
  at the end of the session.
- **Overwrite** the `Current State` block. **Append** to the `Log`, and trim it
  to roughly 15 entries.
- Keep entries at decision level — no case detail, no personal data.

Full rules: `C:\Users\darin\src\HANDOFF-PROTOCOL.md`

## Claude-specific notes

Open every rebuild conversation, and close every handoff, with the standalone
maintenance notice from `agents/rebuilder.md`: without the Librarian and the
Archivist the rebuilt library is not maintained autonomously.

The copied Archivist modules must not be edited here; change them upstream and run
`python ../workspace_health.py sync`.
