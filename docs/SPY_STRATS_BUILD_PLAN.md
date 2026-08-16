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

### ⬜ Phase 1 — Ingest the historical datasets
Load everything into a queryable store, alongside the existing `market_memory`
database, without touching live trading.
- Resolve the 1-minute timezone question against a known session (definitively,
  not by assumption), then load 2008-2021 as a `1min` timeframe.
- Inner-merge the 7 daily CSVs on `Date`; extend daily coverage back to 1993.
- Verify: row counts, date ranges, gap report, no duplicate keys.
- Option-chain ingestion deliberately deferred to Phase 5, where it is first
  used — parsing 8 GB of JSON now would delay Phases 2-3 for no benefit.
- **Exit criteria:** every dataset queryable and reconciled against its source.

### ⬜ Phase 2 — Intraday feature engine
Per-minute market state with **no lookahead**, which the specs demand twice.
- Global market map: prev-day H/L/C/mid/range, prev-week levels, premarket
  H/L/mid/range, gap %, opening range (5/15/30 min), session H/L, VWAP + slope +
  distance, ATR, relative volume (time-of-day normalised).
- Multi-timeframe alignment (daily/60m/15m/5m/2m) → 5-state classification.
- 10-state regime engine; day-type classifier that updates through the session.
- **Exit criteria:** feature parity tests + an explicit no-lookahead test per feature.

### ⬜ Phase 3 — Backtest engine + first strategy tranche
- Event-driven 1-minute backtester, underlying-only (per the spec's instruction
  to optimise the underlying entry *before* contract selection).
- First tranche: the ORB family (1, 2), VWAP family (3, 4, 10).
- Metrics: expectancy, profit factor, win rate, MFE/MAE, drawdown, streaks,
  holding time, and breakdowns by hour/day/regime/volatility/gap.
- Walk-forward splits by era, never a single train-on-everything fit.
- **Exit criteria:** honest per-strategy stats, including strategies that fail.

### ⬜ Phase 4 — Remaining strategies + ranking
- Strategies 5-9, 11-22, the 3 quantified playbooks, and the time-of-day plays.
- Tier A/B/C/FAILED ranking with the spec's stated bar. Failed strategies stay
  failed — the spec explicitly forbids rescuing them by piling on filters.
- **Exit criteria:** full library scored; a written list of what did not work.

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
