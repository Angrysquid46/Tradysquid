# Tradysquid Shared Maintainer Protocol

This repository is maintained by the owner, Codex, and Claude. GitHub `main`
is the authoritative code baseline; OneDrive `Tradysquid-AI-Control` is the
operational audit and coordination record.

Before modifying files:

1. Read `CURRENT_STATE.md`, `CHANGELOG.jsonl`, and your handoff in the control
   folder.
2. Inspect Git status and preserve unrelated changes.
3. Run `python ai_coordination.py begin --actor <Codex|Claude> --task "..." --method "..."`.
4. If the update lock already exists, stop without editing.

After modifying files:

1. Run relevant syntax checks and tests.
2. Commit only intended files and push normally; never force-push.
3. Restart only affected services and verify health.
4. Run `python ai_coordination.py finish` with the actor, summary, method,
   tests, files, and final commit.

Never place credentials, conversation transcripts, brokerage data, or private
Discord content in the shared control folder. Never execute brokerage trades.
Member requests require owner approval through the upgrade queue.
