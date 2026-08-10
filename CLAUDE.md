# Claude Tradysquid Instructions

Read and follow `AGENTS.md` before changing this repository. It defines a
**nonnegotiable updater freeze** covering `run_supervisor_simple.py`,
`tradysquid_supervisor.py`, `simple_upgrade_runtime.py`,
`deployment_validation_manifest.py`, `runtime_contract.py`,
`single_owner_runtime.py`, `ngrok_process_runtime.py`, `run_with_env.py`,
`START-SUPERVISOR.cmd`, `ENSURE-SUPERVISOR.ps1`,
`stop_tradysquid_processes.ps1`, and the updater/watchdog/rollback/
deployment-validation workflows. Do not touch those unless there is current
live evidence the updater itself failed and the owner explicitly authorizes
a repair.

Claude is the sole active maintainer of this checkout (Codex is not in use).
Treat GitHub `main` as the authoritative code. No lock or wait step is needed
before editing. Still keep the OneDrive control folder (`CURRENT_STATE.md`,
`CHANGELOG.jsonl`) as a running audit trail via `ai_coordination.py finish`
after each change — actor, summary, method, tests run, affected files, and
the final commit — since it's useful history, just not a gate.

Do not use brokerage execution tools. Do not expose secrets. Do not act on
member suggestions unless the owner approved them. Everything here is
paper-trading only, zero real money.

## What this project is

Tradysquid is an algorithmic options paper-trading system. Six
semi-independent trader strategies scan live Tradier market data and manage
their own positions:

- regular calls / regular puts (short-dated, same-session directional bets)
- swing calls / swing puts (longer-dated, held for a multi-day move)
- bull-put spreads / bear-call spreads (credit spreads)

A Discord bot handles entry/exit alerts, dashboards, and slash commands.

## Two parallel codebases — know which one you're touching

- **Legacy flat-file scripts** (`spy_scanner.py`, `local_information_engine.py`,
  `discord_command_bot.py`, `tradysquid_supervisor.py`, and dozens of
  `test_*.py` files at the repo root): this is the code that is actually
  committed to `main` and deployed. `spy_scanner.py` (~6,700 lines) holds the
  entry scanners (`scan_single_legs`, `scan_credit_spreads`), the exit
  models (`single_leg_exit_signal`, `spread_exit_signal`,
  `check_time_efficiency_exit`, `check_thesis_invalidation`,
  `apply_greeks_persistence_gate`), and the risk gates
  (`apply_ticker_exposure_cap`, `entry_window_blocked`,
  `days_until_earnings`, the `MAX_RISK_PER_TRADE`/delta-band/DTE constants).
  `local_information_engine.py` runs the scheduled background jobs (market
  snapshots, options dashboards, news, position tracking). `discord_command_bot.py`
  is a Flask app serving Discord slash-command interactions.
- **`tradysquid/` package** (`app.py` + `core/`, `data/`, `discord/`,
  `learning/`, `market/`, `operations/`, `providers/`, `reporting/`,
  `scanner/`, `strategies/` (six strategy modules mirroring the list above),
  `trading/`, `universe/`): a proper installable package (declared in
  `pyproject.toml`) that appears to be an in-progress rewrite of the same
  six strategies. It was committed on 2026-08-06 (previously it sat
  uncommitted for an unknown length of time), so it now exists in git
  history, but it still isn't what's deployed — the legacy scripts are.
  Don't assume this package is "the current thing" just because `pytest`'s
  default config points at it — confirm with the user/owner what it's for
  before building on it further.

## Testing

- Run tests with the project venv, not system Python:
  `./.venv-tradysquid/Scripts/python.exe -m pytest -q`
- `pyproject.toml` sets `testpaths = ["tests"]`, so a bare `pytest` run
  **only** collects `tests/` (the package for the new `tradysquid/` code).
  It silently skips every root-level `test_*.py` file — including the ones
  that directly cover the legacy exit/entry/risk logic above
  (`test_single_leg_exit_signal.py`, `test_spread_trader.py`,
  `test_thesis_invalidation.py`, `test_time_efficiency_exit.py`,
  `test_greeks_persistence_gate.py`, `test_ticker_exposure_cap.py`,
  `test_entry_time_window.py`, `test_breakeven_expected_move.py`,
  `test_delta_bucket_split.py`, `test_directional_spreads.py`,
  `test_regular_swing_traders.py`, etc.). When working on `spy_scanner.py`,
  run those explicitly by naming the files, or you'll get a false-green
  baseline.
- `.venv-tradysquid` needs `pip install -r requirements.txt -r requirements-dev.txt`
  run into it periodically — it was missing `flask` as of 2026-08-06 (fixed
  once), which blocks collection of any test importing `discord_command_bot`.
- `.venv-tradysquid/`, `state/`, `data/`, `logs/`, `archive/`, `backups/`,
  `docs/chain-snapshots/`, and `SETUP-RESULT.*` are gitignored — all runtime
  artifacts, not source. `backups/` in particular has held raw `.env` copies
  (real secrets) — never stage it.
- Known baseline failures as of 2026-08-06 (confirm still true before
  treating any as newly introduced — none of these look caused by a specific
  recent change, they read as pre-existing gaps in tests that were never
  actually being run due to the `testpaths` gap above):
  - `tests/unit/test_verifier_modules.py::test_installation_verifier_runs_from_external_working_directory`
    — fails on `database-integrity` against the live `data/tradysquid.db`
    (`wrong # of entries in index sqlite_autoindex_discord_message_state_1`);
    environment/data issue, not obviously a code bug.
  - `test_single_leg_exit_signal.py::test_breakeven_locks_in_after_a_real_peak_and_pullback`
    — asserts a peak-then-pullback-to-flat trade signals `"TAKE PROFIT"`,
    but `single_leg_exit_signal` in `spy_scanner.py` deliberately returns
    `"BREAKEVEN STOP"` for that case now (the function's own docstring
    explains the rename is intentional). Test looks stale relative to the
    code, not the other way around.
  - `test_local_information_engine.py::InformationEngineTests::test_closed_trade_journal_backfill_is_canonical_and_idempotent`
    and `::test_reporting_job_refreshes_all_closed_trade_views` — both fail
    with `TypeError: ...Tracker.upsert_singleton_message() got an unexpected
    keyword argument 'components'`. The real `DiscordTracker.upsert_singleton_message`
    in `spy_scanner.py` does accept `components` (added for the archive-button
    feature); the test's inline fake `Tracker` class was never updated to
    match. Code looks correct, test double is stale.
  - `test_reset_trading_data.py::test_reset_deletes_every_thread_in_the_channel_directly`
    — `assert result["deleted_threads"] == 3` actually got `15`. Not yet
    diagnosed; unlike the others above this one doesn't have an obvious
    "test is stale" explanation on its face — look here first before trusting
    `reset_all_trade_data`'s thread-deletion count.

## Working conventions

- Every change needs a real test that would actually fail without the fix,
  not one that just confirms the code runs.
- Run the full relevant suite before and after every change (see the
  `testpaths` caveat above — "full" may mean root-level files too,
  depending what you touched).
- Keep changes scoped and verified rather than large speculative rewrites.
- `config/scanner.json` holds the tunable parameters (profit targets, stop
  percentages, delta bands, DTE windows, RSI thresholds, per-strategy
  enable flags, liquidity minimums, schedules). Most of `spy_scanner.py`'s
  constants read from `configured(name, default)`, which layers an env var
  over this file over a hardcoded default — check here first before
  assuming a threshold is hardcoded.
