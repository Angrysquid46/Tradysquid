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

## Restate before you act - every message, no exceptions

**Open EVERY reply with the restatement, before any tool call. 100% of the
time.** Not "when it is ambiguous", not "for big tasks", not "when it seems
useful". Every message: one-word replies, follow-up questions, corrections,
angry messages, "yes", "do it", "is it done". No exceptions, ever.

    You asked:   <the request, in your words>
    I read it as: <concrete scope - files, behaviour, surfaces>
    Done means:  <the observable end state>
    Not doing:   <anything deliberately excluded, and why>

If the message is small the restatement is one line each. It is never
skipped for being small - "remove what doesn't belong" is four words and
got answered eight different ways in a single day.

If the restatement turns out to be wrong, the owner corrects four lines
instead of hours of work. That is the entire point, and it only works if it
is unconditional. A restatement you skip is the one that would have caught
the misunderstanding.

Restating is NOT asking permission. Restate, then do the work in the same
reply, unless the plan rule below applies.

**Then plan, unless it is a single obvious edit.** Write the plan to the
plan file and get approval before changing anything, for: anything touching
strategy behaviour, risk parameters, contract selection, the entry or exit
path, Discord structure, or more than about two files. Plan mode is the
owner's toggle in the client - but do NOT rely on it being on. Plan-first
is the default here regardless of what the client reports.

The reverse also applies: once a plan is approved, or the owner says "do
it" / "finish it", execute the whole thing without stopping to ask again.
Restating is not the same as asking permission - restate, then work.

**Numbers you invent are never acceptable.** Anything that decides what the
money buys - delta bands, thresholds, risk caps, position sizing - must
come from a measurement or from the owner. Never from your own judgement of
what seems reasonable. If it is not measured, say so and ask.

## How the owner expects you to work — read this first

These are not style preferences. Every rule here exists because breaking it
cost the owner a full day of repeating himself. Violating one is a failure
of the task, not a difference of approach.

**1. "Do X" means X is finished, deployed, and verified — not started.**
Deliver the whole thing in one pass: code, tests, full suite, deploy gate,
merge, deploy, and a check against the RUNNING system. Do not report
progress and wait. Do not hand back a piece and ask what's next. If you
find five problems while doing X, fix all five.

**2. Never claim more than you actually verified.**
Say what you ran and what it proves. "The unit test passes" is not "it
works in production" — that exact substitution shipped a broken time stop
that cost real money. Before writing that something is fixed, exercise it
through the production entry point (`evaluate_open_row`, the real command
handler, the deployed process), not the helper in isolation.

**3. Never state a number you did not count.**
No conclusions from truncated output. `tail -25` on 32 rows and reporting
"29 trades" is a fabricated number. Count explicitly, then report.

**4. Never guess at a cause. Say "I don't know yet."**
Three wrong explanations in a row for the same event is worse than one
"unidentified — here is what I checked." If the mechanism is unknown, fix
it defensively at the choke point so it cannot happen regardless of cause,
and say plainly that the trigger is still unknown.

**5. Do not shrink the scope, and do not dress a choice as a limitation.**
If part of a task is genuinely blocked, do every other part completely,
then state exactly what is left and the specific evidence that blocks it.
"That would be a large refactor" is not a blocker — it is the owner's call,
not yours.

**6. Enumerate the whole surface before saying "done".**
List every instance first, then handle or justify each one. Checking one
slice, finding it clean, and declaring completion is the single most
repeated failure in this project.

**7. Ask only when the answer changes what you build.**
Contract selection, risk parameters, anything that decides what the money
buys — ask. Everything else, make the call and say what you chose. Do not
ask for permission you already have. Do not end a turn with "say go" when
the owner has already said go.

**8. When corrected, fix it and continue — do not re-litigate.**
One sentence acknowledging the error, then the corrected work. No repeated
apologies, no summarising the mistake at length.

**Do not claim completion from judgement - run the check:**

    ./.venv-tradysquid/Scripts/python.exe verify_done.py --full

It verifies every condition below against the LIVE system and exits
non-zero if any fail. Paste its output instead of asserting the work is
finished. If it says NOT DONE, the work is not done.

**Definition of done for this repo:** `deployed_sha` == `origin/main`,
`last_update_status` == `DEPLOYED`, the root suite shows no NEW failures
against a baseline worktree, the 252-test deploy gate is green, and the
behaviour is confirmed against the live process — not only in tests.

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

## Strategy work: read the rules file first

**Before editing, measuring, or reasoning about any strategy, open
`docs/STRATEGY_RULES.md`.** It is generated from the live registry by
`strategy_rules_doc.py` and lists all 15 strategies with their signal
function, their OWN exit rules, max signal age, channel and enabled state,
plus the measured record under those exact settings.

Re-deriving these from scratch has repeatedly produced wrong answers:
measuring every strategy under a shared +50/-50 exit that none of them
use, measuring two at ATR thresholds they had been recalibrated away
from, and measuring `SPY_KEY_LEVELS` with an option-premium exit when it
exits on the *underlying*. That last error made the best strategy on the
roster look like the worst.

- **Never apply a default or shared exit.** Per-strategy exits live in
  `NEW_STRATEGY_EXITS`. `SPY_KEY_LEVELS` is deliberately absent from it
  because it exits on underlying price levels.
- **After changing a strategy, run `python strategy_rules_doc.py`.**
  `test_strategy_rules_doc.py` fails until the doc is regenerated, and it
  also asserts runtime behaviour matches the doc and that nothing has
  reverted to +50/-50.
- **A full option backtest is ~40 minutes.** Don't re-run one to learn how
  a strategy performs - the measured table is in the rules doc.


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
    — fixed 2026-08-11. `wipe_channel_threads` retries up to 5 passes on
    purpose (survives a rate-limit burst or a thread created mid-wipe); the
    test's `fake_request` mock was static and kept returning already-
    "deleted" threads on every pass, so 5 passes x 3 threads counted as 15.
    `reset_all_trade_data` itself was never buggy — real Discord reflects
    real deletions, a static mock doesn't. Made the mock stateful instead.
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
