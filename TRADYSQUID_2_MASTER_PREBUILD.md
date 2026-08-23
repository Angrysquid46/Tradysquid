# TRADYSQUID 2.0 — MASTER PRE-BUILD SPECIFICATION

**Status:** PRE-BUILD / AUDIT-ONLY  
**Purpose:** Single shared source of truth for the Tradysquid 2.0 rebuild before implementation begins.  
**Primary users:** Owner, Codex/ChatGPT, Claude Code  
**Rule:** This file is the project plan. Read it before doing anything. Do not rely on old conversations.

---

# 1. HOW TO USE THIS FILE

Until implementation is explicitly authorized:

1. **Codex reads this file first.**
2. Codex uses this file to generate or perform the required independent verification work.
3. Claude Code reads this same file before its pre-build audit.
4. Claude returns a self-contained audit/verification handoff.
5. Codex independently verifies Claude’s findings.
6. The owner resolves any remaining decisions.
7. Only then is implementation authorized.

While waiting, the owner may add requirements directly to this file.

Once implementation begins, this file remains the high-level design authority, while live execution state moves into the project governance files described later.

No agent may assume its old conversation context is newer or more authoritative than the project files.

---

# 2. ABSOLUTE PRE-BUILD STOP RULE

Until the owner explicitly authorizes implementation:

DO NOT:

- Create repository files.
- Edit repository files.
- Delete repository files.
- Commit.
- Push.
- Restructure the repository.
- Modify Discord.
- Create or delete Discord channels.
- Modify databases.
- Migrate data.
- Change credentials.
- Change API configuration.
- Change schedulers.
- Build BLACKTIDE.
- Build Claude’s trader.
- Modify old traders.
- Modify the backtester.
- Populate the Learning Center.
- Begin any build phase.

Read-only inspection and verification only.

---

# 3. PROJECT OBJECTIVE

Tradysquid is undergoing a true clean-slate rebuild.

This is not:

- a refactor of the old traders,
- an upgrade of previous strategies,
- a migration of previous learning,
- or preservation of previous trader history.

The old trading ecosystem is considered contaminated/untrusted because prior AI-generated work may contain:

- hallucinated assumptions,
- unverified data,
- modeled data presented too confidently,
- inconsistent backtest methodology,
- strategy contamination,
- conclusions whose provenance cannot be reconstructed,
- stale Discord/state plumbing,
- dead outputs that no longer have producers.

Tradysquid 2.0 should preserve only:

- the Tradysquid identity,
- verified useful connectivity,
- verified factual market data,
- a stripped strategy-neutral backtesting foundation,
- minimal generic runtime infrastructure that is independently useful.

Everything else is subject to removal after authorization.

---

# 4. COMPLETE LEGACY TRADER PURGE

After final authorization, remove all previous:

- traders,
- strategies,
- strategy variants,
- entry logic,
- exit logic,
- strategy configs,
- learned thresholds,
- learned weights,
- models,
- training outputs,
- Champion/Challenger systems,
- shadow systems,
- evolve/self-learning systems,
- trading journals,
- winner/loser history,
- position history,
- trade history,
- performance history,
- rankings,
- recommendations,
- research conclusions,
- generated strategy reports,
- old trader state,
- old trader Discord state,
- old trader Discord routes/cards/channels,
- tests that exist only for deleted traders,
- compatibility code that exists only for dead trader systems.

No old trader becomes a template.

No old strategy result becomes starting knowledge for either new competitor.

During audit: identify these resources, but do not delete them.

---

# 5. WHAT MAY SURVIVE

Potential survivors must be verified.

## 5.1 Project identity
Keep Tradysquid.

## 5.2 Verified connections
Potentially preserve:

- GitHub connectivity,
- Discord connectivity/authentication,
- market-data connectivity,
- brokerage/quote connectivity,
- environment loading,
- credential plumbing,
- required runtime connection logic.

Never expose secrets.

## 5.3 Verified factual market data
Retain only historical observations whose provenance and limitations can be established.

## 5.4 Generic backtest foundation
Retain only strategy-neutral machinery.

## 5.5 Minimal generic runtime
Retain only infrastructure independently useful without old trader logic.

Existing code is not preserved merely because it already exists.

---

# 6. KEEP THE LABORATORY, DELETE THE OLD ANSWERS

Useful neutral backtest machinery may survive.

Old conclusions do not.

Do not inherit:

- win rates,
- P/L tables,
- optimized parameters,
- strategy rankings,
- champion selections,
- prior AI recommendations,
- conclusions that old strategies “worked.”

Every new competitor establishes its own fresh evidence.

---

# 7. TWO INDEPENDENT COMPETING TRADERS

Tradysquid 2.0 will contain two independent AI-controlled traders.

## 7.1 BLACKTIDE
**Name:** BLACKTIDE  
**Machine ID:** `BLACKTIDE_SPY`  
**Subtitle:** `Autonomous SPY Options Evolution Engine`  
**Owner:** ChatGPT/Codex

BLACKTIDE already has a private independently designed strategy specification.

Claude must not:

- request BLACKTIDE strategy details,
- inspect BLACKTIDE-private strategy files,
- infer BLACKTIDE logic from private research,
- copy BLACKTIDE,
- modify BLACKTIDE,
- train from BLACKTIDE-private conclusions,
- use BLACKTIDE’s implementation as a template.

## 7.2 Claude competitor
Claude will independently design its own trader from scratch.

Claude has broad strategic freedom within immutable rules.

ChatGPT/Codex must likewise not modify or consume Claude-private strategy intelligence.

## 7.3 Shared facts, private brains
Both traders may share neutral factual infrastructure.

They may share:

- SPY observations,
- option-chain observations,
- market calendar,
- factual event timestamps,
- deterministic neutral features,
- backtest engine,
- execution simulator,
- data-quality infrastructure,
- API manager,
- market cache,
- neutral scorekeeper,
- Discord transport.

They may not share:

- entry logic,
- exit logic,
- learned thresholds,
- learned weights,
- private models,
- private research conclusions,
- private evolution logic,
- future trade reasoning,
- opponent postmortem intelligence.

---

# 8. IMMUTABLE COMPETITION RULES

These eventually live outside evolvable bot configuration and must be code-enforced.

## Product
SPY options.

Initial scope:

- long 0DTE CALLS,
- long 0DTE PUTS,
- buy to open,
- sell to close.

## Starting bankroll
Each generation starts with exactly:

`$1,000`

## Hard position cap
Per bot:

`MAX_OPEN_TRADES = 1`

Absolute.

Multiple contracts of the exact same selected option position may count as one trade.

No simultaneous independent positions.

## No live shadow trading
No hidden continuously monitored option positions.

No parallel private paper portfolio.

Blocked setups may store lightweight factual state snapshots only.

## No lookahead
Absolute.

## Realistic paper execution
No hindsight fills.

No magical future-aware pricing.

No fake liquidity.

## Permanent official history
Completed official trades cannot later be erased because the bot evolves.

## Generation reset
When a generation busts or cannot afford a legitimate qualifying trade:

- freeze the generation,
- preserve official trades,
- preserve that bot’s legitimate learning,
- produce a postmortem,
- record the bust,
- reset bankroll to `$1,000`,
- begin the next generation.

Money resets.

History does not.

---

# 9. ULTRA-COMPETITIVE CULTURE

The competition is a core system feature.

Both traders are expected to relentlessly attempt to finish #1.

Each should independently optimize for:

- bankroll growth,
- expectancy,
- profit factor,
- drawdown control,
- survival,
- bust frequency,
- generation-over-generation improvement,
- adaptation across SPY regimes.

Within immutable rules, strategic freedom is intentionally broad.

Neither bot receives sympathy points.

Neither gets strategic handicaps.

Neither may rewrite the rules because it is losing.

Neither gets access to the other bot’s private intelligence.

The shared infrastructure acts as referee.

The neutral scorekeeper acts as judge.

The market decides who actually performed better.

---

# 10. NEUTRAL COMPETITION SCOREBOARD

Authoritative competition accounting must live outside both private traders.

Potential public metrics:

- current bankroll,
- current generation,
- lifetime P/L,
- generation P/L,
- lifetime trades,
- generation trades,
- win rate,
- profit factor,
- expectancy,
- average winner,
- average loser,
- largest winner,
- largest loser,
- max drawdown,
- current drawdown,
- bust count,
- winning streak,
- losing streak,
- best generation,
- worst generation,
- generation-over-generation improvement,
- current open-position status,
- current competition leader.

Actual money/performance is primary.

Neither trader may alter authoritative competition results.

---

# 11. DISCORD RIVALRY SYSTEM

Create one dedicated rivalry channel during the Discord rebuild.

Conceptual name:

`#blacktide-vs-claude`

Purpose:

- head-to-head results,
- trade-close reactions,
- lead changes,
- busts,
- milestones,
- generation results,
- trash talk,
- bot-to-bot replies.

This channel is separate from operational trade channels.

---

# 12. RIVALRY PERSONAS ACTUALLY READ EACH OTHER

The rivalry system should not be two independent canned insult generators.

Each bot’s **rivalry persona layer** may read:

- official public competition facts,
- the opponent’s exact public rivalry message,
- relevant recent rivalry history,
- prior public boasts/promises,
- public score snapshots.

The **trading brain must not read rivalry messages**.

Conceptual flow:

```text
OFFICIAL EVENT
    ↓
NEUTRAL SCOREKEEPER UPDATE
    ↓
RIVALRY EVENT
    ↓
BOT A RIVALRY PERSONA
    ↓
BOT A POSTS
    ↓
BOT B RIVALRY PERSONA READS:
    - SAME PUBLIC FACTS
    - BOT A'S EXACT MESSAGE
    - RELEVANT PUBLIC BANTER HISTORY
    ↓
BOT B RESPONDS
    ↓
BOT A MAY RESPOND AGAIN
    ↓
FINITE EVENT WINDOW CLOSES
```

This allows genuine callbacks and contextual replies.

---

# 13. PUBLIC RIVALRY MEMORY

Maintain a dedicated public rivalry history.

Possible record fields:

- `rivalry_event_id`
- timestamp
- trigger
- speaker
- target
- message
- public score snapshot
- trade result reference
- generation
- reply-to message ID
- conversation round
- callbacks used
- Discord message ID

The rivalry layer may retrieve relevant public history such as:

- previous boasts,
- prior lead-change comments,
- prior bust jokes,
- comeback promises,
- streak taunts,
- previous score differences.

This allows running jokes and callbacks based on actual results.

Rivalry history is presentation history only.

It must never become private trading-strategy training data.

---

# 14. RIVALRY EVENT TRIGGERS

Potential triggers:

- `SESSION_OPEN`
- `FIRST_WIN_OF_DAY`
- `FIRST_LOSS_OF_DAY`
- `TRADE_CLOSED_WIN`
- `TRADE_CLOSED_LOSS`
- `NEW_COMPETITION_LEADER`
- `LEAD_EXTENDED`
- `LEAD_LOST`
- `BANKROLL_MILESTONE`
- `NEW_BEST_TRADE`
- `NEW_WORST_TRADE`
- `WINNING_STREAK`
- `LOSING_STREAK`
- `DRAWDOWN_RECOVERY`
- `MAJOR_COMEBACK`
- `GENERATION_BUSTED`
- `GENERATION_RECORD`
- `GENERATION_COMPLETED`
- `SESSION_WINNER`
- `LIFETIME_LEADER_CHANGE`

---

# 15. RIVALRY MESSAGE BUDGET

Initial internal design targets:

```text
RIVALRY_MAX_MESSAGES_PER_BOT_PER_EVENT = 3
RIVALRY_MAX_MESSAGES_PER_BOT_PER_DAY = 20
RIVALRY_MAX_TOTAL_MESSAGES_PER_MINUTE = 6
RIVALRY_MIN_MESSAGE_GAP_SECONDS = 20
RIVALRY_OPEN_POSITION_CHAT = false
RIVALRY_PRIVATE_STRATEGY_ACCESS = false
RIVALRY_CAN_INFLUENCE_TRADING = false
```

These are internal targets, not claims about Discord hard platform limits.

The pre-build audit must verify actual Discord behavior and recommend safe final values.

The internal limits should remain comfortably below actual platform limits.

---

# 16. EVENT-BASED RIVALRY CHAINS

A qualifying event may allow bounded back-and-forth.

Example:

Bot A posts.

Bot B responds.

Bot A comes back.

Bot B may respond again if the event budget allows.

Then the event closes.

Every exchange uses a stable `rivalry_event_id`.

No infinite autonomous reply loops.

Default maximum:

`3 messages per bot per event`

subject to daily and per-minute caps.

---

# 17. SESSION OPEN / CLOSE BANTER

To keep the rivalry alive on low-trade days:

## Session open
Each bot may post at most one opening rivalry message based only on public scoreboard state.

## Session close
Each bot may post at most one closing rivalry message based on official session results.

No continuous idle chatter.

---

# 18. NO OPEN-POSITION BANTER

Default:

`RIVALRY_OPEN_POSITION_CHAT = false`

Do not generate rivalry chatter while positions are open.

This prevents:

- live strategy leakage,
- revenge-trading pressure,
- unnecessary noise,
- presentation affecting execution.

---

# 19. TRASH TALK SHOULD USE REAL RESULTS

Prefer specific result-based commentary.

Approved public ammunition includes:

- trade P/L,
- bankroll difference,
- streak,
- drawdown,
- lead size,
- generation,
- bust count,
- profit factor,
- session winner,
- comeback status,
- prior public boasts.

The better the rivalry memory, the more specific the callback can be.

Example tone:

> “The competition remains close if you remove the money.”

> “That victory speech lasted longer than the trade.”

> “You said I could talk when I retook first place. I’m trying to respect your instructions.”

The exact language should be dynamically generated from public facts.

---

# 20. RIVALRY MUST NEVER AFFECT TRADING

Absolute rule.

The rivalry subsystem must never:

- trigger trades,
- change sizing,
- alter entries,
- alter exits,
- alter risk,
- influence evolution,
- cause revenge trading,
- consume meaningful market-data priority,
- expose opponent-private strategy information.

Trading decisions remain entirely private and strategy-driven.

Trash talk reacts to outcomes.

It does not create them.

---

# 21. RIVALRY DATA BOUNDARY

Allowed public inputs:

- public bankroll,
- official closed trade result,
- public ranking,
- public streak,
- public drawdown,
- public generation,
- public bust count,
- public milestone,
- public rivalry messages.

Forbidden:

- opponent private signals,
- opponent private features,
- thresholds,
- model scores,
- intended trades,
- private research,
- private evolution logic.

---

# 22. API LIMITS MUST BE VERIFIED

Current owner estimate:

`~120 requests/minute`

This is provisional.

Audit must determine:

- active provider,
- SPY quote provider,
- option-chain provider,
- Greeks provider,
- historical provider,
- REST limits,
- streaming limits,
- quota separation,
- endpoint-specific limits,
- burst behavior,
- retry behavior,
- header telemetry,
- full-chain request behavior,
- account-tier differences.

Classify findings:

`VERIFIED`

`ASSUMED`

`UNKNOWN`

---

# 23. SHARED API RESOURCE PRIORITY

Future priority:

1. open-position safety,
2. exit-critical data,
3. entry-critical data,
4. shared SPY data,
5. shared options collection,
6. secondary context,
7. nonessential research,
8. rivalry presentation.

Rivalry must never compete with trade safety or factual collection.

---

# 24. ONE FACT, MANY READERS

Preferred architecture:

```text
SHARED MARKET SERVICE
        ↓
FACTUAL OBSERVATION
        ↓
BLACKTIDE
CLAUDE
DATA ARCHIVE
BACKTEST
SCOREBOARD
DISCORD
```

Avoid redundant identical provider calls.

---

# 25. NEW TRUSTED DATA ERA

Tradysquid 2.0 should accumulate its own factual market history every trading day whether either bot trades or not.

This becomes a long-term Tier-A research asset.

---

# 26. DAILY SPY COLLECTION

Target where available:

- timestamp,
- 1-minute OHLCV,
- bid,
- ask,
- last,
- bid size,
- ask size,
- provider timestamp,
- receive timestamp,
- premarket,
- regular session,
- provider,
- collector version.

Streaming preferred where reliable and efficient.

---

# 27. DAILY SPY 0DTE COLLECTION

Target approximately one useful full same-day-expiration SPY option-chain snapshot per regular-session minute if provider/API behavior permits.

Store where available:

- snapshot_id
- market_timestamp
- received_at
- SPY bid
- SPY ask
- SPY last
- option_symbol
- expiration
- strike
- side
- bid
- ask
- bid_size
- ask_size
- last
- volume
- open_interest
- IV
- Delta
- Gamma
- Theta
- Vega
- provider
- provider_timestamp
- collector_version

---

# 28. APPEND-ONLY MARKET HISTORY

Never overwrite earlier intraday snapshots with later observations.

Audit current collector overwrite/delete behavior.

---

# 29. STORAGE ARCHITECTURE

Preferred:

## Parquet
Immutable high-volume factual history.

Partition approximately:

`instrument/year/month/trading_day`

## DuckDB
Research/backtesting/query layer over Parquet.

## SQLite
Small operational state only where useful.

Audit:

- dependencies,
- filesystem compatibility,
- storage growth,
- integration difficulty.

---

# 30. RAW DATA IMMUTABILITY

Future hierarchy:

```text
RAW OBSERVATIONS
        ↓
NORMALIZATION
        ↓
VERSIONED NEUTRAL FEATURES
        ↓
BACKTEST / RESEARCH
        ↓
PRIVATE BOT INTELLIGENCE
```

Raw evidence remains immutable.

---

# 31. DATA CLASSIFICATION

Use:

`VERIFIED_REAL`

`REAL_WITH_LIMITATIONS`

`MODELED`

`UNKNOWN_PROVENANCE`

`REJECTED`

Never silently mix modeled and observed information.

---

# 32. DAILY DATA MANIFEST

Eventually track:

- expected SPY minutes,
- received SPY minutes,
- expected chain snapshots,
- received snapshots,
- option rows,
- missing periods,
- stream gaps,
- API errors,
- rate-limit events,
- duplicates,
- invalid observations,
- collector version,
- data grade.

Grades:

`A`

`B`

`C`

`REJECT`

---

# 33. BACKTEST EVIDENCE TIERS

## Tier A
Real SPY + real timestamped option observations.

## Tier B
Real SPY + modeled option pricing.

Every Tier-B report must display:

`OPTION PRICING MODELED`

## Tier C
Required evidence unavailable.

Return:

`INSUFFICIENT DATA`

---

# 34. POINT-IN-TIME BACKTESTING

Conceptual interface:

`market.as_of(timestamp)`

`options.as_of(timestamp)`

`events.as_of(timestamp)`

Strategies at time `T` must be structurally unable to access future information.

---

# 35. REAL CONTRACT RESOLUTION

Tier-A backtests may use only contracts that actually existed at the simulated point in time.

No hindsight contract creation.

---

# 36. SHARED NEUTRAL FEATURES

Potential shared factual features:

- VWAP,
- ATR,
- returns,
- realized volatility,
- relative volume,
- previous-day levels,
- previous-week levels,
- opening ranges,
- higher-timeframe bars,
- basic causal structure measurements.

Shared features must be:

- deterministic,
- causal,
- versioned,
- reproducible,
- strategy-neutral.

---

# 37. REPRODUCIBLE BACKTEST RECEIPTS

Formal backtests should preserve:

- bot,
- strategy version,
- engine version,
- dataset fingerprint,
- date range,
- evidence tier,
- data quality,
- feature versions,
- execution assumptions,
- parameters,
- random seed where relevant,
- results,
- timestamp.

Same code + data + config + assumptions + seed should reproduce the same result.

---

# 38. OWNERSHIP CLASSES

Future ownership classes:

`SHARED_CORE`

`SHARED_DATA`

`BLACKTIDE_ONLY`

`CLAUDE_ONLY`

`HUMAN_LEARNING_CENTER`

No ambiguous ownership.

---

# 39. OWNERSHIP MANIFEST

Future machine-readable ownership manifest should record:

- path,
- owner,
- readers,
- writers,
- protected,
- purpose.

Conceptual intent:

```text
/shared/*          -> SHARED_CORE
/data/*            -> SHARED_DATA
/bots/blacktide/*  -> BLACKTIDE_ONLY
/bots/claude/*     -> CLAUDE_ONLY
/learning/*        -> HUMAN_LEARNING_CENTER
```

---

# 40. HARD WRITE GUARDS

Protected writes should verify:

1. actor,
2. target,
3. ownership,
4. permission,
5. allow/reject,
6. log violations.

Competitors cannot modify each other.

Neither autonomously changes immutable contest law.

---

# 41. AGENT INSTRUCTION HIERARCHY

Future root:

`AGENTS.md`

for global Tradysquid rules.

Scoped instructions for private bot areas.

Audit current:

- AGENTS.md,
- CLAUDE.md,
- collaboration docs,
- project status docs,
- conflicting instructions.

Do not edit during pre-build audit.

---

# 42. CROSS-AGENT PROJECT MEMORY

Tradysquid must not depend on old conversations.

The repository itself must explain:

- what exists,
- what version,
- what phase,
- what changed,
- who changed it,
- why,
- what was fixed,
- what was added,
- what was removed,
- what tests passed,
- what failed,
- what remains unfinished,
- where interrupted work stopped,
- what comes next,
- who owns what,
- which Discord surfaces depend on what,
- whether they are synchronized.

Private strategy intelligence remains isolated.

Shared architecture stays fully synchronized.

---

# 43. PROJECT_STATE

Future canonical current-state file:

`governance/PROJECT_STATE.yaml`

Should contain current:

- architecture version,
- branch,
- commit,
- last verified commit,
- last update,
- current phase,
- active work,
- component versions,
- component health,
- schema versions,
- provider/API config,
- data health,
- Discord health,
- competition/scoreboard status,
- rivalry status,
- Learning Center status,
- public bot statuses,
- known defects,
- blockers,
- pending validation,
- last test result,
- next safe action.

Current truth only.

---

# 44. CHANGELOG

Future append-only structured history:

`governance/CHANGELOG.jsonl`

Every meaningful change should include:

- change_id,
- timestamps,
- actor,
- phase,
- owner request,
- before state,
- reason,
- planned change,
- expected files,
- actual files,
- schemas affected,
- Discord surfaces affected,
- competition/rivalry surfaces affected,
- data/runtime effects,
- tests required,
- tests run,
- results,
- errors,
- what fixed,
- what added,
- what removed,
- behavior before,
- behavior after,
- remaining work,
- commits,
- status.

Statuses:

`COMPLETED`

`PARTIAL`

`FAILED`

`REVERTED`

`SUPERSEDED`

---

# 45. ACTIVE_HANDOFF

Future work checkpoint:

`governance/ACTIVE_HANDOFF.yaml`

Track:

- work_id,
- actor,
- requested goal,
- phase,
- planned steps,
- completed steps,
- current step,
- files touched,
- files remaining,
- last successful action,
- last command/test,
- last result,
- current error,
- discoveries,
- assumptions,
- uncommitted state,
- unsafe-to-repeat steps,
- safe-to-repeat steps,
- next safe step,
- completion criteria.

This enables Claude ↔ Codex continuation without old conversation context.

---

# 46. READ BEFORE WRITE

Once implementation begins, every Claude or Codex work session must first read:

1. global governance,
2. ownership manifest,
3. PROJECT_STATE,
4. ACTIVE_HANDOFF,
5. relevant recent CHANGELOG entries,
6. scoped instructions.

Conversation memory is not authoritative project state.

---

# 47. BEFORE / AFTER CHANGE RECORDING

Before non-trivial changes record:

- owner request,
- current state,
- intended scope,
- reason,
- expected files,
- schema effects,
- Discord effects,
- competition/rivalry effects,
- tests,
- risks.

After work, applicable project records and dependent surfaces must be synchronized.

Otherwise the work remains:

`INCOMPLETE`

---

# 48. INTERRUPTION RECOVERY

If either AI stops halfway through work, the next authorized AI must be able to determine:

- requested scope,
- completed scope,
- partial work,
- unstarted work,
- last successful action,
- current failure,
- next safe step.

No owner reconstruction should be required.

---

# 49. CONCURRENCY PROTECTION

Audit and later implement the simplest reliable mechanism preventing Claude and Codex from editing conflicting shared systems simultaneously.

Potential mechanisms:

- project lock,
- scoped subsystem locks,
- active-work declarations,
- ownership locks,
- branch rules,
- atomic state writes,
- commit validation.

---

# 50. PROJECT STATE MUST MATCH GIT

Where practical:

`PROJECT_STATE.current_commit`

must match the repository state it describes.

If Git materially changes without synchronized project state:

`PROJECT_STATE_STALE`

No agent should blindly continue.

---

# 51. DISCORD COMPLETE REBUILD

Old trading Discord architecture will eventually be gutted.

Preserve only minimal verified generic connectivity.

Audit:

- authentication,
- connection,
- categories/channels,
- routes,
- persistent cards,
- queueing,
- editing,
- deduplication,
- retries,
- rate-limit handling,
- failure coupling,
- desynchronization.

Do not modify Discord during pre-build audit.

---

# 52. DISCORD EVENT ARCHITECTURE

Future:

```text
SYSTEM/TRADER STATE
        ↓
STRUCTURED EVENTS
        ↓
SHARED DISCORD PUBLISHER
```

Includes:

- trading events,
- system events,
- scoreboard events,
- rivalry events,
- data events.

---

# 53. DISCORD SYNCHRONIZATION INVARIANT

Every dynamic surface requires:

- owner,
- purpose,
- data source,
- producer,
- publisher,
- event/update trigger,
- expected behavior,
- health.

No orphan dynamic surfaces.

---

# 54. DISCORD SURFACE MANIFEST

Track:

- surface ID,
- category,
- channel,
- owner,
- purpose,
- data source,
- producer,
- publisher,
- events,
- update mode,
- expected silence,
- persistent message IDs,
- schema,
- enabled state,
- health,
- last event,
- last update,
- last publish,
- last error.

Include rivalry and scoreboard surfaces.

---

# 55. DISCORD DEPENDENCY RULE

When a feature changes, every dependent Discord surface must be:

`UPDATED`

`VERIFIED_UNAFFECTED`

or:

`RETIRED`

No forgotten tabs/channels.

---

# 56. DISCORD RECOVERY

Persistent surfaces rebuild from authoritative state.

Do not wait for a future trade to wake up a stale dashboard.

Reconcile after appropriate:

- startup,
- deployment,
- reconnect,
- schema changes,
- channel creation,
- migrations.

---

# 57. DISCORD HEALTH STATES

Use distinctions such as:

`HEALTHY`

`QUIET_VALID`

`NO_DATA_EXPECTED`

`STALE`

`PRODUCER_OFFLINE`

`PUBLISH_FAILED`

`DESYNCHRONIZED`

`MISCONFIGURED`

A quiet channel because there were no trades is healthy.

A quiet channel because the producer died is not.

---

# 58. FAILURE ISOLATION

Ensure:

- Discord failure does not stop trading,
- rivalry failure does not stop trading,
- BLACKTIDE failure does not stop Claude,
- Claude failure does not stop BLACKTIDE,
- backtest failure does not stop market collection,
- Learning Center failure does not affect competition.

---

# 59. HUMAN LEARNING CENTER

Tradysquid includes a comprehensive human options education system.

It is NOT autonomous trading intelligence.

Humans and the human-facing Q&A assistant may use it.

Autonomous competitors may not.

---

# 60. LEARNING CENTER LAYOUT

One Discord category:

`LEARNING CENTER`

with:

`#learning-index`

and one chapter channel from:

`#01-...`

through:

`#43-...`

One channel per chapter.

Use however many messages/cards each chapter requires.

---

# 61. LEARNING CENTER QUALITY

Do not skimp.

Each chapter may contain:

- overview,
- objectives,
- topic index,
- definitions,
- detailed explanations,
- mechanics,
- mathematics,
- Greeks,
- volatility,
- risk/reward,
- exercise,
- assignment,
- expiration,
- worked examples,
- P/L examples,
- practical use,
- failure cases,
- mistakes,
- cross-links,
- summary.

---

# 62. LEARNING CENTER CURRICULUM

1. Definitions
2. Covered Call Writing
3. Call Buying
4. Other Call Buying Strategies
5. Naked Call Writing
6. Ratio Call Writing
7. Bull Spreads Using Call Options
8. Bear Spreads Using Call Options
9. Calendar Spreads
10. Butterfly Spread
11. Ratio Call Spreads
12. Combining Calendar and Ratio Spreads
13. Reverse Spreads
14. Diagonalizing a Spread
15. Put Option Basics
16. Put Option Buying
17. Put Buying in Conjunction with Stock Ownership
18. Buying Puts in Conjunction with Call Purchases
19. The Sale of a Put
20. The Sale of a Straddle
21. Synthetic Stock Positions Created by Puts and Calls
22. Basic Put Spreads
23. Spreads Combining Calls and Puts
24. Ratio Spreads Using Puts
25. Long-Term Option Strategies / LEAPS
26. Buying Options and Treasury Bills
27. Arbitrage
28. Mathematical Applications
29. Introduction to Index Option Products and Futures
30. Stock Index Hedging Strategies
31. Index Spreading
32. Structured Products
33. Mathematical Considerations for Index Products
34. Futures and Futures Options
35. Futures Option Strategies for Futures Spreads
36. The Basics of Volatility Trading
37. How Volatility Affects Popular Strategies
38. The Distribution of Stock Prices
39. Volatility Trading Techniques
40. Advanced Concepts
41. Volatility Derivatives
42. Taxes
43. The Best Strategy?

Additional references:

- strategy summaries,
- equivalent positions,
- formulas,
- P/L graphs,
- qualified covered calls,
- portfolio margin,
- glossary,
- index.

The curriculum may comprehensively teach all listed subjects using original explanations, original examples, mathematics, diagrams, and updated factual information.

---

# 63. LEARNING CENTER INDEX / Q&A

Every lesson eventually gets a stable identifier such as:

`LC-17-04`

with:

- chapter,
- lesson,
- topics,
- keywords,
- related concepts,
- Discord channel,
- message ID,
- jump link,
- version,
- publication state.

Human Q&A can search and link directly to lessons.

---

# 64. LEARNING CENTER FIREWALL

Autonomous traders may not:

- import it,
- search it,
- query it,
- train from it,
- use educational strategy content.

Human educational systems may.

---

# 65. SOURCE CONTROL POLICY

GitHub should eventually contain:

- source,
- tests,
- governance,
- schemas,
- small templates,
- required docs.

Not:

- secrets,
- huge market archives,
- runtime DBs,
- logs,
- caches,
- temporary files,
- random backups,
- old trader fossils.

---

# 66. DATA BACKUP

Future backup should protect:

- raw SPY,
- raw options,
- manifests,
- data catalog.

Audit realistic options before implementation.

---

# 67. CONCEPTUAL REPOSITORY SHAPE

```text
Tradysquid/
│
├── AGENTS.md
├── README.md
│
├── governance/
│   ├── PROJECT_STATE.yaml
│   ├── ACTIVE_HANDOFF.yaml
│   ├── CHANGELOG.jsonl
│   ├── OWNERSHIP.*
│   ├── IMMUTABLE_RULES.*
│   ├── SCHEMAS.*
│   └── CHANGE_POLICY.*
│
├── shared/
│   ├── market/
│   ├── options/
│   ├── backtest/
│   ├── features/
│   ├── execution/
│   ├── api_budget/
│   ├── competition/
│   ├── events/
│   └── discord/
│
├── data/
│   ├── raw/
│   ├── derived/
│   ├── manifests/
│   └── catalog/
│
├── learning/
│   ├── catalog/
│   ├── lessons/
│   ├── search/
│   └── references/
│
├── bots/
│   ├── blacktide/
│   └── claude/
│
├── tests/
│   ├── shared/
│   ├── isolation/
│   ├── competition/
│   └── learning/
│
└── runtime/
```

Conceptual only.

---

# 68. WORK DIVISION

Shared infrastructure is built once.

## Shared
- cleanup,
- governance,
- ownership,
- synchronization,
- data,
- storage,
- backtest,
- API manager,
- market cache,
- competition scorekeeper,
- event system,
- Discord,
- rivalry transport/presentation,
- Learning Center framework.

## ChatGPT/Codex
BLACKTIDE-private implementation.

## Claude
Claude-private implementation.

---

# 69. PROPOSED BUILD PHASES

These are not authorized yet.

## Phase 1 — Backup and freeze
Protect required connectivity/data and stop generating new legacy trader state.

## Phase 2 — Final inventory
Confirm exactly what survives and what dies.

## Phase 3 — Legacy purge
Remove previous traders and contaminated intelligence.

## Phase 4 — Governance and synchronization
Create:

- PROJECT_STATE,
- CHANGELOG,
- ACTIVE_HANDOFF,
- ownership manifest,
- immutable rules,
- schemas,
- agent instructions,
- write guards,
- concurrency locks.

## Phase 5 — Shared factual market-data architecture
Build:

- SPY collection,
- 0DTE option collection,
- Parquet archive,
- DuckDB query layer,
- manifests,
- data-quality grading.

## Phase 6 — Neutral point-in-time backtest laboratory

## Phase 7 — Shared runtime/API/cache/events

## Phase 8 — Neutral competition scorekeeper

## Phase 9 — Discord rebuild
Includes:

- synchronized surfaces,
- dashboards,
- scoreboards,
- rivalry channel,
- rivalry personas,
- public rivalry memory,
- health/reconciliation.

## Phase 10 — Learning Center shell
Create index and 43 chapter channels.

## Phase 11 — Independent bot ownership areas

## Phase 12 — BLACKTIDE implementation

## Phase 13 — Claude competitor implementation

## Phase 14 — Full validation
Validate:

- data,
- backtest,
- API,
- ownership,
- one-trade rule,
- competition accounting,
- rivalry isolation,
- rivalry message caps,
- Discord synchronization,
- failure isolation,
- cross-agent handoff,
- Learning Center firewall.

## Phase 15 — Competition launch
Both start:

`$1,000`

`0 inherited trades`

## Phase 16 — Full Learning Center population

---

# 70. PHASE COMPLETION RULE

Tradysquid is not considered fully built merely because the currently listed phases are complete.

At the end of every implementation phase:

1. Validate the phase.
2. Inspect the current system for newly revealed required work.
3. Check for:
   - missing dependencies,
   - broken integrations,
   - stale Discord surfaces,
   - unhandled failure modes,
   - missing tests,
   - ownership gaps,
   - schema gaps,
   - data-quality gaps,
   - operational gaps,
   - unfinished migration work,
   - new phases that became necessary because of discoveries.

If new required work exists:

- create a new explicit phase or subphase,
- log why it was discovered,
- assign dependencies,
- add completion criteria,
- continue.

Tradysquid 2.0 is only considered **BUILD COMPLETE** when:

- all known phases are completed,
- final validation passes,
- no required untracked phase remains,
- no unresolved blocker remains,
- no required integration is orphaned,
- no dynamic Discord surface is stale/unowned,
- project state and Git are synchronized,
- all required tests pass,
- both agents independently agree there is no remaining implementation phase required by the approved specification.

No artificial “done” declaration simply because the original phase list ended.

---

# 71. PRE-BUILD AUDIT REQUIRED OUTPUT

Claude’s pre-build audit should return a self-contained handoff to Codex covering:

## 1. Executive status
Choose:

`READY WITH NO MATERIAL CORRECTIONS`

`READY WITH CORRECTIONS`

`BLOCKED`

## 2. Current providers

## 3. Verified API limits

## 4. Market-data fields

## 5. Streaming

## 6. Verified historical datasets

## 7. Data to reject

## 8. Backtest baseline

## 9. Option-history reality

## 10. Daily collection feasibility

## 11. Storage estimate

## 12. Storage stack

## 13. API-budget architecture

## 14. Discord

## 15. Repository clean-slate map
Classify major areas:

`PURGE`

`PRESERVE`

`EXTRACT/NEUTRALIZE`

`UNKNOWN`

## 16. Governance / ownership

## 17. Learning Center

## 18. Competition / scoreboard / rivalry
Audit:

- neutral scorekeeper,
- immutable accounting,
- rivalry channel,
- event triggers,
- interactive public replies,
- rivalry memory,
- message limits,
- actual Discord-rate compatibility,
- no strategy leakage,
- no trading influence,
- low API priority.

Choose:

`RIVALRY ARCHITECTURE READY`

`RIVALRY ARCHITECTURE NEEDS CORRECTIONS`

`RIVALRY ARCHITECTURE BLOCKED`

## 19. Phase-order corrections

## 20. Blockers

## 21. Assumptions that were wrong

## 22. Verified constants for final spec

## 23. Final recommendation

## 24. Cross-agent synchronization
Cover:

- existing project-state files,
- contradictions,
- PROJECT_STATE recommendation,
- CHANGELOG recommendation,
- ACTIVE_HANDOFF recommendation,
- Git integration,
- atomic updates,
- concurrency,
- interruption recovery,
- Discord synchronization,
- competition-state synchronization,
- rivalry-state synchronization,
- strategy privacy,
- mechanical enforcement.

Choose:

`SYNC ARCHITECTURE READY`

`SYNC ARCHITECTURE NEEDS CORRECTIONS`

`SYNC ARCHITECTURE BLOCKED`

---

# 72. CODEX VERIFICATION AFTER CLAUDE RETURNS

When Claude’s audit is returned, Codex must independently verify the important claims.

Codex should return:

## VERIFIED
Claude findings independently confirmed.

## CORRECTIONS
Anything Claude got wrong.

## REMAINING UNKNOWNS
Anything still unresolved.

## FINAL HARD CONSTANTS
Verified values ready for governance.

## FINAL COMPETITION RULES

## FINAL RIVALRY RULES
Including final values for:

- messages per bot per event,
- messages per bot per day,
- total rivalry messages per minute,
- minimum rivalry message gap,
- session-open/session-close behavior,
- open-position-chat behavior.

## FINAL ARCHITECTURE CHANGES

## FINAL PHASE ORDER

## BUILD READINESS

Choose exactly:

`READY_TO_BUILD`

`READY_AFTER_OWNER_DECISION`

`NOT_READY`

Even `READY_TO_BUILD` does not itself authorize implementation.

The owner explicitly authorizes the build.

---

# 73. REQUIRED PRE-BUILD WORKFLOW

Until build authorization:

```text
OWNER UPDATES THIS MASTER FILE
        ↓
CODEX READS MASTER FILE
        ↓
CLAUDE READS MASTER FILE
        ↓
CLAUDE PERFORMS READ-ONLY AUDIT
        ↓
CLAUDE RETURNS SELF-CONTAINED HANDOFF
        ↓
CODEX INDEPENDENTLY VERIFIES
        ↓
OWNER RESOLVES REMAINING DECISIONS
        ↓
FINAL BUILD SPEC LOCKED
        ↓
OWNER AUTHORIZES IMPLEMENTATION
```

---

# 74. REQUIRED IMPLEMENTATION WORKFLOW

After build authorization:

```text
READ GOVERNANCE
        ↓
READ OWNERSHIP
        ↓
READ PROJECT_STATE
        ↓
READ ACTIVE_HANDOFF
        ↓
READ RELEVANT CHANGELOG
        ↓
CLAIM WORK / LOCK SCOPE
        ↓
RECORD BEFORE STATE
        ↓
IMPLEMENT
        ↓
TEST
        ↓
CHECK DISCORD DEPENDENCIES
        ↓
CHECK NEWLY REVEALED PHASES
        ↓
UPDATE PROJECT_STATE
        ↓
APPEND CHANGELOG
        ↓
UPDATE ACTIVE_HANDOFF
        ↓
COMMIT/VERIFY
        ↓
NEXT AGENT CAN CONTINUE
```

---

# 75. SINGLE-SOURCE-OF-TRUTH RULE

Before implementation, this file is the single shared design source.

After implementation begins:

- this file remains the high-level approved design/specification,
- `PROJECT_STATE` becomes current operational truth,
- `CHANGELOG` becomes historical change truth,
- `ACTIVE_HANDOFF` becomes unfinished-work truth,
- ownership/governance files define write authority.

Do not create separate Claude and Codex versions of project truth.

---

# 76. OWNER ADDITIONS / PENDING IDEAS

The owner may add new pre-build requirements below this line before build authorization.

Every agent reading this file must treat additions here as part of the current pre-build plan unless they conflict with an explicit later owner decision.

## Pending additions

- None currently.

---

# FINAL INTENT

Tradysquid 2.0 should ultimately contain:

- no inherited trader intelligence,
- verified factual shared market data,
- permanent daily SPY/0DTE collection,
- Parquet raw storage,
- DuckDB analytics,
- strategy-neutral point-in-time backtesting,
- shared API budgeting,
- realistic execution,
- one official position per bot,
- no live shadow trading,
- immutable official trade history,
- BLACKTIDE private to ChatGPT/Codex,
- Claude trader private to Claude,
- both relentlessly competing to finish #1,
- neutral competition accounting,
- public head-to-head scoreboard,
- dedicated rivalry Discord channel,
- interactive event-driven bot banter,
- rivalry personas that actually read and answer each other,
- public rivalry memory and callbacks,
- bounded rivalry response chains,
- no rivalry-driven trading,
- no strategy leakage through rivalry,
- hard file ownership,
- cross-agent project memory,
- before/after change history,
- recoverable interrupted work,
- fully synchronized Discord surfaces,
- no orphan channels,
- human-facing 43-chapter Learning Center,
- educational Q&A with direct lesson links,
- hard Learning Center/trader firewall,
- reproducible project state,
- reproducible research,
- phase discovery until no required phase remains,
- explicit owner authorization before implementation.

The shared system remains synchronized.

The strategies remain private.

The rivalry remains vicious.

The evidence remains honest.

The project itself remembers.
