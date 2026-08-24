# Tradysquid Maintainer Protocol

This repository is maintained by the owner, Claude, and Codex. GitHub `main`
is the authoritative code baseline. OneDrive `Tradysquid-AI-Control` is the
shared pre-Phase-0 coordination hub and audit mirror. Claude and Codex must
both use its exclusive lock; neither may edit while the other owns it.

Before modifying files:

1. Read `TRADYSQUID_2_MASTER_PREBUILD.md`.
2. Read `governance/PROJECT_STATE.json`, `governance/PHASES.json`, and
   `governance/ACTIVE_HANDOFF.json` for the current phase/subphase and any
   task already in flight, readable straight from this checkout with no
   OneDrive access required.
3. Read `CURRENT_STATE.md`, `CHANGELOG.jsonl`, and the relevant handoff in the
   control folder.
4. Inspect Git status and preserve unrelated changes.
5. Run `python ai_coordination.py verify`.
6. Acquire the shared lock with `python ai_coordination.py begin --actor ...`
   before the first repository write.

`READY_CLEAR` means a new task may claim the lock. `READY_ACTIVE` means the hub
is structurally healthy but another task owns the lock; do not edit or call
`begin` until that task finishes. `BLOCKED` means repair/recovery is required.

After modifying files:

1. Run relevant syntax checks and tests.
2. Commit only intended files and push normally; never force-push.
3. Restart only affected services and verify health.
4. Run `python ai_coordination.py finish` with the same actor, summary,
   method, tests, files, and final commit. This writes the handoff and releases
   the lock. The lock is a permission gate, not merely an audit note.

The OneDrive `UPDATE_LOCK.json` remains the real-time cross-agent exclusion
lock — git cannot provide atomic exclusive-create across two independent
working trees the way a synced folder can. `governance/` (created by Phase 0)
is the git-committed mirror of the same state: `PROJECT_STATE.json`,
`PHASES.json`, `ACTIVE_HANDOFF.json`, and `CHANGELOG.jsonl` are kept in sync
by `ai_coordination.py`'s `begin`/`checkpoint`/`finish` on every call, so a
fresh Claude or Codex session with no OneDrive access can still answer
"what's active, what's next" from repository state alone (Master Spec
Section 12's immediate-knowability requirement). Do not create separate
Claude and Codex copies of project truth. Private strategy boundaries remain
absolute: Codex owns BLACKTIDE-private work, Claude owns Claude-private work,
and neither may read or change the other's private strategy intelligence.

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

## Ownership enforcement and scoped instructions

`governance/OWNERSHIP.json` is the machine-readable source for Section 11's
five ownership classes (`SHARED_CORE`, `SHARED_DATA`, `BLACKTIDE_ONLY`,
`CLAUDE_ONLY`, `HUMAN_LEARNING_CENTER`). A path with a `protected: true`
entry may only be written by the actors listed in that entry's `writers`.
`TRADYSQUID_2_MASTER_PREBUILD.md` is `Owner`-writers-only, for example; no
agent may edit it regardless of what a task seems to require.

This is now enforced, not just documented: `ai_coordination.py finish`
calls `enforce_ownership(actor, files)` against `governance/OWNERSHIP.json`
before releasing the lock, and refuses to complete — no lock release, no
`COMPLETE` changelog event — if the declared file list includes a protected
path the declared actor is not a writer for. `ai_coordination.py verify`
separately calls `validate_governance_schema()` and `check_state_freshness()`
against every `governance/*.json` file and returns `BLOCKED` if a file is
malformed or `governance/PROJECT_STATE.json`'s recorded commit has drifted
from `HEAD` with no lock active to explain it. Both checks reuse `verify()`'s
and `finish()`'s existing shapes; there is no second lock or second
coordination script. Check a specific actor/path pair standalone with
`python ai_coordination.py check-ownership --actor ... --paths ...`.

A path with no `OWNERSHIP.json` entry is not a violation — most of the tree
is intentionally unassigned until the phase that creates it (see that
file's `not_yet_assigned` list). Enforcement only ever applies to paths
that already have an explicit entry.

Each `BLACKTIDE_ONLY`/`CLAUDE_ONLY` directory (created Phase 11+, e.g.
`bots/blacktide`, `bots/claude`) must contain its own `AGENTS.md` scoped to
that directory: an agent reads this root file plus the nearest scoped
`AGENTS.md` above its working path. `governance/OWNERSHIP.json`'s `writers`
field for that directory's entry is the authoritative grant; the scoped
file is a readable restatement of the same rule, not a separate grant. This
root file does not enumerate bot directories in advance of the phase that
creates them.
