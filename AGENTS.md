# Tradysquid Maintainer Protocol

This repository is maintained by the owner and Claude (Codex is not an active
collaborator on this checkout). GitHub `main` is the authoritative code
baseline; OneDrive `Tradysquid-AI-Control` is an audit trail, not a
coordination gate — there is no second AI actor to coordinate with, so no
lock-and-wait step is required before editing.

Before modifying files:

1. Read `CURRENT_STATE.md` and `CHANGELOG.jsonl` in the control folder for
   recent context.
2. Inspect Git status and preserve unrelated changes.

After modifying files:

1. Run relevant syntax checks and tests.
2. Commit only intended files and push normally; never force-push.
3. Restart only affected services and verify health.
4. Run `python ai_coordination.py begin --actor Claude --task "..." --method "..."`
   followed by `python ai_coordination.py finish` with the actor, summary,
   method, tests, files, and final commit — this just logs the change to
   `CURRENT_STATE.md`/`CHANGELOG.jsonl`, it's not a permission check.

Never place credentials, conversation transcripts, brokerage data, or private
Discord content in the shared control folder. Never execute brokerage trades.
Member requests require owner approval through the upgrade queue.

## Nonnegotiable updater freeze

The existing automatic update path is production infrastructure. A working
updater must not be rewritten, refactored, replaced, simplified, expanded, or
"improved" merely because an application feature failed or an old Discord card
shows historical errors.

Before any change that could affect deployment:

1. Read this section first.
2. Identify the latest approved merge on GitHub `main`.
3. Read the laptop deployment receipt and confirm the deployed commit, last
   update status, rollback status, and current service health.
4. Treat old `#applied-upgrades` cards and historical commit numbers as history,
   not proof of a current updater failure.
5. If the latest approved merge is deployed automatically and core services are
   healthy, the updater is working. Stop investigating it and change only the
   requested application code.

These files and components are frozen unless current live evidence proves that
the updater component itself failed and the owner explicitly authorizes an
updater repair:

- `run_supervisor_simple.py`
- `tradysquid_supervisor.py`
- `simple_upgrade_runtime.py`
- `deployment_validation_manifest.py`
- `runtime_contract.py`
- `single_owner_runtime.py`
- `ngrok_process_runtime.py`
- `run_with_env.py`
- `START-SUPERVISOR.cmd`
- `ENSURE-SUPERVISOR.ps1`
- `stop_tradysquid_processes.ps1`
- updater, watchdog, rollback, startup-task, and deployment-validation workflows

A failure in a scanner, strategy, dashboard, report, Discord command, scheduled
job, provider call, or other application feature is not authorization to touch
the updater. Repair the exact failed feature or exact failed pipeline stage.

Every future change must follow the established path:

1. Separate branch.
2. Relevant tests and existing CI.
3. Merge only after required checks pass.
4. No manual file copying to the laptop.
5. Existing updater installs the approved merge.
6. Live receipt confirms the deployed commit.
7. Only the affected services are evaluated; no broad restart or architecture
   replacement without evidence.
8. Roll back automatically if deployment validation fails.

Do not claim deployment from GitHub code alone. Distinguish code written, CI
passed, merged, automatically installed, and live verified. Never change the
updater to make an application-only test easier.
