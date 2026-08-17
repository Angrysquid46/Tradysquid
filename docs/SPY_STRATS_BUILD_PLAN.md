# SPY Strategy Research Build — Phased Plan

Source material: `C:\Users\strea\OneDrive\Desktop\spy strats` (12 spec documents,
36 data files, ~10.4 GB). This document is the resumable plan — each phase is
independently shippable, so work can stop and restart without losing the thread.

**Status legend:** ⬜ not started · 🟨 in progress · ✅ merged

---

## What the source material actually contains

### Specifications (12 text files, ~263 KB — all read)

| File | Content |
|---|---|
| `spy strats.txt` (98 KB) | **The core.** 20 fully-specified strategies, plus ~24 time-of-day "plays", plus a third overlapping ORB/VWAP set. Global market map, multi-timeframe context, 10-state regime engine, option selection, stop system, profit management, trailing/time stops, 100-point trade quality score, no-trade conditions, Tier A/B/C/FAILED ranking, overfitting protection, walk-forward, execution realism, trade journal schema. Names a **FINAL STRATEGY SET of 22**. |
| `backtest data.txt` (17 KB) | 30 research upgrades: feature store, regime detection, multi-target models (direction/magnitude/MFE/MAE/time-to-move), predict-the-option-not-just-SPY, expected-vs-required move, meta-model, strategy competition, NO-TRADE as a class, calibration, SHAP, market memory/analogs, day-type, drift detection, champion/challenger, Monte Carlo, walk-forward, execution simulation, edge decay, counterfactuals, postmortems. |
| `spy technicals for claude.txt` (13 KB) | Master feature inventory — 30 numbered groups, several hundred features, plus per-strategy feature sets. Explicit instruction: make them **available**, do not force every one into every strategy. |
| `spy stuff.txt` (9 KB) | 3 fully-quantified playbooks with exact thresholds: Institutional Opening Gap Fade, Intraday 1-Min Momentum Squeeze, Mid-Day Theta Burn (iron condor). |
| `maybe system order for machine leraning.txt` (4 KB) | Tier 1/2/3 build order and the pipeline: DATA → FEATURES → BACKTEST → STRATEGIES → ML → VALIDATION → RANKING → DISCORD → LEARNING. "Discord should be the interface, not the brain." |
| `learning update.txt` (58 KB) | Learning Center modules **28 → 128** (~100 new channels), each with 3-8 lesson bullets. |
| `learning shit for spy.txt`, `more learning shit.txt`, `maybe new shit.txt` (45 KB) | Learning Center curriculum: market structure through auction theory, volume profile, volatility surface, VIX term structure, entropy, fractals, PCA, factor models. |
| `indicators instructions.txt`, `macro overlays instructions.txt` | Merge the daily CSVs on `Date`; **do not look forward when testing**. |
| `discord changes.txt` | Consolidate strategies under one group; per-strategy channel with a P/L card; drop strategy-results; dashboard ranks best performers. |

### Data (36 files, ~10.4 GB — all profiled)

| Dataset | Coverage | Verdict |
|---|---|---|
| 7 daily CSVs (`spy_ultimate_max_indicators` + 6 overlays) | 1993 → 2026, 8,444–8,752 rows, common `Date` key | ✅ Clean inner-merge. ~50 daily columns incl. `SPY_30D_IV`, `SPY_9D_IV`, `SPY_Volume_PC_Ratio`, `SPY_OI_PC_Ratio`, `Volume_ZScore_20`, `Intraday_Efficiency_Ratio`, `Opening_Gap_Pct`, `Close_vs_Range_Pct`, `Rolling_Sharpe_60d`, `Market_Drawdown_Pct`, `Volatility_Risk_Premium` |
| `spy_1min_2008_2021_cleaned.csv` (134 MB) | **2008-01-22 → 2021-05-06, real 1-minute OHLCV** + `barCount`, `average` | ✅ The single most valuable file. ~1.3M bars/yr. Includes some extended-hours bars. ✅ Timezone **resolved**: volume peaks at exactly 07:30 and 13:59 (open/close spikes), and 07:30 is the session start in both January and July every year — DST-aware local **Mountain Time**. Converted to ET on ingest. |
| `spy_options_data_14..25.json` (~8 GB) | 2014 → 2025, one **EOD snapshot per trading day**, full chain: bid/ask/sizes, volume, OI, IV, delta, gamma, theta, vega, rho | ✅ Real chains, 0DTE rows confirmed present (~1.4% of records). ⚠️ **EOD only.** |
| `spy_2020_2022.csv` (1.3 GB) | 2020–2022 chains, `QUOTE_TIME_HOURS` = 16.0 only | ⚠️ Also **EOD only**. Same limitation. |
| `spy_eod_*.parquet` (2010–2023, ~600 MB) | EOD options | Needs `pyarrow` (not currently installed in either venv). |

---

## The one finding that constrains everything

**There is no intraday option-quote data anywhere in this folder.** Every option
source — the 8 GB of JSON, the 1.3 GB CSV, the parquet set — is a single
end-of-day snapshot per trading day.

A 0DTE option quoted at 16:00 on its expiration day is worth essentially
intrinsic value; it is minutes from expiry. It tells you almost nothing about
what that contract was worth at 09:45 when a strategy would actually have
entered.

So, stated plainly:

- ✅ **Underlying backtests are fully real.** 13 years of true 1-minute bars
  support every entry/exit rule in the specs, honestly.
- ✅ **Option-chain characteristics are real** at daily resolution: IV level and
  term structure, skew, put/call ratios, OI, spread width, liquidity — 2014-2025.
- ❌ **A true intraday 0DTE option P/L backtest is not possible from this data.**
  It can only be *modelled* (Black-Scholes from a real IV starting point, with
  explicit slippage and decay assumptions), never measured.

This is exactly the distinction the source material itself draws in
`backtest data.txt` — "underlying backtest" vs "options backtest" — and it warns
that conflating them hides where edge is actually lost. The build will keep the
two separated and labelled everywhere, and no phase will claim a measured 0DTE
option edge that the data cannot support.

---

## Phases

Ordered per the source material's own pipeline. Each phase ends in a merged PR.

### ✅ Phase 1 — Ingest the historical datasets
Load everything into a queryable store, alongside the existing `market_memory`
database, without touching live trading.
- Resolve the 1-minute timezone question against a known session (definitively,
  not by assumption), then load 2008-2021 as a `1min` timeframe.
- Inner-merge the 7 daily CSVs on `Date`; extend daily coverage back to 1993.
- Verify: row counts, date ranges, gap report, no duplicate keys.
- Option-chain ingestion deliberately deferred to Phase 5, where it is first
  used — parsing 8 GB of JSON now would delay Phases 2-3 for no benefit.
- **Exit criteria:** every dataset queryable and reconciled against its source.

### ✅ Phase 2 — Intraday feature engine
`spy_intraday_features.py` → `minute_features`, **1,300,717 rows across 3,347
sessions** (2008-01-22 → 2021-05-06), 69 columns, built in 70s.

- Global market map: prev-day H/L/C/mid/range, prev-week levels, premarket
  H/L/mid/range, gap %/$/ATR, opening ranges (5/15/30 min), session H/L/range,
  VWAP + slope + distance (raw/%/ATR) + cross count, ATR, relative volume
  (time-of-day normalised), plus the bar's own OHLCV so the store is
  self-contained.
- Multi-timeframe alignment (5m/15m/60m/daily) → 5-state classification, read
  from the last **closed** higher-timeframe bucket only.
- 10-state regime engine; day-type classifier that evolves through the session.
- **No-lookahead is enforced by truncation test**: every feature at bar *i* must
  be byte-identical whether computed over the full session or a session ending
  at *i*. 17 tests pass.

**Observed distributions** (sanity, not edge): RANGE 58%, COMPRESSION 14%,
strong trends 2.0% combined; day types at the close skew CHOPPY_DAY 51%.
Nulls are warm-up only — first session (prev-day), first 14 (ATR), first week
(prev-week) — plus 2 sessions whose source data starts late (2009-07-27 at
11:15, 2013-12-23 at 10:08), left NULL rather than fabricated.

> ⚠️ **Second data constraint found here.** Premarket bars are present in only
> **226 of 3,347 sessions (6.8%)** — 2020 (78%), early 2021 (29%), 4 days in
> 2008, and **zero across 2009-2019**. So `premarket_*` and any strategy keyed
> to premarket range are testable only on a COVID-era sample, which is the least
> representative window available. Gap % itself is unaffected (it uses the prior
> close), so gap strategies remain fully testable — but premarket-*range*
> strategies must be reported with this caveat attached, or dropped.

### ✅ Phase 3 — Backtest engine + first strategy tranche
`spy_backtest.py` + `spy_backtest_strategies.py` → full results in
[`BACKTEST_RESULTS.md`](BACKTEST_RESULTS.md).

- Event-driven 1-minute backtester, underlying-only, over all 3,347 sessions.
- 20 variants (ORB 1/2 × 5/15/30-min windows; VWAP 3 × zones A/B/C; 4 × chop
  limits 2-5; 10 × 6 extension thresholds) × 12 exit policies = **228
  combinations**, plus a random-entry control.
- Metrics: expectancy, PF, win rate, MFE/MAE, drawdown, streaks, holding time,
  **t-statistic vs zero**, and breakdowns by era/regime/time-of-day/direction/
  exit reason.

**Realism rules, each of which inflates results when skipped:** signals evaluate
on a closed bar and fill at the *next* bar's open; a bar containing both stop and
target resolves as the **stop** (1-min OHLC cannot order them); one position at a
time; forced flat at 15:59.

> **Headline result: 0 of 15 variants clear 95% significance, and 0 are
> profitable in all four eras.** Best expectancy is +0.028 ATR/trade at t=+1.37;
> the highest t anywhere is +1.78. The random control returns -0.0002 ATR/trade,
> so the leaders beat noise by less than noise moves between eras. And each t is
> already the best of 12 exit policies, so it is an upper bound.
>
> This is a measurement, not a failure. The ORB and VWAP families **as literally
> specified, with light filtering** do not predict the SPY underlying over
> 2008-2021. The spec anticipated this — it repeatedly says the filters matter as
> much as the pattern. Establishing this baseline first is what makes it possible
> to tell later whether a filter adds real edge or just looks like it does.
>
> Also consistent: **every leading variant loses money in 2020-2021**, the most
> recent era. COVID distortion or edge decay cannot be separated here, and the
> 2021-2026 intraday gap means it cannot be settled at all until that is filled.

### ✅ Phase 4 — Remaining strategies + measurement
`spy_backtest_strategies_extended.py` + a Tier-2 feature layer. Combined results
in [`BACKTEST_RESULTS.md`](BACKTEST_RESULTS.md).

- **Tier-2 features added** to `minute_features` (now 95 columns, rebuilt in
  182s): EMA 5/9/10/20 + slope, Wilder ADX/+DI/−DI, Kaufman efficiency ratio,
  volume z-score, momentum score, bar range position, confirmed swing points,
  short-term structure label, compression flags, expected-move consumption,
  and level-confluence count.
- **19 more strategy families** (S5-S9, S11-S19, S21, S22 + the two directional
  playbooks), 47 variants total, run through the same 12 exit policies →
  **336 combinations with n≥30**.

> 🛑 **Correction (2026-08-17): the first Phase 4 run was invalid.**
> `BACKTEST_COLUMNS` was a hand-curated subset of the feature table and
> omitted 27 columns the new strategies read — `prev_day_high`,
> `premarket_low`, `structure`, `adx_14` and others. A missing key in a
> feature dict reads as `None`, so nothing raised: S5-S19, PB1 and PB2
> produced **zero signals**, and strategies shaped like
> `if row.get(x) … elif not row.get(x)` took the `elif` branch every time
> and quietly became **short-only**. The sweep still emitted a complete,
> plausible-looking report. The column list is now derived from the schema,
> and a test runs every strategy over rows that record which keys they touch,
> failing if anything read isn't loaded. Results below are from the re-run.
> The gap-continuation finding is unaffected — `gap_pct` and `above_vwap`
> were both in the old subset — but it was re-verified rather than assumed.

> **Headline: gap continuation is the first real edge found.**
> `S21 gap>=0.5%` returns **+0.0620 ATR/trade over 1,058 trades (t=+3.33),
> positive in 4/4 eras** — the only thing in the build to clear both bars, and
> it holds up in 2020-2021 where every other leader fails.
>
> It survives the check that matters: a **matched control** — random entries on
> *the same sessions* with *the same exits* — returns −0.0043 (t=−0.28). So the
> edge is not drift, not exit geometry, and not long bias. A dose-response
> across thresholds (0.25% → +0.032, 0.5% → +0.062) corroborates it.
>
> ⚠️ **But 90% of those trades exit at the session close, not at a target.** The
> edge is mostly *hold to the bell*, which is the worst possible holding pattern
> for a 0DTE option — theta is largest exactly then. Phase 5 must settle whether
> this survives being expressed as an option at all.
>
> Honest limits: t=+3.33 clears the naive 1.96 threshold but **not** the
> Bonferroni-corrected 3.79 for 336 tests. The matched control and era
> consistency are independent of that correction, which is why they carry more
> weight here than the t-statistic alone.

**Not tested, and why** — stated so a library of 22 reporting 20 isn't mistaken
for an oversight: **S20 Relative-Strength** needs intraday QQQ/IWM/DIA and
breadth that the SPY-only archive does not contain; **PB3 Mid-Day Theta Burn**
is an iron condor whose entire P/L is premium decay, so it has no underlying
entry to measure and belongs to Phase 5.

### Phase 4 as originally scoped
- Strategies 5-9, 11-22, the 3 quantified playbooks, and the time-of-day plays.
- Scored on the same basis as Phase 3, **including where they sit relative to
  the random baseline**.
- **Owner decision (2026-08-16): nothing gets eliminated.** The goal is to see
  how effective each strategy is, not to prune the library. Tier labels are
  descriptive only — a weak result is a measurement to keep, not a deletion.
  The spec's ban on rescuing failed strategies by piling on filters still
  applies: a strategy is reported as it was specified.
- **Exit criteria:** full library measured, with the weak results written down
  as plainly as the strong ones.

### ✅ Shortlist — live Discord strategies measured against the new ideas
Requested 2026-08-16: rank everything currently on Discord (excluding `evolve_bot`)
alongside every new idea, to pick a **top 15** and stop the channel sprawl. Full
table in [`BACKTEST_RESULTS.md`](BACKTEST_RESULTS.md).

`spy_backtest_live_strategies.py` adapts the live strategies by calling the
deployed `spy_scanner` functions **directly**, so the backtest cannot drift from
what is running.

> **The live library is 4 entry signals, not 14 strategies.**
>
> | Entry signal | Live strategies sharing it | Expectancy | t | Eras + |
> |---|---|---|---|---|
> | ORB, 1-min bars | **11** (`SPY_0DTE_1M` + all 10 ratchets) | +0.0004 | +0.39 | 3/4 |
> | ORB, 5-min bars | 1 (`SPY_0DTE_5M`) | −0.0004 | −0.64 | 0/4 |
> | Key-levels | 1 (`SPY_KEY_LEVELS`) | **+0.0188** | **+2.01** | 3/4 |
> | Expansion | 1 (`SPY_EXPANSION_LEVEL`) | −0.0044 | −0.34 | 2/4 |
>
> **`SPY_KEY_LEVELS` is the only live strategy with a statistically real entry
> edge.** The ORB signal that **12 of the 14** live strategies run on measures at
> essentially zero. That is not an artefact of the adapters' entry window —
> relaxing it from minute 360 to 380 moves the 1-min variant to t=+0.95 and the
> 5-min to t=+0.27, both still noise.
>
> **Only 1 of the top 15 is a strategy already on Discord.** The other 14 slots
> are research strategies, led by gap continuation (+0.0620, t=+3.33, 4/4 eras)
> and failed-breakout (+0.0322, t=+2.94, 4/4 eras).

**What this cannot decide yet.** Every live *exit* is defined in option-premium
percent — `SPY_0DTE`'s ±50% with a floor raise at +30%, and each ratchet's
`step_pct`/`stop_pct`. None of that is measurable from underlying bars, so the
10 ratchet variants are indistinguishable here: one entry, ten exit shapes.
Phase 5 is what separates them. And every significant winner exits at the
session close 89-97% of the time, which is the worst holding pattern for a 0DTE
option — so **no Discord restructure should be built on this ranking until
Phase 5 confirms the edges survive theta.**

### ⬜ Phase 5 — Option layer (explicitly modelled)
- Ingest EOD option chains into a compact table (0DTE + near-ATM band rather
  than all 8 GB verbatim), keyed by date/expiration/strike/type.
- Delta-band selection (0.50-0.70 tested individually), liquidity rejection
  rules, expected-move vs required-move.
- Option outcome **modelled** from real EOD IV with stated slippage/decay
  assumptions — labelled as modelled everywhere it surfaces.
- **Exit criteria:** underlying edge and option edge reported separately, always.

### ⬜ Phase 6 — ML and meta-model
- Extend `evolve_bot`'s feature set with the Phase 2 features.
- Multi-target models: direction, magnitude, MFE, MAE, time-to-move.
- **NO-TRADE as a first-class class**, not an absence of signal.
- Calibration (reliability curves, Brier), SHAP, meta-model strategy ranking,
  duplicate-signal detection, drift detection.
- **Exit criteria:** calibrated probabilities; predicted ≈ observed on held-out data.

### ⬜ Phase 7 — Discord restructure
- Consolidate strategies under one group; per-strategy channel with an updating
  P/L card; dashboard ranks best performers; retire strategy-results.
- One channel per strategy (owner decision), not per trade.

### ⬜ Phase 8 — Learning Center expansion
- Modules 28 → 128, **condensed** into fewer dense channels (owner decision)
  rather than ~100 thin ones, keeping the curriculum inside one category.

---

## Decisions made

1. **One channel per strategy** (~36 total: 14 existing + 22 new), each holding a
   single updating card with that strategy's current/last trade P/L. Confirmed
   with the owner — per-*trade* channels would have exhausted Discord's
   500-channel guild cap in roughly five weeks at current trade volume.

2. **Condense the Learning Center** into fewer, denser channels rather than
   spanning 2-3 categories. Related modules from the 28-128 set get merged so
   the curriculum fits without sprawling; each channel carries more content.

---

## Standing constraints

- `runtime_contract.py` and the rest of the CLAUDE.md freeze list stay untouched.
- Paper trading only; no brokerage execution.
- Research code stays isolated from live trading, as `market_memory` already is.
- Every phase: real tests that fail without the change, run before and after.
