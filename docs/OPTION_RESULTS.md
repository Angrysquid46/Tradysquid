# 0DTE Option Results (Phase 5)

The side-by-side: **underlying edge next to option edge**, so it is visible which strategies are actually better as 0DTE trades rather than as underlying moves.


> ⚠️ **Every option number here is MODELLED.** The archive contains no intraday option quotes at all — only 16:00 snapshots, at which point a 0DTE is minutes from expiry and worth roughly intrinsic. Prices are Black-Scholes from a **real IV level for that day**, priced to the session close. Validated against real 1DTE quotes: median error −8.2%, 87% within 25%.
>
> Scored on **988 sessions where a same-day expiry actually existed**. Before 2023, most days had none (38–157 per year), so this sample is far smaller than the underlying results and the conclusions are correspondingly weaker.
>
> Entry pays the ask, exit receives the bid, $0.65/contract each way. Position size uses the live $500 cap and $5.00 max ask.


## The shortlist as options — exit shape `spy_0dte`

| Strategy | Underlying exp (ATR) | Option trades | Win% | Option exp (%) | **Total P/L** | PF | EOD exits | Survives? |
|---|---|---|---|---|---|---|---|---|
| S21 Gap continuation | gap>=0.5% | +0.0620 | 4,042 | 42.9% | +0.3% | $-156,222 | 0.78 | 0% | no |
| S7 Failed breakout | prev-day levels | +0.0322 | 1,229 | 42.2% | -0.7% | $-51,569 | 0.76 | 1% | no |
| S21 Gap continuation | gap>=0.25% | +0.0315 | 6,763 | 41.4% | -1.8% | $-349,311 | 0.72 | 0% | no |
| S8 Liquidity sweep | reclaim<=10bars | +0.0209 | 972 | 41.8% | -1.7% | $-45,922 | 0.74 | 0% | no |
| S8 Liquidity sweep | reclaim<=5bars | +0.0178 | 793 | 43.0% | -0.2% | $-31,063 | 0.78 | 1% | no |
| S14 Momentum continuation | adx25 unaligned | +0.0145 | 10,083 | 38.1% | -5.4% | $-684,884 | 0.65 | 1% | no |
| S18 Time-of-day | MIDDAY | +0.0122 | 7,008 | 39.3% | -4.7% | $-437,176 | 0.66 | 0% | no |
| S16 Confluence | 4+ levels | +0.0098 | 5,229 | 39.7% | -3.8% | $-304,411 | 0.69 | 1% | no |
| S18 Time-of-day | FINAL_30 | +0.0086 | 281 | 44.8% | +2.3% | $-7,051 | 0.85 | 15% | no |
| S19 MTF breakout | 4/4 agree | +0.0217 | 2,601 | 37.9% | -6.0% | $-194,827 | 0.62 | 1% | no |
| LIVE SPY_KEY_LEVELS | deployed rules | +0.0188 | 16,065 | 38.2% | -5.7% | $-1,162,952 | 0.63 | 1% | no |
| S15 Momentum exhaustion | 1.0atr ext | +0.1019 | 11 | 63.6% | +31.0% | $+1,360 | 2.29 | 0% | **YES** |
| S21 Gap continuation | gap>=1.0% | +0.0532 | 1,547 | 45.4% | +3.9% | $-23,091 | 0.91 | 0% | no |
| S12 First pullback | 0.5atr drive | +0.0460 | 56 | 44.6% | -0.6% | $-1,624 | 0.83 | 0% | no |
| PB1 Opening gap fade | spec thresholds | +0.0389 | 13 | 53.8% | +20.9% | $+889 | 1.50 | 0% | **YES** |

**2 of 15 survive the option layer** (positive total P/L and positive average return per trade, after spread and commission).


Survivors, best first:

- **S15 Momentum exhaustion | 1.0atr ext** — 11 trades, 63.6% win, +31.0% per trade, **$+1,360** total.
- **PB1 Opening gap fade | spec thresholds** — 13 trades, 53.8% win, +20.9% per trade, **$+889** total.


## Exit-shape comparison on `S21 Gap continuation | gap>=0.5%`

The 10 live ratchet variants share one entry and differ **only** in exit shape, which is defined in option-premium percent. On underlying bars they are indistinguishable; this is the first time they can be ranked against each other.

| Exit shape | Trades | Win% | Exp (%) | Total P/L | PF | EOD exits |
|---|---|---|---|---|---|---|
| `spy_0dte (+50/-50, floor +30->-15)` | 4,042 | 42.9% | +0.3% | $-156,222 | 0.78 | 0% |
| `ratchet_26_36` | 4,695 | 41.3% | -3.9% | $-275,012 | 0.63 | 0% |
| `ratchet_30_17` | 5,837 | 28.9% | -6.2% | $-394,710 | 0.52 | 0% |
| `ratchet_26_18` | 5,864 | 30.3% | -6.2% | $-396,693 | 0.52 | 0% |
| `ratchet_30_16` | 5,916 | 28.2% | -6.2% | $-399,800 | 0.51 | 0% |
| `ratchet_26_17` | 5,941 | 29.8% | -6.2% | $-400,247 | 0.51 | 0% |
| `ratchet_26_16` | 6,031 | 29.0% | -6.3% | $-408,334 | 0.50 | 0% |
| `ratchet_25_17` | 5,963 | 29.8% | -6.4% | $-409,259 | 0.50 | 0% |
| `ratchet_29_16` | 5,957 | 28.4% | -6.5% | $-409,451 | 0.50 | 0% |
| `ratchet_25_16` | 6,051 | 29.1% | -6.5% | $-416,986 | 0.49 | 0% |
| `ratchet_24_16` | 6,084 | 29.2% | -6.5% | $-417,335 | 0.50 | 0% |

---

## What this means

**13 of 15 lose money as 0DTE options, and all 11 live exit shapes lose money.**
The two "survivors" rest on **11 and 13 trades** and are noise, not findings.

### Why a real underlying edge still loses

Every strategy here has a positive underlying expectancy, yet win rates collapse
to **38-45%** once expressed as options. A symmetric ±50% target/stop needs a
win rate **above 50%** just to break even, and on a decaying asset with a
bid-ask spread it needs more than that. Theta and the spread take the
difference. That is the whole answer to "does the edge survive": mostly, no.

### All 10 ratchet variants are worse than the shape you already run

| | Total P/L |
|---|---|
| `spy_0dte (+50/-50, floor +30→-15)` | **−$156,222** (best of the 11) |
| best ratchet (`26/36`) | −$275,012 |
| worst ratchet (`24/16`) | −$417,335 |

The ratchets' tight base stops (−16% to −18%) get hit constantly — win rates
drop to **28-30%** versus 42.9% for the current shape. Retiring all 10, which
Phase 7 already decided on entry-signal grounds, is independently supported here
on exit grounds.

### Two caveats that matter for reading the table

1. **These are not the same trades as the underlying run.** Option exits at
   ±50% premium trigger on a much smaller underlying move than a 2-ATR target,
   so trades close far sooner and re-enter far more often — 4,042 option trades
   versus 1,058 underlying trades on the same signal. That is why EOD exits show
   0-1% here but 89-97% there. The entry signal is identical; the exit regime is
   the live system's real one.
2. **Sample and modelling limits.** 988 sessions (0DTE only existed on some days
   before 2023), and every option price is modelled — validated at median −8.2%
   error, but a systematic 8% bias would move marginal cases.

### What this does not say

It does **not** say these strategies are worthless. It says buying a 0DTE
directional option with a ±50% exit is a losing way to express them. Untested
alternatives that the data could still support: longer-dated contracts (less
theta), asymmetric exits (wider target than stop, to fix the sub-50% win rate),
or trading the underlying directly.

### Recommended next step

Before wiring any of these into Discord, sweep the **exit shape** rather than
the entry — asymmetric targets (+100/−40, +150/−50) and shorter time stops are
the obvious candidates, since the current failure is entirely an exit-geometry
and cost problem, not an entry problem.
