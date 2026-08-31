# Adding a Trader to Tradysquid

This is the production integration runbook for adding a new paper trader. It is not a strategy template. A trader is not live merely because its code is merged, a Python process exists, or a TCP port is open.

The required result is:

> The approved commit is installed on the laptop; one restart-safe trader process is running; scheduled cycles continue advancing; the cycles receive current market evidence; official opens and closes can reach the neutral scoreboard; the trader appears on its own Discord surfaces; and all of that remains true after a process exit and an updater deployment.

Do not copy another trader's private strategy. Reuse only the shared operational contracts described here.

## 1. Non-negotiable boundaries

- Read the root `AGENTS.md`, governance state, and the nearest scoped `AGENTS.md` before editing.
- Claim the shared coordination lock with `python ai_coordination.py begin --actor ...` before the first write.
- Give the trader an isolated `bots/<slug>/` package and an ownership entry in `governance/OWNERSHIP.json` before private implementation.
- Strategy logic, signals, thresholds, sizing, exits, learning, and evolution stay inside the trader's protected ownership area.
- Shared code may handle factual market data, the official ledger, Discord transport, process lifecycle, and strategy-neutral health only.
- Never execute brokerage trades. The competition runtime is paper-only.
- Never rewrite the frozen updater or supervisor to accommodate a trader defect. Fix the trader or the exact failed application pipeline stage.
- Never force an entry to prove liveness. Prove evaluation and explainable `NO_ACTION`; use tests to prove the order path.
- Do not restart unrelated traders. Replace only the affected process, and only when it is flat unless the trader has a tested open-position recovery path.

## 2. Define the trader contract first

Choose and record all of these before implementation:

| Field | Contract |
|---|---|
| Display name | Uppercase stable ID, such as `GROK`; never rename after official trades exist. |
| Package slug | Lowercase `bots/<slug>/`. |
| Owner/writers | Explicit entry in `governance/OWNERSHIP.json` and matching `bots/<slug>/AGENTS.md`. |
| Product and mode | SPY 0DTE long calls/puts, realistic paper execution, one open trade maximum. |
| Starting state | Generation 1, $1,000, zero inherited trades, flat. |
| Instance port | A unique loopback port. Inspect current assignments before choosing; production currently uses 8892 through 8895. |
| Cycle cadence | State the evaluation interval and what timestamp proves the last completed cycle. |
| Required evidence | Completed bars, quote, option chain, expiration, session/calendar, and any shared factual features. |
| Closed-session behavior | Process remains healthy and idle; entry evaluation returns `NO_ACTION`. Market closure must not kill the process. |
| Health artifact | Strategy-neutral atomic state containing at least `observed_at`, `status`, and `action`. No private reasoning. |
| Logs | `state/<slug>-startup.log` plus bounded/rotated runtime logging where supported. |
| Stop control | `state/<slug>-stop.flag`; its presence intentionally prevents restart. |
| Discord category | Uppercase category and four dedicated channels: dashboard, held trades, winners, losers. |

Check port assignments before committing:

```powershell
netstat -ano -p tcp | Select-String ':8892|:8893|:8894|:8895'
rg -n "INSTANCE_PORT|889[0-9]" bots start_*.cmd
```

Do not reuse a port because another trader happens to be stopped. A collision can make one healthy trader look dead whenever the other starts.

## 3. Build the isolated package

The package should normally contain:

```text
bots/<slug>/
  AGENTS.md          ownership and private-strategy boundary
  __init__.py
  env_bootstrap.py   environment loading without printing secrets
  preflight.py       fail-closed readiness checks
  launch.py          single supported production entry point
  runtime.py         recovery and one-cycle orchestration
  scheduler.py       repeated cycle execution
  engine.py          private strategy
  evolution.py       optional private learning, restart-safe
```

Additional private modules are allowed. Operational code must not leak private signals, thresholds, features, or future trade reasoning through logs, health files, Discord, or shared databases.

### Preflight requirements

`preflight.py` must check at least:

1. The installed commit matches the laptop deployment receipt and `last_update_status` is `DEPLOYED` or `UP_TO_DATE`.
2. The assigned instance port is free before bind.
3. Required credentials are present without printing their values.
4. The market calendar/session state is known.
5. The required expiration and provider endpoints are available when the market is expected to be tradable.
6. Official scoreboard recovery is possible.
7. Required shared evidence is present and fresh enough for the trader's cadence.

Separate fatal startup failures from expected idle conditions. A closed market is normally an idle condition, not a reason for the long-lived process to exit. Provider unavailability may fail closed for trading while the runtime remains available and reports degradation.

### Runtime and recovery requirements

The runtime must:

- connect to `scoreboard.py` and derive bankroll, generation, and open position from official state;
- recover an existing official open position before evaluating a new entry;
- never maintain more than one official open trade;
- make trade IDs globally unique and stable across retries;
- record entry once through `scoreboard.record_trade_open`;
- record close once through `scoreboard.record_trade_close`;
- use observed ask for entry and observed bid for exit under the current paper-execution rules;
- survive a restart without inventing, duplicating, or losing a position;
- keep the process alive outside market hours while suppressing entries;
- catch and report cycle exceptions without silently stopping future cycles;
- close every SQLite connection in the same thread that uses it, or deliberately open it with the repository's supported cross-thread option when a scheduler worker requires that;
- atomically update a strategy-neutral cycle-health artifact after every completed, idle, or failed cycle.

A listener proves only that something bound a socket. It does not prove the scheduler is executing.

### Scheduler requirements

- Use one scheduler instance and one job identity per trader.
- Prevent overlapping cycle executions.
- Make the first cycle observable promptly after startup.
- Continue scheduling after `NO_ACTION` and recoverable exceptions.
- Emit a current health timestamp on `COMPLETED`, `IDLE`, and `ERROR`.
- Test at least two consecutive scheduled cycles; a one-shot test misses worker-thread and connection-lifetime defects.

## 4. Wire every shared integration point

Adding the package alone does not register the trader. Update every applicable point below in the same pull request.

### Ownership

- Add the protected directory to `governance/OWNERSHIP.json` with the correct writer.
- Add `bots/<slug>/AGENTS.md` restating the same boundary.
- Extend ownership/isolation tests so unauthorized writes and cross-private imports fail.

### Neutral scoreboard

- Add the uppercase ID to `scoreboard.BOTS` in `scoreboard.py`.
- Do not seed fake trades or copy another bot's history.
- Verify `scoreboard_snapshot` returns generation 1, $1,000, zero trades, and `FLAT` on an empty ledger.
- Test legal open/close, duplicate rejection, bankroll enforcement, one-position enforcement, immutable close, bust/start transitions, and restart recovery.

### Public presentation and Discord

- Add the trader to `rivalry_presentation.PUBLIC_BOTS`.
- Declare its five surfaces in `discord_surface_manifest.py`: dashboard card, dashboard chart, held-trade card, winner events, and loser events.
- Add its category and four channels to `sync_discord_structure.py`.
- Add channel topics/cadence descriptions there as well.
- Ensure `local_information_engine.competition_surfaces_job` includes it through `PUBLIC_BOTS`.
- Extend presentation, surface-manifest, competition-job, and Discord-layout tests.

Persistent cards must rebuild from authoritative state after startup or deployment. Do not wait for the trader's first trade to create its dashboard and flat-position card.

### Shared market evidence

Confirm the information engine supplies evidence at least as frequently as the trader consumes it:

- `spy-market-data-capture` supplies quotes and option chains.
- `spy-bars-capture` supplies completed one-minute bars.
- `state/local-information.db`, table `job_runs`, records job status and detail.
- Shared REST access goes through the existing quota/cache path; do not create an independent polling loop that bypasses priority and budget controls.

The bar collector uses a weekend-safe rolling backfill window, globally
deduplicates provider timestamps, and partitions every bar by the bar's own
Central-time market date—not by the date on which it was downloaded. Audit a
range with `python audit_bar_history.py --start YYYY-MM-DD --end YYYY-MM-DD`.
Use `--apply` only for an owner-authorized additive repair from verified
provider rows. Formal backtests must reject any session whose bar audit is not
complete; missing minutes may never be silently interpolated.

Fresh quote/chain data does not compensate for stale bars. Validate each required evidence stream independently, using provider/market timestamps rather than file modification time alone.

### Production launcher and restart loop

Create:

- `start_<slug>.cmd`: changes to repository root, ensures `state/` exists, honors `<slug>-stop.flag`, activates the repository virtual environment through `PATH`, launches only `python -u -m bots.<slug>.launch`, logs the exit, waits 15 seconds, and retries.
- `start_<slug>_hidden.vbs`: launches the CMD wrapper hidden without waiting.

The 15-second loop means **restart after the trader process exits**. It must not restart a healthy trader every 15 seconds. If the startup log shows a new start every 15 seconds, the Python process is crashing or preflight is rejecting it; diagnose that actual error.

The wrapper itself must also be started automatically after login/reboot and remain present across updater-driven process replacement. Register it through the repository's currently approved competition-watchdog mechanism. If no single approved mechanism exists for the new trader, treat that as a launch blocker and obtain owner authorization for a narrowly scoped watchdog change; do not modify the frozen supervisor/updater.

After wiring, prove intentional stop semantics:

1. With no stop flag, killing the trader process causes one replacement after approximately 15 seconds.
2. With the stop flag present, the wrapper does not replace it.
3. Removing the flag and invoking the hidden launcher restores exactly one process.
4. Reboot/startup registration points to the hidden wrapper, not directly to Python or a visible console.

## 5. Required tests before merge

At minimum, add focused tests for:

- ownership permission and private import isolation;
- preflight success and each fatal failure;
- unique port and single-instance rejection;
- launch entry point and clean shutdown;
- after-hours process availability with entry suppression;
- two consecutive scheduler cycles;
- scheduler exception followed by a later successful cycle;
- SQLite/thread behavior used by the real scheduler;
- atomic cycle-health output without strategy leakage;
- flat restart and open-position restart recovery;
- official open/close and duplicate prevention;
- current and stale market evidence;
- no-entry behavior on insufficient evidence;
- roster, scoreboard, presentation, surface manifest, and Discord declarations;
- dashboard publication from an empty ledger;
- launcher retry and stop-flag behavior where practical.

Run focused tests and the full existing CI. A mocked one-cycle unit test is not a production launch test.

## 6. Deploy through the supported path

1. Work on a separate branch.
2. Commit only intended files.
3. Push and open a pull request.
4. Wait for every required CI check.
5. Merge normally; never force-push production history.
6. Let the existing automatic updater install the approved merge.
7. Read `state/supervisor-state.json` and require all of the following:
   - `deployed_sha` equals the approved merge;
   - `last_update_status` is `DEPLOYED` or `UP_TO_DATE`;
   - `rollback_result` is `NOT_NEEDED`;
   - supervisor heartbeat is current;
   - existing core services remain healthy.
8. Do not claim deployment from GitHub or local `HEAD` alone.

Old Discord upgrade cards and historical commit numbers are not evidence of an updater failure. The laptop receipt is authoritative for installation state.

## 7. Live launch sequence

Perform the cutover during a valid session when possible:

1. Confirm all existing traders' ports, cycle timestamps, positions, and wrappers before touching the new one.
2. Run the new trader's real preflight against the installed commit.
3. Run `python sync_discord_structure_public.py --apply` if that is still the supported public synchronizer; otherwise use the current declared synchronizer documented by the repository.
4. Verify the new category and all four channels by live Discord read-back.
5. Remove only the new trader's stale stop flag, if owner-authorized and safe.
6. Start the hidden retry wrapper, not a bare interactive Python process.
7. Confirm exactly one wrapper and exactly one trader runtime.
8. Confirm the assigned loopback port is listening.
9. Observe at least two consecutive cycle-health timestamps.
10. Confirm shared bars, quotes, and chain jobs are current and successful.
11. Query the official scoreboard and verify the new bot's clean initial state or correctly recovered state.
12. Run/observe the competition surface publisher and require acknowledged Discord message IDs for dashboard and held-position cards.
13. Confirm every existing trader still has a listener and advancing cycle/decision telemetry.
14. Test restart recovery while flat. If an open-position recovery test is required live, use an already-existing paper position—never manufacture one merely for acceptance.

## 8. Hard definition of `LIVE`

Do not say “live” until every applicable row is proven:

| Layer | Required production evidence |
|---|---|
| Code | Approved PR merged; exact merge SHA identified. |
| Installed | Laptop receipt names that SHA and reports `DEPLOYED`/`UP_TO_DATE`, rollback `NOT_NEEDED`. |
| Process | Exactly one runtime and persistent restart wrapper; unique port listening. |
| Scheduler | At least two consecutive current cycle timestamps; no repeating exception. |
| Evidence | Required bar, quote, and chain timestamps are current; capture jobs report success. |
| Decision | Current `COMPLETED`/`IDLE`/`ERROR` health and public-safe action; `NO_ACTION` is valid if current. |
| Referee | Bot ID accepted by neutral scoreboard; bankroll/generation/position recover correctly. |
| Discord | Category/channels exist; dashboard and held-position messages have acknowledged IDs. |
| Isolation | Existing traders continue listening and cycling; no shared port, state, or stop flag. |
| Persistence | A deliberate flat-state process exit is automatically recovered exactly once. |

There are three distinct states that must never be conflated:

- **Dead:** no process, no listener, or no advancing cycles.
- **Running but unhealthy:** process/listener exists, but cycles error, scheduler is stalled, or evidence is stale.
- **Healthy and flat:** cycles and evidence are current, and the strategy returns `NO_ACTION`.

Trade count is not a liveness signal. A trader can be healthy with zero trades. Conversely, an old trade in the ledger does not prove the trader is currently alive.

## 9. Production verification commands

Adjust the bot name, port, and health path. These commands are read-only except the explicit Discord `--apply` command in the launch sequence.

```powershell
# Installed commit and core health
Get-Content state/supervisor-state.json

# All assigned trader listeners
netstat -ano -p tcp | Select-String ':8892|:8893|:8894|:8895'

# Startup/crash loop
Get-Content state/<slug>-startup.log -Tail 100

# Current strategy-neutral health
Get-Content state/<slug>/cycle-health.json

# Shared evidence jobs
@'
import sqlite3
c = sqlite3.connect('state/local-information.db')
for row in c.execute("""
    SELECT job_name, started_at, finished_at, status, detail
    FROM job_runs
    WHERE job_name IN ('spy-bars-capture', 'spy-market-data-capture', 'competition-surfaces')
    ORDER BY id DESC LIMIT 20
"""):
    print(row)
'@ | python -

# Official state for every registered bot
@'
import scoreboard
c = scoreboard.connect_db()
for bot in scoreboard.BOTS:
    print(scoreboard.scoreboard_snapshot(c, bot))
'@ | python -

# Discord surface acknowledgements
@'
import sqlite3
c = sqlite3.connect('state/discord_surfaces.db')
for row in c.execute("SELECT * FROM surface_events ORDER BY id DESC LIMIT 30"):
    print(row)
'@ | python -
```

## 10. Failure diagnosis

### Port absent

Read `state/<slug>-startup.log`. Determine whether the wrapper is absent, the stop flag is present, preflight fails, imports fail, the port collides, or Python exits after launch. Do not alter the strategy to repair lifecycle wiring.

### Restart every 15 seconds

The wrapper is working and the child is dying. The final exception or preflight failure in the startup log is the cause. The delay is intentional crash-loop throttling.

### Port present but no trades

Check whether cycle timestamps advance. If they do, inspect public-safe action/reason telemetry and evidence timestamps. Current `NO_ACTION` means healthy and flat; stale timestamps or repeated exceptions mean unhealthy.

### Cycles fail only under the scheduler

Test thread ownership, especially SQLite connections created on the launch thread and used by a scheduler worker. Reproduce two real scheduled cycles, not only direct calls to `run_cycle()`.

### `INSUFFICIENT` repeats despite current quotes

Inspect every required input. Bars, chain, expiration, or selected-contract evidence may be stale or absent even when the quote is current. Confirm shared capture cadence matches the trader cadence.

### Dashboard exists but is stale or blank

Confirm roster registration, the competition-surface fingerprint, publisher job status, `discord_surfaces.db` events, and acknowledged message IDs. Persistent flat-state cards must publish without waiting for a trade.

### Works until the next merge/reboot

The process was launched manually instead of through a persistent hidden retry wrapper/startup mechanism, or the updater restart path does not re-arm that wrapper. Fix the exact launch registration; do not rewrite the updater.

### One new trader stops another

Check unique ports, process IDs, stop-flag names, state paths, module entry points, and launcher commands. Each trader must own all six independently.

## 11. Completion record

Before releasing the coordination lock, record:

- exact merge and deployed SHA;
- CI and focused test results;
- assigned port and owning process;
- at least two cycle timestamps;
- evidence job timestamps/status;
- scoreboard snapshot;
- Discord channel read-back and message IDs;
- restart-recovery result;
- unaffected-trader verification;
- every changed file;
- any disclosed gap that prevents the word `LIVE`.

Finish with `python ai_coordination.py finish ...` using the same actor. If any hard-live row is missing, call the trader `PARTIAL` or `BLOCKED`, leave an actionable handoff, and do not make the owner rediscover the missing wiring.

## 12. Keep this runbook current

Any pull request that changes trader registration, launch/watchdog behavior, official accounting, market evidence, Discord publishing, deployment receipts, or the definition of production health must update this file in the same change. New integration points must be added to Section 4 and the hard-live table before another trader is launched.
