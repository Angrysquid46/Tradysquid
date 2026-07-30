# Codex and Claude Collaboration

Tradysquid uses one shared checkout and GitHub repository. It does not copy
conversation memory between assistants.

- GitHub `main`: authoritative current code.
- OneDrive `Tradysquid-AI-Control/CURRENT_STATE.md`: current branch, commit,
  dirty files, and lock owner.
- `CHANGELOG.jsonl`: append-only structured update history with actor, task,
  method, tests, files, and commits.
- `GIT_HISTORY.md`: human-readable repository history.
- `HANDOFF_CODEX.md` and `HANDOFF_CLAUDE.md`: last completed handoff.
- `UPDATE_LOCK.json`: exclusive edit lock. Its existence means no other actor
  may modify files.

Use `python ai_coordination.py status` to refresh and inspect state. Use
`begin` before edits and `finish` after a tested, published update.
