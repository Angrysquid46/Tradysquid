# 0DTE Option Results (Phase 5)

The side-by-side: **underlying edge next to option edge**, so it is visible which strategies are actually better as 0DTE trades rather than as underlying moves.


> ⚠️ **Every option number here is MODELLED.** The archive contains no intraday option quotes at all — only 16:00 snapshots, at which point a 0DTE is minutes from expiry and worth roughly intrinsic. Prices are Black-Scholes from a **real IV level for that day**, priced to the session close. Validated against real 1DTE quotes: median error −8.2%, 87% within 25%.
>
> Scored on **988 sessions where a same-day expiry actually existed**. Before 2023, most days had none (38–157 per year), so this sample is far smaller than the underlying results and the conclusions are correspondingly weaker.
>
> Entry pays the ask, exit receives the bid, $0.04/contract each way. Position size uses the live $500 cap and $5.00 max ask.


## The shortlist as options — exit shape `spy_0dte`

| Strategy | Underlying exp (ATR) | Option trades | Win% | Option exp (%) | **Total P/L** | PF | EOD exits | Survives? |
|---|---|---|---|---|---|---|---|---|
| S21 Gap continuation | gap>=0.5% | +0.0620 | 4,042 | 42.9% | +0.3% | $-7,308 | 0.99 | 0% | no |
| S7 Failed breakout | prev-day levels | +0.0322 | 1,229 | 42.2% | -0.7% | $-7,249 | 0.96 | 1% | no |
| S21 Gap continuation | gap>=0.25% | +0.0315 | 6,763 | 41.4% | -1.8% | $-82,997 | 0.92 | 0% | no |
| S8 Liquidity sweep | reclaim<=10bars | +0.0209 | 972 | 41.8% | -1.7% | $-10,397 | 0.93 | 0% | no |
| S8 Liquidity sweep | reclaim<=5bars | +0.0178 | 793 | 43.0% | -0.2% | $-2,733 | 0.98 | 1% | no |
| S14 Momentum continuation | adx25 unaligned | +0.0145 | 10,083 | 38.1% | -5.4% | $-296,333 | 0.82 | 1% | no |
| S18 Time-of-day | MIDDAY | +0.0122 | 7,008 | 39.3% | -4.7% | $-181,630 | 0.84 | 0% | no |
| S16 Confluence | 4+ levels | +0.0098 | 5,229 | 39.7% | -3.8% | $-110,368 | 0.87 | 1% | no |
| S18 Time-of-day | FINAL_30 | +0.0086 | 281 | 44.8% | +2.3% | $+2,623 | 1.06 | 15% | **YES** |
| S19 MTF breakout | 4/4 agree | +0.0217 | 2,601 | 37.9% | -6.0% | $-85,260 | 0.81 | 1% | no |
| LIVE SPY_KEY_LEVELS | deployed rules | +0.0188 | 16,065 | 38.2% | -5.7% | $-497,258 | 0.82 | 1% | no |
| S15 Momentum exhaustion | 1.0atr ext | +0.1019 | 11 | 63.6% | +31.0% | $+1,667 | 2.72 | 0% | **YES** |
| S21 Gap continuation | gap>=1.0% | +0.0532 | 1,547 | 45.4% | +3.9% | $+24,595 | 1.11 | 0% | **YES** |
| S12 First pullback | 0.5atr drive | +0.0460 | 56 | 44.6% | -0.6% | $-206 | 0.98 | 0% | no |
| PB1 Opening gap fade | spec thresholds | +0.0389 | 13 | 53.8% | +20.9% | $+1,286 | 1.84 | 0% | **YES** |

**4 of 15 survive the option layer** (positive total P/L and positive average return per trade, after spread and commission).


Survivors, best first:

- **S21 Gap continuation | gap>=1.0%** — 1,547 trades, 45.4% win, +3.9% per trade, **$+24,595** total.
- **S18 Time-of-day | FINAL_30** — 281 trades, 44.8% win, +2.3% per trade, **$+2,623** total.
- **S15 Momentum exhaustion | 1.0atr ext** — 11 trades, 63.6% win, +31.0% per trade, **$+1,667** total.
- **PB1 Opening gap fade | spec thresholds** — 13 trades, 53.8% win, +20.9% per trade, **$+1,286** total.


## Exit-shape comparison on `S21 Gap continuation | gap>=0.5%`

The 10 live ratchet variants share one entry and differ **only** in exit shape, which is defined in option-premium percent. On underlying bars they are indistinguishable; this is the first time they can be ranked against each other.

| Exit shape | Trades | Win% | Exp (%) | Total P/L | PF | EOD exits |
|---|---|---|---|---|---|---|
| `spy_0dte (+50/-50, floor +30->-15)` | 4,042 | 42.9% | +0.3% | $-7,308 | 0.99 | 0% |
