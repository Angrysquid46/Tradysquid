# TRADYSQUID 2.0 — MASTER PRE-BUILD SPECIFICATION

**Status:** PRE-BUILD / AUDIT-ONLY  
**Purpose:** Single shared source of truth for the Tradysquid 2.0 clean-slate rebuild.  
**Readers:** Owner, Codex/ChatGPT, Claude Code  
**Authority:** Read this file before doing anything. Do not rely on old conversation context when repository state is available.

---

# 1. PRE-BUILD WORKFLOW AND STOP RULE

Until the owner explicitly authorizes implementation:

1. Codex reads this file.
2. Claude Code reads this same file and performs the required read-only audit.
3. Claude returns a self-contained audit handoff.
4. Codex independently verifies the important claims.
5. The owner resolves remaining decisions.
6. Only then does implementation begin.

Before implementation authorization, do **not** create/edit/delete project files, commit/push, restructure the repo, modify Discord, migrate data, change credentials/API config/schedulers, build either trader, modify the backtester, or populate the Learning Center, except when the owner explicitly edits this master specification itself.

---

# 2. CLEAN-SLATE OBJECTIVE

Tradysquid 2.0 is not a refactor or migration of old trader intelligence.

The old trading ecosystem is untrusted because prior AI work may contain hallucinated assumptions, modeled data presented too confidently, inconsistent backtests, stale state, dead Discord surfaces, or conclusions whose provenance cannot be reconstructed.

After authorization, purge old trader intelligence including:

- traders and strategy variants;
- entries/exits/configs;
- learned thresholds/weights/models/training outputs;
- champion/challenger, shadow, evolve, and self-learning systems;
- journals, winners, losers, trades, positions, rankings, recommendations, performance history;
- old strategy research conclusions and generated result reports;
- trader-specific Discord state/routes/cards/channels;
- tests and compatibility code that exist only for deleted traders.

No old trader becomes a template. No old strategy result becomes starting knowledge for either new competitor.

Potential survivors must be independently verified:

- Tradysquid identity;
- working GitHub/Discord/market-data/broker/env/credential plumbing;
- verified factual historical market data;
- strategy-neutral backtesting machinery;
- minimal generic runtime infrastructure useful without old traders.

Keep the laboratory where valid. Delete the old answers.

---

# 3. TWO PRIVATE COMPETITORS

## BLACKTIDE
- Name: `BLACKTIDE`
- Machine ID: `BLACKTIDE_SPY`
- Subtitle: `Autonomous SPY Options Evolution Engine`
- Owner: ChatGPT/Codex

BLACKTIDE has a private independently designed strategy. Claude must not request, inspect, infer, copy, modify, or train from BLACKTIDE-private strategy intelligence.

## Claude competitor
Claude independently designs its own trader from scratch. ChatGPT/Codex must not modify or consume Claude-private strategy intelligence.

## Shared facts, private brains
Approved shared resources may include SPY/option observations, calendars, factual event timestamps, deterministic neutral features, the backtest engine, execution simulator, data-quality infrastructure, API manager, market cache, neutral scorekeeper, and Discord transport.

Private resources include entries, exits, learned thresholds/weights, private models, private research conclusions, private evolution logic, future trade reasoning, and opponent postmortem intelligence.

---

# 4. IMMUTABLE COMPETITION RULES

- Product: SPY options.
- Initial scope: long 0DTE CALLS and PUTS, buy to open and sell to close.
- Starting bankroll per generation: `$1,000`.
- Hard cap: `MAX_OPEN_TRADES = 1` per bot.
- Multiple contracts of the exact same selected option may count as one trade; independent positions may not overlap.
- No live shadow trading or hidden continuously monitored option portfolios.
- No lookahead.
- Realistic paper execution only. No hindsight fills, fake liquidity, or future-aware pricing.
- Official completed trades are immutable.
- On bust/effective inability to afford a legitimate qualifying trade: freeze the generation, preserve official history and that bot’s legitimate learning, record a postmortem/bust, reset bankroll to `$1,000`, and start a new generation.
- Money resets. History does not.
- Neither bot may alter shared rules because it is losing.

---

# 5. ULTRA-COMPETITIVE CULTURE

The competition is a core system feature. Both traders are expected to relentlessly attempt to finish #1.

Optimize independently for real performance: bankroll growth, expectancy, profit factor, drawdown control, survival, bust frequency, generation-over-generation improvement, and adaptation across SPY regimes.

Strategic freedom is intentionally broad within immutable rules. Neither competitor receives sympathy points, strategic handicaps, extra data/API resources, or access to the other’s private intelligence.

The shared infrastructure is the referee. The neutral scorekeeper is the judge. The market decides who was actually better.

---

# 6. NEUTRAL SCOREBOARD

Authoritative competition accounting must live outside both private traders and consume immutable official trade records.

Public metrics may include current bankroll, generation, lifetime/generation P&L, trade counts, win rate, profit factor, expectancy, average/largest winner and loser, max/current drawdown, bust count, streaks, best/worst generation, generation-over-generation improvement, current position status, and current leader.

Neither trader may modify authoritative competition results. Actual money/performance remains primary.

---

# 7. DISCORD RIVALRY SYSTEM

Create a dedicated rivalry channel during the Discord rebuild, conceptually `#blacktide-vs-claude`.

It is for official head-to-head results, trade-close reactions, lead changes, busts, milestones, generation results, and bot-to-bot trash talk. It is separate from operational trade channels.

## Rivalry personas actually read each other
The rivalry persona layer may read:
- official public competition facts;
- the opponent’s exact public rivalry message;
- relevant public rivalry history;
- prior public boasts/promises;
- public score snapshots.

The trading brain may **not** read rivalry messages.

Flow:

`OFFICIAL EVENT -> SCOREKEEPER UPDATE -> RIVALRY EVENT -> BOT A POST -> BOT B READS POST + PUBLIC FACTS + RELEVANT BANTER -> BOT B RESPONDS -> BOUNDED REPLIES -> EVENT CLOSES`

## Public rivalry memory
Store traceable public rivalry history with fields such as `rivalry_event_id`, timestamp, trigger, speaker, target, message, public score snapshot, trade reference, generation, reply-to ID, conversation round, callbacks used, and Discord message ID.

This supports callbacks, running jokes, prior boasts, comeback promises, and score-history references. Rivalry history is presentation data only and may not enter either trader’s private learning loop.

## Triggers
Possible triggers include:
`SESSION_OPEN`, `FIRST_WIN_OF_DAY`, `FIRST_LOSS_OF_DAY`, `TRADE_CLOSED_WIN`, `TRADE_CLOSED_LOSS`, `NEW_COMPETITION_LEADER`, `LEAD_EXTENDED`, `LEAD_LOST`, `BANKROLL_MILESTONE`, `NEW_BEST_TRADE`, `NEW_WORST_TRADE`, `WINNING_STREAK`, `LOSING_STREAK`, `DRAWDOWN_RECOVERY`, `MAJOR_COMEBACK`, `GENERATION_BUSTED`, `GENERATION_RECORD`, `GENERATION_COMPLETED`, `SESSION_WINNER`, `LIFETIME_LEADER_CHANGE`.

## Initial internal rivalry limits
These are design targets, not claims about Discord platform limits:

- `RIVALRY_MAX_MESSAGES_PER_BOT_PER_EVENT = 3`
- `RIVALRY_MAX_MESSAGES_PER_BOT_PER_DAY = 20`
- `RIVALRY_MAX_TOTAL_MESSAGES_PER_MINUTE = 6`
- `RIVALRY_MIN_MESSAGE_GAP_SECONDS = 20`
- `RIVALRY_OPEN_POSITION_CHAT = false`
- `RIVALRY_PRIVATE_STRATEGY_ACCESS = false`
- `RIVALRY_CAN_INFLUENCE_TRADING = false`

Claude must audit actual Discord behavior and recommend safe final values.

Bounded event chains may look like A -> B -> A -> B until the event budget closes. No infinite autonomous loops.

Each bot may make at most one session-open and one session-close rivalry post. No continuous idle chatter.

No open-position banter by default.

Trash talk should use real public results such as P&L, bankroll difference, streak, drawdown, lead, generation, bust count, profit factor, session winner, comeback status, and prior public boasts.

The rivalry subsystem must never trigger trades, change sizing/entries/exits/risk, influence evolution, create revenge trading, consume meaningful market-data priority, or reveal private strategy information.

---

# 8. API AND MARKET-DATA ARCHITECTURE

Current owner estimate is approximately `120 requests/minute`, but this is provisional.

The pre-build audit must verify:
- active market-data/quote/options/Greeks/historical providers;
- REST limits;
- streaming limits;
- separate/shared quota buckets;
- endpoint-specific and burst limits;
- retries and header telemetry;
- whether a full same-expiration chain arrives in one request;
- account-tier differences.

Classify claims as `VERIFIED`, `ASSUMED`, or `UNKNOWN`.

Future API priority:
1. open-position safety;
2. exit-critical data;
3. entry-critical data;
4. shared SPY observations;
5. shared options collection;
6. secondary context;
7. nonessential research;
8. rivalry presentation.

Use one shared factual market service wherever practical: one observation, many authorized readers.

---

# 9. TRUSTED DATA ERA

Tradysquid 2.0 should permanently accumulate factual market history every trading day regardless of trade activity.

## SPY target collection
Where available: timestamp, 1-minute OHLCV, bid/ask/last, bid/ask size, provider timestamp, receive timestamp, premarket/RTH context, provider, collector version.

## 0DTE option target collection
Approximately one useful same-day SPY chain snapshot per RTH minute if provider limits permit. Preserve where available:
snapshot ID, market/receive timestamps, synchronized SPY bid/ask/last, option symbol, expiration, strike, side, bid/ask, bid/ask size, last, volume, open interest, IV, Delta, Gamma, Theta, Vega, provider/provider timestamp, collector version.

History must be append-only. New intraday snapshots may not overwrite old ones.

## Storage
Preferred:
- Parquet for immutable high-volume raw observations, partitioned approximately by `instrument/year/month/trading_day`;
- DuckDB for research/backtesting/query over Parquet;
- SQLite only for smaller operational metadata/state where useful.

## Data classes
Use:
`VERIFIED_REAL`
`REAL_WITH_LIMITATIONS`
`MODELED`
`UNKNOWN_PROVENANCE`
`REJECTED`

Never silently mix modeled and observed information.

## Daily data manifest
Track expected/received SPY minutes, expected/received chain snapshots, option rows, missing periods, stream gaps, API/rate-limit errors, duplicates, invalid observations, collector version, and data grade (`A`, `B`, `C`, `REJECT`).

---

# 10. NEUTRAL POINT-IN-TIME BACKTESTING

Target shared interface conceptually:

- `market.as_of(timestamp)`
- `options.as_of(timestamp)`
- `events.as_of(timestamp)`

At simulated time `T`, future information should be structurally inaccessible.

Evidence tiers:

- **Tier A:** real SPY + real timestamped option observations.
- **Tier B:** real SPY + modeled options. Every report must display `OPTION PRICING MODELED`.
- **Tier C:** required evidence unavailable. Return `INSUFFICIENT DATA`.

Tier A may select only contracts that actually existed at the simulated point in time.

Shared neutral features may include deterministic causal VWAP, ATR, returns, realized volatility, relative volume, previous-day/week levels, opening ranges, higher-timeframe bars, and basic structure measurements. Shared features must be deterministic, causal, versioned, reproducible, and strategy-neutral.

Formal backtests should record bot/strategy version, engine version, dataset fingerprint, date range, evidence tier, data quality, feature versions, execution assumptions, parameters, random seed where relevant, results, and timestamp. Identical inputs should reproduce identical output.

---

# 11. OWNERSHIP AND ISOLATION

Ownership classes:
- `SHARED_CORE`
- `SHARED_DATA`
- `BLACKTIDE_ONLY`
- `CLAUDE_ONLY`
- `HUMAN_LEARNING_CENTER`

Future machine-readable ownership should define path, owner, readers, writers, protected status, and purpose.

Protected writes should verify actor -> target -> ownership -> permission -> allow/reject -> log violations.

Claude cannot modify BLACKTIDE-private resources. ChatGPT/Codex cannot modify Claude-private resources. Neither competitor autonomously changes immutable competition law.

Use root `AGENTS.md` for global rules and scoped instructions for private areas.

---

# 12. PHASE 0 — GOVERNANCE BOOTSTRAP BEFORE ANY OTHER IMPLEMENTATION

This is mandatory.

**Before Phase 1 or any other implementation work touches the system, the first authorized implementation action is to create and validate the project-memory/logging system.**

Create at minimum:

- `governance/PROJECT_STATE.yaml`
- `governance/PHASES.yaml`
- `governance/ACTIVE_HANDOFF.yaml`
- `governance/CHANGELOG.jsonl`
- `governance/OWNERSHIP.*`
- `governance/IMMUTABLE_RULES.*`
- required locking/concurrency mechanism
- root/scoped agent instructions enforcing read-before-write

Phase 0 itself must be tied to the commit that introduces it.

Once Phase 0 exists, no intentional implementation change may bypass the logging protocol.

## Mandatory task lifecycle

Before touching implementation files for any task:

1. Read this master specification.
2. Read governance/ownership.
3. Read `PROJECT_STATE`.
4. Read `PHASES`.
5. Read `ACTIVE_HANDOFF`.
6. Read relevant recent `CHANGELOG`.
7. Claim/lock the work scope.
8. Create a unique `work_id` / `change_id`.
9. Write a **STARTED** record containing the owner request, before state, reason, intended scope, expected files/schemas/Discord/competition effects, required tests, risks, and the next safe action if interrupted immediately.
10. Update `ACTIVE_HANDOFF` **before the first implementation write**.

During non-trivial work:
- checkpoint `ACTIVE_HANDOFF` after meaningful milestones;
- record discoveries that alter scope;
- add newly required phases/subphases to `PHASES`;
- never leave the only record of progress in chat.

If usage/session/tooling dies mid-task, the open STARTED record plus ACTIVE_HANDOFF must state what is completed, partial, not started, last successful action, current error if any, unsafe-to-repeat actions, and next safe step.

A missing completion record means the task remains `IN_PROGRESS`/`PARTIAL`. The next authorized AI resumes from repository state instead of asking the owner to reconstruct the work.

After a task completes:
1. run required tests/validation;
2. reconcile affected Discord surfaces;
3. reconcile schemas/data/runtime state;
4. update phase/subphase state;
5. update `PROJECT_STATE`;
6. finalize/append the change record with actual files changed, behavior after, tests/results, errors, additions/removals/fixes, side effects, remaining work, commit after, and final status;
7. clear/advance `ACTIVE_HANDOFF`;
8. release the work lock.

A task without a valid start record is unauthorized. A task with code changes but no end record is `INCOMPLETE`.

## Immediate knowability requirement

At any moment, a fresh Claude or Codex conversation must be able to read repository state and answer:
- what task is active;
- who started it;
- why;
- before state;
- what has changed and what has not;
- last successful operation;
- tests run/results;
- complete/partial/failed/blocked status;
- next safe action;
- phase/subphase.

After Phase 0 is active, manual conversational handoffs should not be required for normal Tradysquid development.

---

# 13. PROJECT MEMORY FILE ROLES

- `TRADYSQUID_2_MASTER_PREBUILD.md` = approved architecture, goals, and rules.
- `PROJECT_STATE.yaml` = exact current operational truth.
- `PHASES.yaml` = authoritative live build backlog, phase/subphase status, dependencies, completion criteria.
- `CHANGELOG.jsonl` = append-only historical change truth.
- `ACTIVE_HANDOFF.yaml` = current unfinished work and recovery checkpoint.
- `OWNERSHIP.*` = who may read/write what.
- `IMMUTABLE_RULES.*` = rules no agent may casually change.

`PROJECT_STATE.current_commit` should match the repository state it describes. If Git materially changes without synchronized state, flag `PROJECT_STATE_STALE`.

Do not create separate Claude and Codex versions of project truth.

---

# 14. DISCORD SYNCHRONIZATION INVARIANT

Every dynamic Discord surface must have an explicit owner, purpose, data source, producer, publisher, event/update trigger, expected behavior, and health state.

Maintain a surface manifest with fields such as surface ID, category/channel, owner/purpose, producer/publisher, event types, update mode, expected silence, persistent message IDs, schema, enabled status, health, last event/update/publish/error.

When a feature changes, every dependent Discord surface must become:
`UPDATED`, `VERIFIED_UNAFFECTED`, or `RETIRED`.

Persistent surfaces must rebuild from authoritative state after startup/deployment/reconnect/schema/channel/migration events. They must not sit blank waiting for a future trade to wake them up.

Health should distinguish:
`HEALTHY`, `QUIET_VALID`, `NO_DATA_EXPECTED`, `STALE`, `PRODUCER_OFFLINE`, `PUBLISH_FAILED`, `DESYNCHRONIZED`, `MISCONFIGURED`.

Discord failure must not stop trading. Rivalry failure must not stop trading. BLACKTIDE and Claude failures must be isolated from each other. Backtest failure must not stop market collection. Learning Center failure must not affect competition.

---

# 15. HUMAN LEARNING CENTER

The Learning Center is a comprehensive human-facing options education system, not autonomous trader intelligence.

Discord layout:
- one `LEARNING CENTER` category;
- `#learning-index`;
- one chapter channel for each chapter `#01-...` through `#43-...`;
- as many messages/cards per chapter as required.

Do not skimp. Chapters may include overview, objectives, topic index, detailed explanations, terminology, mechanics, math, Greeks, volatility effects, risk/reward, exercise/assignment/expiration, worked examples, P&L examples, practical uses, failure cases, mistakes, cross-links, and summary.

Curriculum:
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
17. Put Buying with Stock Ownership
18. Buying Puts with Call Purchases
19. Sale of a Put
20. Sale of a Straddle
21. Synthetic Stock Positions
22. Basic Put Spreads
23. Spreads Combining Calls and Puts
24. Ratio Spreads Using Puts
25. LEAPS / Long-Term Option Strategies
26. Buying Options and Treasury Bills
27. Arbitrage
28. Mathematical Applications
29. Index Option Products and Futures
30. Stock Index Hedging
31. Index Spreading
32. Structured Products
33. Mathematical Considerations for Index Products
34. Futures and Futures Options
35. Futures Option Strategies for Futures Spreads
36. Basics of Volatility Trading
37. How Volatility Affects Popular Strategies
38. Distribution of Stock Prices
39. Volatility Trading Techniques
40. Advanced Concepts
41. Volatility Derivatives
42. Taxes
43. The Best Strategy?

Additional references may include strategy summaries, equivalent positions, formulas, P&L graphs, qualified covered calls, portfolio margin, glossary, and index.

Use comprehensive original explanations/examples/math/diagrams and updated factual material rather than long verbatim reproduction.

Every lesson should eventually receive a stable ID such as `LC-17-04` with chapter/lesson/topics/keywords/related concepts/Discord channel/message/jump link/version/publication state.

Human Q&A may search and link directly to lessons.

Autonomous BLACKTIDE and Claude trading processes must be mechanically prevented from importing, searching, querying, training from, or using Learning Center strategy content.

---

# 16. SOURCE CONTROL AND BACKUP

Git should contain source, tests, governance, schemas, small templates, and required documentation.

Do not commit secrets, huge raw market archives, runtime databases, logs, caches, temp files, random backups, or legacy trader fossils.

Future backup must protect at least raw SPY observations, raw option observations, daily manifests, and data catalog.

---

# 17. CONCEPTUAL REPOSITORY

Conceptually:

```text
Tradysquid/
  AGENTS.md
  README.md
  TRADYSQUID_2_MASTER_PREBUILD.md
  governance/
    PROJECT_STATE.yaml
    PHASES.yaml
    ACTIVE_HANDOFF.yaml
    CHANGELOG.jsonl
    OWNERSHIP.*
    IMMUTABLE_RULES.*
    SCHEMAS.*
    CHANGE_POLICY.*
  shared/
    market/
    options/
    backtest/
    features/
    execution/
    api_budget/
    competition/
    events/
    discord/
  data/
    raw/
    derived/
    manifests/
    catalog/
  learning/
    catalog/
    lessons/
    search/
    references/
  bots/
    blacktide/
    claude/
  tests/
    shared/
    isolation/
    competition/
    learning/
  runtime/
```

Names may change for concrete technical reasons; ownership boundaries may not become ambiguous.

---

# 18. WORK DIVISION

Shared infrastructure is built once: cleanup, governance, ownership, synchronization, factual data, storage, neutral backtest, API manager, market cache, scorekeeper, events, Discord, rivalry presentation, and Learning Center framework.

ChatGPT/Codex owns BLACKTIDE-private implementation.

Claude owns Claude-private implementation.

---

# 19. PROPOSED BUILD PHASES

These are the starting map, not an artificial finish line.

- **Phase 0:** governance bootstrap/logging activation.
- **Phase 1:** backup and freeze.
- **Phase 2:** final inventory.
- **Phase 3:** legacy purge.
- **Phase 4:** governance hardening, schemas, write guards, ownership enforcement, stale-state detection, atomic state updates, concurrency prevention, scoped agent instructions, continuity/CI enforcement. Do not recreate competing copies of Phase-0 state files.
- **Phase 5:** shared factual market-data architecture/storage.
- **Phase 6:** neutral point-in-time backtest laboratory.
- **Phase 7:** shared runtime/API/cache/events.
- **Phase 8:** neutral competition scorekeeper.
- **Phase 9:** Discord rebuild, synchronized surfaces, dashboards, scoreboards, rivalry channel/personas/memory, health/reconciliation.
- **Phase 10:** Learning Center shell/index/43 chapter channels.
- **Phase 11:** independent bot ownership areas.
- **Phase 12:** BLACKTIDE implementation.
- **Phase 13:** Claude competitor implementation.
- **Phase 14:** full validation.
- **Phase 15:** competition launch with both bots at `$1,000` and `0 inherited trades`.
- **Phase 16:** full Learning Center population.

Claude may recommend justified ordering changes during audit.

---

# 20. DYNAMIC PHASE DISCOVERY AND TRUE COMPLETION

At the end of every implementation phase:

1. validate the phase;
2. inspect what new required work was revealed;
3. check for missing dependencies, broken integrations, stale Discord surfaces, unhandled failures, missing tests, ownership/schema/data-quality/operational gaps, unfinished migrations, and newly necessary work;
4. if required work exists, create a new explicit phase/subphase in `PHASES.yaml`, log why it was discovered, assign dependencies/owner/completion criteria, and continue.

Tradysquid 2.0 is only **BUILD COMPLETE** when:
- every known phase/subphase is complete;
- final validation passes;
- no required untracked phase remains;
- no unresolved blocker remains;
- no required integration is orphaned;
- no dynamic Discord surface is stale/unowned;
- project state and Git are synchronized;
- required tests pass;
- Claude and Codex independently inspect the approved system and find no additional implementation phase required.

The phase list ending is not proof of completion.

---

# 21. PRE-BUILD AUDIT REQUIREMENTS

Claude’s read-only audit must be self-contained for Codex and cover at least:

1. executive status: `READY WITH NO MATERIAL CORRECTIONS`, `READY WITH CORRECTIONS`, or `BLOCKED`;
2. current providers;
3. verified API limits;
4. available/limited/unavailable/unknown market-data fields;
5. streaming;
6. verified historical datasets;
7. data to reject;
8. neutral backtest baseline;
9. real vs EOD vs modeled/proxy option-history reality;
10. daily SPY/0DTE collection feasibility;
11. storage estimate;
12. storage-stack recommendation;
13. shared API-budget architecture;
14. current Discord architecture/rate behavior/failure coupling;
15. repository map: `PURGE`, `PRESERVE`, `EXTRACT/NEUTRALIZE`, `UNKNOWN`;
16. governance/ownership;
17. Learning Center feasibility/firewall;
18. competition/scoreboard/rivalry feasibility, including interactive replies, rivalry memory, final safe message limits, no strategy leakage, and no trading influence;
19. phase-order corrections;
20. blockers;
21. assumptions this master got wrong;
22. verified constants ready for final governance;
23. final recommendation;
24. cross-agent synchronization: current state tracking/contradictions, recommended PROJECT_STATE/PHASES/CHANGELOG/ACTIVE_HANDOFF, Git integration, atomic updates, concurrency, interruption recovery, Discord/competition/rivalry synchronization, strategy privacy, mechanical enforcement.

For rivalry, choose:
`RIVALRY ARCHITECTURE READY`
`RIVALRY ARCHITECTURE NEEDS CORRECTIONS`
`RIVALRY ARCHITECTURE BLOCKED`

For synchronization, choose:
`SYNC ARCHITECTURE READY`
`SYNC ARCHITECTURE NEEDS CORRECTIONS`
`SYNC ARCHITECTURE BLOCKED`

No implementation during audit.

---

# 22. CODEX VERIFICATION AFTER CLAUDE

After Claude’s audit, Codex independently verifies the important claims and returns:

- `VERIFIED`
- `CORRECTIONS`
- `REMAINING UNKNOWNS`
- `FINAL HARD CONSTANTS`
- `FINAL COMPETITION RULES`
- `FINAL RIVALRY RULES`
- `FINAL ARCHITECTURE CHANGES`
- `FINAL PHASE ORDER`
- `BUILD READINESS`

Build readiness must be exactly one of:
`READY_TO_BUILD`
`READY_AFTER_OWNER_DECISION`
`NOT_READY`

Even `READY_TO_BUILD` does not authorize implementation. The owner explicitly authorizes the build.

---

# 23. REQUIRED IMPLEMENTATION WORKFLOW AFTER AUTHORIZATION

```text
READ MASTER SPEC
    ↓
READ GOVERNANCE / OWNERSHIP
    ↓
READ PROJECT_STATE / PHASES / ACTIVE_HANDOFF / RECENT CHANGELOG
    ↓
CLAIM + LOCK WORK
    ↓
CREATE STARTED RECORD / BEFORE STATE
    ↓
UPDATE ACTIVE_HANDOFF
    ↓
IMPLEMENT WITH CHECKPOINTS
    ↓
TEST / VALIDATE
    ↓
RECONCILE DISCORD + SCHEMAS + STATE
    ↓
DISCOVER NEW REQUIRED PHASES
    ↓
UPDATE PROJECT_STATE / PHASES
    ↓
FINALIZE CHANGELOG
    ↓
CLEAR/ADVANCE ACTIVE_HANDOFF
    ↓
VERIFY COMMIT + RELEASE LOCK
```

The repository, not conversation memory, becomes the handoff between agents.

---

# 24. OWNER ADDITIONS

The owner may add new pre-build requirements to this master before build authorization. Every agent must treat the latest committed master file as current design intent unless superseded by an explicit later owner decision.

---

# FINAL INTENT

Tradysquid 2.0 ultimately has:

- no inherited trader intelligence;
- verified factual shared market data;
- permanent daily SPY/0DTE collection;
- Parquet raw storage and DuckDB analytics;
- neutral reproducible point-in-time backtesting;
- shared API budgeting;
- one official position per bot;
- no live shadow trading;
- immutable official trade history;
- private BLACKTIDE and private Claude strategies;
- ruthless legitimate competition for #1;
- neutral scorekeeping;
- interactive result-driven Discord rivalry with public memory and bounded replies;
- no rivalry-driven trading or strategy leakage;
- hard ownership/isolation;
- Phase-0 logging before any other implementation touch;
- before/during/after change records;
- recoverable interrupted work;
- synchronized Discord surfaces with no orphans;
- comprehensive 43-chapter human Learning Center and human Q&A;
- hard Learning Center/trader firewall;
- dynamic phase discovery until no required work remains;
- reproducible project state and research;
- explicit owner authorization before implementation.

The shared system remains synchronized.  
The strategies remain private.  
The rivalry remains vicious.  
The evidence remains honest.  
The project itself remembers.
