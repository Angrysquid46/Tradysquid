# Codex and Claude Collaboration

Tradysquid uses one shared checkout and GitHub repository. Repository and
control-hub state—not conversation memory—is the handoff between assistants.

- GitHub `main`: authoritative approved code baseline.
- OneDrive `Tradysquid-AI-Control/CURRENT_STATE.md`: current branch, commit,
  dirty files, and lock owner.
- `CHANGELOG.jsonl`: append-only structured update history with actor, task,
  method, tests, files, and commits.
- `GIT_HISTORY.md`: human-readable repository history.
- `HANDOFF_CODEX.md` and `HANDOFF_CLAUDE.md`: last completed handoff.
- `UPDATE_LOCK.json`: exclusive repository edit lock. Its existence means no
  other actor may modify files.
- `ACTIVE_TASK.json`: recoverable current work record, including `work_id`.

Before edits, read the master specification and control records, inspect Git,
run `python ai_coordination.py verify`, then use `begin`. Use `checkpoint`
after meaningful milestones and `finish` only after tests and the intended
commit. The same actor and `work_id` own the lifecycle.

`verify` reports `READY_CLEAR` when the hub is healthy and unlocked,
`READY_ACTIVE` when it is healthy but currently owned, and `BLOCKED` for an
inconsistent hub. Only `READY_CLEAR` permits a new `begin`.

This OneDrive hub is the temporary coordination authority until Phase 0
activates repository-native `governance/`. Phase 0 must reconcile history into
one shared truth; it must not create competing Claude/Codex state files.

Private strategy boundary: Codex owns BLACKTIDE-private resources and Claude
owns Claude-private resources. Neither agent reads or writes the other's
private strategy intelligence. Shared infrastructure may be changed only
under an approved, locked task.
