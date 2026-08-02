# Tradysquid upgrade, deployment, diagnostics, and verification rewrite

## Active architecture

The active supervisor is `run_supervisor_simple.py`, launched only through
`START-SUPERVISOR.cmd`. It checks `origin/main` every 120 seconds and limits the
deployment transaction to fetch, preflight, safe fast-forward, validation,
rollback, and one stack restart.

Discord maintenance, diagnostics, lifecycle dashboards, and live verification
run after startup. They cannot block or roll back a valid code installation.

## Shared upgrade path

Both owner requests and persistent diagnostics use the same GitHub upgrade
batch. Diagnostics are labeled `AUTOMATIC DIAGNOSTIC` and
`DIAGNOSTIC-GENERATED`, deduplicated by a stable signature, and updated in place
even after the batch becomes READY.

The system never automatically edits code, creates pull requests, merges,
approves, or deploys repairs.

## Runtime diagnostics

`self-diagnostics` runs every five minutes and immediately after each
information-engine startup. It checks supervisor state, service ports, watchdog,
Git state, Discord channels, command hooks, scheduler receipts, incremental log
evidence, and restart-loop deltas.

Persistent defects enter the shared upgrade batch after their threshold. A
controlled live self-test verifies one diagnostic can be created and recovered
using the same local record and Discord message.

## Market-hours review

`market-hours-upgrade-review` runs at most once every two hours during the
official regular market session. It uses the configured market calendar when
available and a tested holiday/early-close fallback. Empty or unchanged queues
are not reposted.

## Factual Discord proof

- `#upgrade-requests` receives intake records and one shared lifecycle card.
- `#upgrade-review` receives stable diagnostic records, the market review queue,
  and itemized live acceptance.
- `#applied-upgrades` identifies implementations, affected channels, commits,
  and runtime receipts. A generated card is never proof of itself.

Lifecycle states do not skip evidence. CI success is not deployment; deployment
is not verification. VERIFIED requires fresh post-deployment self-diagnostic and
applied-upgrade receipts with no open diagnostic failures.

## Runtime data

Generated databases, logs, scheduler state, Discord message state, and trading
runtime files are ignored or preserved. Backup verification and a rollback ref
are completed before healthy services are stopped.

## Legacy behavior

The resilient and legacy supervisor modules remain only as historical source.
The BAT launcher, watchdog, stop script, diagnostics, and active tests all point
to `run_supervisor_simple.py`. Retired Discord-readiness gates are not part of
the active deployment path.

## Completion contract

Repository validation may approve merge, but live completion is withheld until
the laptop deploys the merged commit and the itemized `#upgrade-review`
acceptance card reports the real runtime state.
