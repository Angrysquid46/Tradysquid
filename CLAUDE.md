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

Tradysquid is an algorithmic options paper-trading system, SPY-only (the
older multi-ticker/credit-spread system described in earlier versions of
this file was erased — see PR #148, "Erase multi-ticker scanning/tracking
capability entirely"). Independently-tracked strategies scan live Tradier
market data and manage their own positions, each with its own Discord
category, config flag, and $500/trade risk cap:

- `SPY_0DTE_1M` / `SPY_0DTE_5M` — same-day-expiration directional bets;
  entry signal source differs (1M reads a live TradingView alert, 5M reads
  the Python opening-range breakout on 5-minute bars), exit rules identical.
- `SPY_KEY_LEVELS` — opening-range/VWAP/prior-day-level strategy with its
  own FRED/Finnhub economic-catalyst check.
- `SPY_EXPANSION_LEVEL` — EMA/MACD multi-timeframe-alignment strategy
  (disabled by default as of its introduction; check `config/scanner.json`
  for current state).
- 10 `SPY_RATCHET_<step>_<stop>` variants — share `SPY_0DTE_1M`'s live
  TradingView entry signal, differ only in exit shape (a ratchet floor that
  locks in gains at each step instead of a fixed profit target).

A Discord bot handles entry/exit alerts, dashboards, and slash commands.

## Two parallel codebases — know which one you're touching

- **Legacy flat-file scripts** (`spy_scanner.py`, `local_information_engine.py`,
  `discord_command_bot.py`, `tradysquid_supervisor.py`, and dozens of
  `test_*.py` files at the repo root): this is the code that is actually
  committed to `main` and deployed. `spy_scanner.py` (~7,000 lines) holds
  the entry scanners (`scan_spy_0dte_candidates`, `scan_spy_key_levels_candidates`,
  `scan_spy_expansion_candidates`), the exit models (`spy_0dte_exit_signal`,
  `spy_ratchet_exit_signal`, and the per-strategy `evaluate_open_*_row`
  dispatch in `evaluate_open_row`), and the risk gates (`apply_ticker_exposure_cap`,
  `entry_window_blocked`, `days_until_earnings`, the `MAX_RISK_PER_TRADE`/
  delta-band/DTE constants). `local_information_engine.py` runs the
  scheduled background jobs (market snapshots, options dashboards, news,
  position tracking, the real-time stream-quote exit path). `discord_command_bot.py`
  is a Flask app serving Discord slash-command interactions.
- **`tradysquid/` package** (`app.py` + `core/`, `data/`, `discord/`,
  `learning/`, `market/`, `operations/`, `providers/`, `reporting/`,
  `scanner/`, `strategies/`, `trading/`, `universe/`): a proper installable
  package (declared in `pyproject.toml`) that appears to be an in-progress
  rewrite of the *old* six-strategy, multi-ticker system (its `strategies/`
  modules are still `regular_call.py`/`regular_put.py`/`swing_call.py`/
  `swing_put.py`/`bull_put_spread.py`/`bear_call_spread.py` — it was never
  updated for the SPY-only pivot). It was committed on 2026-08-06
  (previously it sat uncommitted for an unknown length of time), so it now
  exists in git history, but it still isn't what's deployed — the legacy
  scripts are, and they've since diverged further (SPY-only, four strategy
  families instead of six). Don't assume this package is "the current
  thing" just because `pytest`'s default config points at it — confirm
  with the user/owner what it's for before building on it further.

## Testing

- Run tests with the project venv, not system Python:
  `./.venv-tradysquid/Scripts/python.exe -m pytest -q`
- `pyproject.toml` sets `testpaths = ["tests"]`, so a bare `pytest` run
  **only** collects `tests/` (the package for the orphaned `tradysquid/`
  code). It silently skips every one of the ~58 root-level `test_*.py`
  files — including the ones that directly cover the live exit/entry/risk
  logic above (`test_spy_0dte.py`, `test_spy_ratchet.py`,
  `test_ticker_exposure_cap.py`, `test_entry_time_window.py`,
  `test_journal_contract.py`, `test_performance_reconciliation.py`,
  `test_local_information_engine.py`, `test_runtime_contract.py`, etc.).
  When working on `spy_scanner.py`/`local_information_engine.py`/
  `runtime_contract.py`, run those explicitly by naming the files, or
  you'll get a false-green baseline.
- `.venv-tradysquid` needs `pip install -r requirements.txt -r requirements-dev.txt`
  run into it periodically — it was missing `flask` as of 2026-08-06 (fixed
  once), which blocks collection of any test importing `discord_command_bot`.
- `.venv-tradysquid/`, `state/`, `data/`, `logs/`, `archive/`, `backups/`,
  `docs/chain-snapshots/`, and `SETUP-RESULT.*` are gitignored — all runtime
  artifacts, not source. `backups/` in particular has held raw `.env` copies
  (real secrets) — never stage it.
- Known baseline failures, re-verified 2026-08-11 (confirm still true
  before treating any as newly introduced):
  - `test_local_information_engine.py::InformationEngineTests::test_closed_trade_journal_backfill_is_canonical_and_idempotent`
    — fails with `TypeError: ...Tracker.upsert_singleton_message() got an
    unexpected keyword argument 'components'`. The real
    `DiscordTracker.upsert_singleton_message` in `spy_scanner.py` does
    accept `components` (added for the archive-button feature); the test's
    inline fake `Tracker` class was never updated to match. Code looks
    correct, test double is stale. (`::test_reporting_job_refreshes_all_closed_trade_views`,
    previously listed alongside this one, now passes standalone — drop it
    if you don't reproduce it.)
  - `test_reset_trading_data.py::test_reset_deletes_every_thread_in_the_channel_directly`
    — `assert result["deleted_threads"] == 3` actually got `15`. Still not
    diagnosed; unlike the one above this doesn't have an obvious
    "test is stale" explanation on its face — look here first before
    trusting `reset_all_trade_data`'s thread-deletion count.
  - `tests/unit/test_verifier_modules.py::test_installation_verifier_runs_from_external_working_directory`
    — as of 2026-08-11 this errors on a Windows temp-directory permission
    issue in pytest's own tmpdir fixture (`PermissionError` on
    `C:\Users\...\Temp\pytest-of-<user>`), not the `database-integrity`
    assertion originally documented here. Environment-specific; check
    whether it still reproduces before assuming either description is
    current.

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
