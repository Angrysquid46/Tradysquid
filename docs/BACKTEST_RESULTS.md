# Underlying Backtest Results (Phases 3-4)

Generated from `minute_features` over **3,347 sessions** (2008-01-22 - 2021-05-06). Every number below is the **SPY underlying**, measured in ATR multiples. There is no option P/L here - that is Phase 5, and mixing the two would misreport what was actually tested.

**Nothing is eliminated.** Every variant tested is listed, including the losing ones. Where a strategy does not work, that is the finding.


### Not tested, and why

Stated up front so a list of 22 strategies with 20 results does not look like an oversight.

- **S20 Relative-Strength Breakout** — needs intraday QQQ/IWM/DIA and breadth to confirm against; the archive is SPY-only, so there is nothing to compare SPY with.
- **PB3 Mid-Day Theta Burn** — an iron condor - all of its P/L is option premium decay, with no underlying entry to measure. Belongs to Phase 5.

### Tested, but read with a caveat

- **S5 Premarket breakout** — only 226 of 3,347 sessions carry premarket bars (6.8%), nearly all in 2020 - not comparable to the other samples.
- **S17 Expected-move breakout** — expected move is derived from daily ATR, not a 0DTE implied move; no intraday IV exists in this archive.

## The comparison that matters

Random entries on the same bars, under the same exit policy search, return **-0.0002 ATR/trade** (48.8% win rate over 6,133 trades).

That is the bar. A strategy beating zero but not beating this has shown nothing - it is being carried by the same drift and exit geometry the random control gets for free.


## Best exit policy per variant

Exit labels read `t<target>/s<stop>/m<time-stop>`, all in ATR multiples. `t` is the t-statistic of the expectancy against zero; **|t| >= 1.96 is the 95% threshold**. Per-trade P/L scatters about +-1 ATR, so a few hundred trades cannot resolve an edge of a few hundredths - most rows below are statistically indistinguishable from a coin flip, and the column says so.

| Strategy | Variant | Best exit | Trades | Win% | Expectancy (ATR) | t | Sig? | PF | MaxDD | vs random |
|---|---|---|---|---|---|---|---|---|---|---|
| S15 Momentum exhaustion | 1.0atr ext | `t0.5/s0.5/m30` | 34 | 58.8% | +0.1019 | +1.52 | no | 1.77 | -1.4 | +0.1022 |
| S21 Gap continuation | gap>=0.5% | `t2.0/s1.0/m-` | 1,058 | 56.8% | +0.0620 | +3.33 | **yes** | 1.30 | -7.4 | +0.0622 |
| S5 Premarket breakout | retest | `t2.0/s1.0/m-` | 174 | 55.2% | +0.0596 | +1.63 | no | 1.42 | -3.0 | +0.0599 |
| S5 Premarket breakout | immediate | `t1.0/s0.75/m-` | 209 | 56.9% | +0.0592 | +1.90 | no | 1.41 | -4.4 | +0.0594 |
| S21 Gap continuation | gap>=1.0% | `t2.0/s1.0/m-` | 388 | 58.8% | +0.0532 | +1.65 | no | 1.23 | -8.8 | +0.0534 |
| S12 First pullback | 0.5atr drive | `t1.0/s0.75/m-` | 215 | 51.2% | +0.0460 | +1.14 | no | 1.21 | -6.6 | +0.0463 |
| PB1 Opening gap fade | spec thresholds | `t0.5/s0.5/m15` | 46 | 60.9% | +0.0389 | +1.37 | no | 1.76 | -0.8 | +0.0391 |
| S7 Failed breakout | prev-day levels | `t1.5/s1.0/m-` | 2,003 | 51.7% | +0.0322 | +2.94 | **yes** | 1.19 | -9.3 | +0.0324 |
| S21 Gap continuation | gap>=0.25% | `t1.5/s1.0/m-` | 1,956 | 52.9% | +0.0315 | +2.44 | **yes** | 1.15 | -11.7 | +0.0317 |
| S10 VWAP reversion | 0.5atr | `t1.0/s0.75/m-` | 420 | 52.1% | +0.0284 | +1.37 | no | 1.19 | -10.7 | +0.0286 |
| S2 ORB immediate | or5 | `t1.0/s0.75/m-` | 1,565 | 50.5% | +0.0251 | +1.75 | no | 1.11 | -11.9 | +0.0254 |
| S4 VWAP reclaim | chop<=2 | `t2.0/s1.0/m-` | 2,164 | 49.8% | +0.0217 | +1.78 | no | 1.11 | -17.1 | +0.0219 |
| S19 MTF breakout | 4/4 agree | `t2.0/s1.0/m-` | 2,361 | 52.9% | +0.0217 | +2.61 | **yes** | 1.16 | -11.8 | +0.0219 |
| S8 Liquidity sweep | reclaim<=10bars | `t2.0/s1.0/m-` | 1,859 | 51.4% | +0.0209 | +1.84 | no | 1.12 | -9.5 | +0.0211 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t2.0/s1.0/m-` | 3,466 | 50.1% | +0.0188 | +2.01 | **yes** | 1.09 | -20.9 | +0.0190 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.5/s1.0/m-` | 1,603 | 50.8% | +0.0185 | +1.59 | no | 1.11 | -14.0 | +0.0188 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.5/s1.0/m-` | 1,732 | 50.9% | +0.0178 | +1.55 | no | 1.11 | -9.9 | +0.0181 |
| S1 ORB retest | or5 | `t2.0/s1.0/m-` | 3,198 | 50.0% | +0.0172 | +1.74 | no | 1.08 | -25.5 | +0.0175 |
| S17 Expected-move | <50% used | `t2.0/s1.0/m-` | 3,300 | 50.5% | +0.0162 | +1.64 | no | 1.08 | -21.0 | +0.0164 |
| S17 Expected-move | <75% used | `t2.0/s1.0/m-` | 3,327 | 50.5% | +0.0155 | +1.57 | no | 1.07 | -22.3 | +0.0158 |
| S17 Expected-move | <100% used | `t2.0/s1.0/m-` | 3,330 | 50.5% | +0.0149 | +1.51 | no | 1.07 | -23.3 | +0.0152 |
| S17 Expected-move | <125% used | `t2.0/s1.0/m-` | 3,482 | 50.3% | +0.0146 | +1.50 | no | 1.07 | -23.9 | +0.0148 |
| S14 Momentum continuation | adx25 unaligned | `t1.5/s1.0/m-` | 3,579 | 50.0% | +0.0145 | +1.63 | no | 1.07 | -20.6 | +0.0148 |
| S3 VWAP pullback | zoneC 0.50atr | `t2.0/s1.0/m-` | 3,489 | 51.0% | +0.0143 | +1.53 | no | 1.07 | -28.0 | +0.0146 |
| S3 VWAP pullback | zoneB 0.25atr | `t2.0/s1.0/m-` | 3,392 | 51.1% | +0.0142 | +1.49 | no | 1.07 | -21.8 | +0.0144 |
| S18 Time-of-day | OPEN | `t1.0/s0.75/m-` | 3,345 | 50.0% | +0.0130 | +1.43 | no | 1.06 | -23.3 | +0.0133 |
| S16 Confluence | 2+ levels | `t1.0/s0.75/m-` | 3,655 | 50.0% | +0.0125 | +1.45 | no | 1.06 | -23.1 | +0.0127 |
| S11 Compression break | 5bars quiet | `t1.5/s1.0/m-` | 101 | 45.5% | +0.0123 | +0.40 | no | 1.12 | -2.9 | +0.0126 |
| S18 Time-of-day | MIDDAY | `t2.0/s1.0/m-` | 3,361 | 51.0% | +0.0122 | +1.56 | no | 1.08 | -14.7 | +0.0125 |
| S19 MTF breakout | 3/4 agree | `t2.0/s1.0/m-` | 3,496 | 50.5% | +0.0121 | +1.40 | no | 1.07 | -22.5 | +0.0123 |
| S16 Confluence | 4+ levels | `t1.5/s1.0/m-` | 2,235 | 50.1% | +0.0098 | +0.92 | no | 1.05 | -21.4 | +0.0101 |
| S4 VWAP reclaim | chop<=5 | `t1.0/s0.75/m-` | 3,249 | 48.9% | +0.0087 | +0.96 | no | 1.04 | -28.7 | +0.0089 |
| S18 Time-of-day | FINAL_30 | `t1.5/s1.0/m30` | 1,596 | 50.8% | +0.0086 | +1.70 | no | 1.13 | -5.0 | +0.0089 |
| S4 VWAP reclaim | chop<=3 | `t1.0/s0.75/m-` | 2,761 | 48.5% | +0.0084 | +0.85 | no | 1.04 | -20.2 | +0.0086 |
| S4 VWAP reclaim | chop<=4 | `t1.0/s0.75/m-` | 3,105 | 48.7% | +0.0072 | +0.78 | no | 1.04 | -28.6 | +0.0074 |
| S3 VWAP pullback | zoneA vwap | `t1.0/s0.75/m-` | 2,374 | 51.4% | +0.0066 | +0.70 | no | 1.04 | -23.9 | +0.0068 |
| S11 Compression break | 3bars quiet | `t0.5/s0.5/m-` | 754 | 50.0% | +0.0065 | +0.59 | no | 1.06 | -9.3 | +0.0068 |
| S14 Momentum continuation | adx30 aligned | `t1.0/s0.75/m-` | 3,788 | 49.8% | +0.0062 | +0.81 | no | 1.03 | -19.7 | +0.0065 |
| S14 Momentum continuation | adx25 aligned | `t1.5/s1.0/m-` | 3,543 | 48.9% | +0.0042 | +0.48 | no | 1.02 | -34.9 | +0.0045 |
| S16 Confluence | 3+ levels | `t0.5/s0.5/m-` | 4,061 | 50.4% | +0.0030 | +0.47 | no | 1.02 | -36.0 | +0.0032 |
| S2 ORB immediate | or30 | `t2.0/s1.0/m-` | 1,472 | 48.0% | +0.0027 | +0.17 | no | 1.01 | -19.8 | +0.0029 |
| S6 Prev-day breakout | immediate | `t1.5/s1.0/m30` | 3,087 | 49.0% | +0.0015 | +0.38 | no | 1.02 | -16.1 | +0.0017 |
| S19 MTF breakout | 2/4 agree | `t1.0/s0.75/m-` | 4,146 | 49.5% | +0.0014 | +0.18 | no | 1.01 | -31.7 | +0.0016 |
| S2 ORB immediate | or15 | `t0.5/s0.5/m-` | 1,506 | 50.7% | +0.0011 | +0.10 | no | 1.01 | -10.1 | +0.0013 |
| S22 Gap fade | gap>=0.25% | `t0.5/s0.5/m30` | 12,561 | 48.4% | +0.0006 | +0.40 | no | 1.01 | -20.0 | +0.0009 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.5/s1.0/m30` | 27,507 | 48.9% | +0.0004 | +0.39 | no | 1.01 | -20.6 | +0.0006 |
| S13 Structure reversal | vwap confirmed | `t1.5/s1.0/m30` | 17,655 | 48.6% | +0.0003 | +0.28 | no | 1.01 | -18.5 | +0.0006 |
| S1 ORB retest | or15 | `t1.0/s0.75/m-` | 3,324 | 48.5% | +0.0001 | +0.01 | no | 1.00 | -34.2 | +0.0003 |
| S1 ORB retest | or30 | `t2.0/s1.0/m-` | 3,267 | 48.3% | -0.0001 | -0.01 | no | 1.00 | -34.3 | +0.0002 |
| BASELINE random | 2/session | `t0.5/s0.5/m30` | 6,133 | 48.8% | -0.0002 | -0.12 | no | 1.00 | -13.1 |  |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.5/s1.0/m15` | 37,820 | 47.8% | -0.0004 | -0.64 | no | 0.99 | -22.1 | -0.0001 |
| S9 Range reversal | range-filtered | `t0.5/s0.5/m-` | 4,789 | 50.1% | -0.0010 | -0.17 | no | 0.99 | -26.8 | -0.0007 |
| S13 Structure reversal | no vwap filter | `t0.5/s0.5/m15` | 33,104 | 48.1% | -0.0012 | -1.88 | no | 0.97 | -53.3 | -0.0009 |
| S22 Gap fade | gap>=0.5% | `t2.0/s1.0/m15` | 10,814 | 48.1% | -0.0013 | -1.10 | no | 0.97 | -19.3 | -0.0011 |
| S14 Momentum continuation | adx20 aligned | `t1.0/s0.75/m-` | 4,004 | 48.4% | -0.0013 | -0.17 | no | 0.99 | -34.4 | -0.0011 |
| S18 Time-of-day | MIDMORNING | `t1.0/s0.75/m15` | 13,158 | 49.1% | -0.0014 | -1.35 | no | 0.97 | -26.6 | -0.0012 |
| S9 Range reversal | unfiltered | `t0.5/s0.5/m15` | 29,525 | 50.0% | -0.0015 | -2.23 | **yes** | 0.96 | -61.1 | -0.0013 |
| S18 Time-of-day | AFTERNOON | `t0.5/s0.5/m15` | 24,039 | 47.6% | -0.0020 | -2.77 | **yes** | 0.95 | -50.5 | -0.0017 |
| S22 Gap fade | gap>=1.0% | `t1.0/s0.75/m15` | 3,878 | 48.1% | -0.0026 | -1.16 | no | 0.95 | -17.0 | -0.0024 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.0/s0.75/m-` | 114 | 47.4% | -0.0038 | -0.11 | no | 0.97 | -4.5 | -0.0035 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t0.5/s0.5/m-` | 818 | 52.1% | -0.0044 | -0.34 | no | 0.97 | -9.1 | -0.0042 |
| S6 Prev-day breakout | retest | `t2.0/s1.0/m15` | 5,034 | 46.1% | -0.0076 | -4.20 | **yes** | 0.84 | -38.2 | -0.0073 |
| S18 Time-of-day | MORNING | `t1.5/s1.0/m15` | 6,663 | 47.1% | -0.0090 | -5.30 | **yes** | 0.84 | -62.8 | -0.0087 |
| S12 First pullback | 0.75atr drive | `t0.5/s0.5/m-` | 33 | 51.5% | -0.0159 | -0.20 | no | 0.93 | -1.7 | -0.0157 |
| S10 VWAP reversion | 0.75atr | `t1.0/s0.75/m15` | 88 | 50.0% | -0.0245 | -1.44 | no | 0.67 | -3.2 | -0.0242 |

## Verdict

- **5 of 64 variants** clear statistical significance at 95% AND beat the random baseline.
- **10 of 64 variants** are profitable in every one of the four eras.


The variants that clear both bars:

- **S21 Gap continuation | gap>=0.5%** — +0.0620 ATR/trade over 1,058 trades (t=+3.33), positive in 4/4 eras.
  - ⚠️ **90% of these exit at the session close**, not at a target. The edge is therefore mostly *hold to the bell*, which is the single worst holding pattern for a 0DTE option — theta is largest exactly then. A positive underlying edge realised this way may not survive being expressed as a 0DTE call or put at all. Phase 5 has to settle that before this becomes a strategy.
- **S7 Failed breakout | prev-day levels** — +0.0322 ATR/trade over 2,003 trades (t=+2.94), positive in 4/4 eras.
  - ⚠️ **93% of these exit at the session close**, not at a target. The edge is therefore mostly *hold to the bell*, which is the single worst holding pattern for a 0DTE option — theta is largest exactly then. A positive underlying edge realised this way may not survive being expressed as a 0DTE call or put at all. Phase 5 has to settle that before this becomes a strategy.
- **S21 Gap continuation | gap>=0.25%** — +0.0315 ATR/trade over 1,956 trades (t=+2.44), positive in 4/4 eras.
  - ⚠️ **89% of these exit at the session close**, not at a target. The edge is therefore mostly *hold to the bell*, which is the single worst holding pattern for a 0DTE option — theta is largest exactly then. A positive underlying edge realised this way may not survive being expressed as a 0DTE call or put at all. Phase 5 has to settle that before this becomes a strategy.
- **S19 MTF breakout | 4/4 agree** — +0.0217 ATR/trade over 2,361 trades (t=+2.61), positive in 3/4 eras.
  - ⚠️ **97% of these exit at the session close**, not at a target. The edge is therefore mostly *hold to the bell*, which is the single worst holding pattern for a 0DTE option — theta is largest exactly then. A positive underlying edge realised this way may not survive being expressed as a 0DTE call or put at all. Phase 5 has to settle that before this becomes a strategy.
- **LIVE SPY_KEY_LEVELS | deployed rules** — +0.0188 ATR/trade over 3,466 trades (t=+2.01), positive in 3/4 eras.
  - ⚠️ **92% of these exit at the session close**, not at a target. The edge is therefore mostly *hold to the bell*, which is the single worst holding pattern for a 0DTE option — theta is largest exactly then. A positive underlying edge realised this way may not survive being expressed as a 0DTE call or put at all. Phase 5 has to settle that before this becomes a strategy.


The t-statistics above are also **optimistic by construction**: each row is the best of 12 exit policies for that variant, so the selection has already had 12 chances to find a favourable draw. Correcting for that search would push every one of them further toward zero, not away from it. Treat the column as an upper bound.


## Shortlist: top 15 of everything measured

Live Discord strategies and new research ideas ranked **together**, on the same data, the same exit-policy search and the same rules. Sorted by evidence rather than by headline number: eras survived first, then statistical significance, then size of edge — because expectancy alone puts a 40-trade fluke above a 2,000-trade result.

| # | Strategy | Variant | Live? | Trades | Win% | Expectancy (ATR) | t | Eras + | vs matched control |
|---|---|---|---|---|---|---|---|---|---|
| 1 | S21 Gap continuation | gap>=0.5% | no | 1,058 | 56.8% | +0.0620 | +3.33 | 4/4 | +0.0663 |
| 2 | S7 Failed breakout | prev-day levels | no | 2,003 | 51.7% | +0.0322 | +2.94 | 4/4 | +0.0520 |
| 3 | S21 Gap continuation | gap>=0.25% | no | 1,956 | 52.9% | +0.0315 | +2.44 | 4/4 | +0.0460 |
| 4 | S8 Liquidity sweep | reclaim<=10bars | no | 1,859 | 51.4% | +0.0209 | +1.84 | 4/4 | — |
| 5 | S8 Liquidity sweep | reclaim<=5bars | no | 1,732 | 50.9% | +0.0178 | +1.55 | 4/4 | — |
| 6 | S14 Momentum continuation | adx25 unaligned | no | 3,579 | 50.0% | +0.0145 | +1.63 | 4/4 | — |
| 7 | S18 Time-of-day | MIDDAY | no | 3,361 | 51.0% | +0.0122 | +1.56 | 4/4 | — |
| 8 | S16 Confluence | 4+ levels | no | 2,235 | 50.1% | +0.0098 | +0.92 | 4/4 | — |
| 9 | S18 Time-of-day | FINAL_30 | no | 1,596 | 50.8% | +0.0086 | +1.70 | 4/4 | — |
| 10 | S19 MTF breakout | 4/4 agree | no | 2,361 | 52.9% | +0.0217 | +2.61 | 3/4 | +0.0389 |
| 11 | LIVE SPY_KEY_LEVELS | deployed rules | **yes** | 3,466 | 50.1% | +0.0188 | +2.01 | 3/4 | +0.0293 |
| 12 | S15 Momentum exhaustion | 1.0atr ext | no | 34 | 58.8% | +0.1019 | +1.52 | 3/4 | — |
| 13 | S21 Gap continuation | gap>=1.0% | no | 388 | 58.8% | +0.0532 | +1.65 | 3/4 | — |
| 14 | S12 First pullback | 0.5atr drive | no | 215 | 51.2% | +0.0460 | +1.14 | 3/4 | — |
| 15 | PB1 Opening gap fade | spec thresholds | no | 46 | 60.9% | +0.0389 | +1.37 | 3/4 | — |

**1 of the 15 are strategies already running on Discord.**


### What this can and cannot decide yet

Every live strategy's *entry* is measured here faithfully — these adapters call the deployed functions in `spy_scanner` directly rather than reimplementing them, so the backtest cannot drift from what is running.


Every live exit is defined in option-premium percent - SPY_0DTE's +50%/-50% with a one-time floor raise at +30%, and each ratchet variant's step_pct/stop_pct floor. None of those can be measured from underlying bars, so the 10 ratchet variants are indistinguishable here: they share one entry and differ only in exit shape. Ranking them against each other requires the Phase 5 option model.


**The live library is smaller than it looks:**

| Entry signal | Live strategies sharing it |
|---|---|
| LIVE ORB 1-min entry | **11** — `SPY_0DTE_1M`, `SPY_RATCHET_26_16`, `SPY_RATCHET_30_16`, … (+8 more) |
| LIVE ORB 5-min entry | **1** — `SPY_0DTE_5M` |
| LIVE Key-Levels entry | **1** — `SPY_KEY_LEVELS` |
| LIVE Expansion entry | **1** — `SPY_EXPANSION_LEVEL` |

So 14 Discord strategies are really **4 entry signals**. The 10 ratchet variants are one entry with ten exit shapes, which is exactly the kind of duplication a channel-per-strategy layout multiplies into noise. Phase 7 should group by entry signal, and Phase 5 decides which exit shape on top of each is worth keeping.


## Matched control: same days, same exits, random entries

The headline table pits each variant's best exit policy against the baseline's best exit policy, which is not a fair fight. Here the control trades **the same sessions** with **the same exits**, so the entry rule is the only thing that differs. This is what separates a real signal from inherited drift and favourable exit geometry.

| Variant | Exit | Strategy exp | t | Random exp (same days) | t | Difference |
|---|---|---|---|---|---|---|
| S21 Gap continuation | gap>=0.5% | `t2.0/s1.0/m-` | +0.0620 (1,058) | +3.33 | -0.0043 (1,044) | -0.28 | **+0.0663** |
| S7 Failed breakout | prev-day levels | `t1.5/s1.0/m-` | +0.0322 (2,003) | +2.94 | -0.0199 (2,024) | -1.90 | **+0.0520** |
| S21 Gap continuation | gap>=0.25% | `t1.5/s1.0/m-` | +0.0315 (1,956) | +2.44 | -0.0145 (1,916) | -1.35 | **+0.0460** |
| S19 MTF breakout | 4/4 agree | `t2.0/s1.0/m-` | +0.0217 (2,361) | +2.61 | -0.0172 (2,397) | -1.89 | **+0.0389** |
| LIVE SPY_KEY_LEVELS | deployed rules | `t2.0/s1.0/m-` | +0.0188 (3,466) | +2.01 | -0.0105 (3,388) | -1.33 | **+0.0293** |
| S9 Range reversal | unfiltered | `t0.5/s0.5/m15` | -0.0015 (29,525) | -2.23 | -0.0015 (6,381) | -1.08 | **+0.0000** |
| S18 Time-of-day | AFTERNOON | `t0.5/s0.5/m15` | -0.0020 (24,039) | -2.77 | -0.0015 (6,347) | -1.05 | **-0.0005** |
| S6 Prev-day breakout | retest | `t2.0/s1.0/m15` | -0.0076 (5,034) | -4.20 | -0.0009 (3,695) | -0.49 | **-0.0067** |
| S18 Time-of-day | MORNING | `t1.5/s1.0/m15` | -0.0090 (6,663) | -5.30 | -0.0017 (6,390) | -1.25 | **-0.0073** |

**Multiple-comparison note.** 777 combinations with n>=30 were scored. A Bonferroni correction at that width requires |t| >= 3.79 rather than 1.96, so a raw t of ~3.3 clears the naive threshold but not the corrected one. The matched control above and per-era consistency are independent of that correction, which is why they carry more weight here than the t-statistic alone.


## Walk-forward: does it hold across eras?

A strategy that only works in one era is an artefact of that era. These are the same trades split by period, never refitted.


### BASELINE random | 2/session

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,841 | 47.3% | -0.0048 | 0.92 | -10.6 |
| 2012-2015 low-vol bull | 1,844 | 48.6% | +0.0038 | 1.07 | -4.3 |
| 2016-2019 late bull | 1,837 | 50.6% | +0.0025 | 1.04 | -7.5 |
| 2020-2021 covid era | 611 | 48.6% | -0.0068 | 0.89 | -8.3 |

### LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets)

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 8,372 | 48.9% | +0.0010 | 1.02 | -10.7 |
| 2012-2015 low-vol bull | 8,089 | 49.2% | +0.0001 | 1.00 | -12.5 |
| 2016-2019 late bull | 8,260 | 48.4% | +0.0002 | 1.00 | -10.6 |
| 2020-2021 covid era | 2,786 | 49.1% | -0.0003 | 1.00 | -6.2 |

### LIVE SPY_0DTE (ORB) | 5-min bars (5M)

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 11,544 | 47.6% | -0.0002 | 0.99 | -10.7 |
| 2012-2015 low-vol bull | 11,087 | 47.0% | -0.0003 | 0.99 | -10.8 |
| 2016-2019 late bull | 11,356 | 48.2% | -0.0000 | 1.00 | -9.8 |
| 2020-2021 covid era | 3,833 | 49.3% | -0.0018 | 0.96 | -8.8 |

### LIVE SPY_EXPANSION_LEVEL | deployed rules

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 244 | 50.0% | -0.0202 | 0.88 | -8.7 |
| 2012-2015 low-vol bull | 250 | 54.8% | +0.0077 | 1.05 | -3.8 |
| 2016-2019 late bull | 235 | 49.8% | -0.0075 | 0.96 | -6.0 |
| 2020-2021 covid era | 89 | 56.2% | +0.0129 | 1.08 | -2.7 |

### LIVE SPY_KEY_LEVELS | deployed rules

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,002 | 51.4% | +0.0409 | 1.22 | -10.7 |
| 2012-2015 low-vol bull | 1,048 | 51.7% | +0.0195 | 1.10 | -9.1 |
| 2016-2019 late bull | 1,057 | 48.6% | +0.0139 | 1.07 | -14.6 |
| 2020-2021 covid era | 359 | 46.2% | -0.0309 | 0.87 | -17.3 |

### PB1 Opening gap fade | spec thresholds

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 30 | 63.3% | +0.0662 | 2.75 | -0.6 |
| 2012-2015 low-vol bull | 6 | 50.0% | -0.0841 | 0.26 | -0.7 |
| 2016-2019 late bull | 4 | 50.0% | +0.0116 | 1.27 | -0.2 |
| 2020-2021 covid era | 6 | 66.7% | +0.0436 | 1.68 | -0.3 |

### PB2 Momentum squeeze | eff>=0.65

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 34 | 50.0% | -0.0212 | 0.84 | -1.9 |
| 2012-2015 low-vol bull | 41 | 39.0% | -0.0393 | 0.75 | -2.7 |
| 2016-2019 late bull | 33 | 54.5% | +0.0637 | 1.60 | -1.3 |
| 2020-2021 covid era | 6 | 50.0% | -0.0333 | 0.81 | -0.7 |

### S1 ORB retest | or15

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 980 | 49.5% | +0.0023 | 1.01 | -23.8 |
| 2012-2015 low-vol bull | 1,006 | 49.1% | +0.0006 | 1.00 | -20.7 |
| 2016-2019 late bull | 999 | 46.3% | -0.0081 | 0.96 | -18.7 |
| 2020-2021 covid era | 339 | 50.1% | +0.0164 | 1.09 | -8.6 |

### S1 ORB retest | or30

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 968 | 48.7% | +0.0017 | 1.01 | -13.8 |
| 2012-2015 low-vol bull | 978 | 48.0% | -0.0104 | 0.95 | -19.6 |
| 2016-2019 late bull | 984 | 48.3% | +0.0128 | 1.07 | -11.9 |
| 2020-2021 covid era | 337 | 48.1% | -0.0128 | 0.94 | -12.3 |

### S1 ORB retest | or5

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 931 | 51.7% | +0.0181 | 1.09 | -17.3 |
| 2012-2015 low-vol bull | 966 | 49.9% | +0.0280 | 1.14 | -12.5 |
| 2016-2019 late bull | 973 | 48.9% | +0.0121 | 1.06 | -24.1 |
| 2020-2021 covid era | 328 | 48.8% | -0.0019 | 0.99 | -9.6 |

### S10 VWAP reversion | 0.5atr

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 120 | 60.8% | +0.1271 | 2.34 | -2.5 |
| 2012-2015 low-vol bull | 141 | 43.3% | -0.0623 | 0.68 | -10.7 |
| 2016-2019 late bull | 133 | 54.9% | +0.0466 | 1.32 | -4.4 |
| 2020-2021 covid era | 26 | 46.2% | -0.0284 | 0.82 | -2.3 |

### S10 VWAP reversion | 0.75atr

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 13 | 76.9% | +0.0584 | 5.85 | -0.1 |
| 2012-2015 low-vol bull | 44 | 45.5% | -0.0324 | 0.61 | -1.6 |
| 2016-2019 late bull | 24 | 45.8% | -0.0529 | 0.45 | -1.3 |
| 2020-2021 covid era | 7 | 42.9% | -0.0309 | 0.43 | -0.3 |

### S11 Compression break | 3bars quiet

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 280 | 53.2% | +0.0170 | 1.14 | -4.9 |
| 2012-2015 low-vol bull | 255 | 51.4% | +0.0242 | 1.22 | -3.4 |
| 2016-2019 late bull | 185 | 44.9% | -0.0305 | 0.75 | -8.1 |
| 2020-2021 covid era | 34 | 41.2% | -0.0104 | 0.92 | -2.5 |

### S11 Compression break | 5bars quiet

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 33 | 48.5% | +0.0052 | 1.04 | -2.3 |
| 2012-2015 low-vol bull | 33 | 57.6% | +0.0855 | 2.31 | -0.7 |
| 2016-2019 late bull | 26 | 34.6% | -0.0374 | 0.66 | -1.7 |
| 2020-2021 covid era | 9 | 22.2% | -0.0860 | 0.37 | -0.8 |

### S12 First pullback | 0.5atr drive

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 53 | 45.3% | -0.0830 | 0.69 | -6.6 |
| 2012-2015 low-vol bull | 76 | 53.9% | +0.1049 | 1.56 | -3.6 |
| 2016-2019 late bull | 60 | 53.3% | +0.0762 | 1.37 | -2.5 |
| 2020-2021 covid era | 26 | 50.0% | +0.0675 | 1.24 | -2.2 |

### S12 First pullback | 0.75atr drive

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 7 | 42.9% | -0.0577 | 0.79 | -0.9 |
| 2012-2015 low-vol bull | 7 | 57.1% | +0.0465 | 1.27 | -0.5 |
| 2016-2019 late bull | 14 | 64.3% | +0.0541 | 1.30 | -1.0 |
| 2020-2021 covid era | 5 | 20.0% | -0.2409 | 0.29 | -1.2 |

### S13 Structure reversal | no vwap filter

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 9,798 | 48.5% | -0.0003 | 0.99 | -14.5 |
| 2012-2015 low-vol bull | 9,653 | 47.0% | -0.0030 | 0.93 | -32.7 |
| 2016-2019 late bull | 10,081 | 48.1% | -0.0011 | 0.97 | -15.2 |
| 2020-2021 covid era | 3,572 | 50.6% | +0.0012 | 1.03 | -3.9 |

### S13 Structure reversal | vwap confirmed

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 5,218 | 48.4% | +0.0002 | 1.00 | -14.5 |
| 2012-2015 low-vol bull | 5,201 | 48.0% | +0.0001 | 1.00 | -8.4 |
| 2016-2019 late bull | 5,375 | 48.8% | -0.0003 | 1.00 | -11.6 |
| 2020-2021 covid era | 1,861 | 50.4% | +0.0031 | 1.06 | -5.2 |

### S14 Momentum continuation | adx20 aligned

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,158 | 48.0% | -0.0054 | 0.97 | -17.0 |
| 2012-2015 low-vol bull | 1,213 | 49.1% | -0.0022 | 0.99 | -29.9 |
| 2016-2019 late bull | 1,208 | 47.7% | +0.0102 | 1.05 | -15.7 |
| 2020-2021 covid era | 425 | 49.2% | -0.0207 | 0.91 | -12.9 |

### S14 Momentum continuation | adx25 aligned

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,025 | 49.7% | +0.0124 | 1.07 | -14.4 |
| 2012-2015 low-vol bull | 1,068 | 49.0% | +0.0045 | 1.02 | -23.9 |
| 2016-2019 late bull | 1,081 | 47.7% | +0.0054 | 1.03 | -15.9 |
| 2020-2021 covid era | 369 | 49.6% | -0.0227 | 0.90 | -10.6 |

### S14 Momentum continuation | adx25 unaligned

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,040 | 50.3% | +0.0025 | 1.01 | -16.5 |
| 2012-2015 low-vol bull | 1,079 | 48.9% | +0.0101 | 1.05 | -12.7 |
| 2016-2019 late bull | 1,086 | 50.6% | +0.0340 | 1.19 | -11.7 |
| 2020-2021 covid era | 374 | 50.0% | +0.0039 | 1.02 | -10.1 |

### S14 Momentum continuation | adx30 aligned

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,096 | 49.5% | -0.0030 | 0.98 | -14.9 |
| 2012-2015 low-vol bull | 1,143 | 51.8% | +0.0194 | 1.11 | -19.7 |
| 2016-2019 late bull | 1,159 | 48.6% | +0.0097 | 1.05 | -11.4 |
| 2020-2021 covid era | 390 | 48.7% | -0.0167 | 0.92 | -12.6 |

### S15 Momentum exhaustion | 1.0atr ext

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 3 | 66.7% | +0.1544 | 1.93 | -0.5 |
| 2012-2015 low-vol bull | 6 | 33.3% | -0.0698 | 0.64 | -0.9 |
| 2016-2019 late bull | 14 | 64.3% | +0.1411 | 2.56 | -1.1 |
| 2020-2021 covid era | 11 | 63.6% | +0.1314 | 1.94 | -0.8 |

### S16 Confluence | 2+ levels

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,074 | 49.3% | -0.0105 | 0.95 | -23.1 |
| 2012-2015 low-vol bull | 1,103 | 50.5% | +0.0176 | 1.09 | -10.9 |
| 2016-2019 late bull | 1,106 | 50.8% | +0.0273 | 1.14 | -13.5 |
| 2020-2021 covid era | 372 | 48.7% | +0.0197 | 1.10 | -13.9 |

### S16 Confluence | 3+ levels

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,248 | 49.1% | -0.0076 | 0.96 | -36.0 |
| 2012-2015 low-vol bull | 1,218 | 51.4% | +0.0121 | 1.07 | -16.9 |
| 2016-2019 late bull | 1,185 | 50.6% | +0.0022 | 1.01 | -15.6 |
| 2020-2021 covid era | 410 | 50.2% | +0.0102 | 1.06 | -8.7 |

### S16 Confluence | 4+ levels

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 675 | 48.9% | +0.0020 | 1.01 | -19.2 |
| 2012-2015 low-vol bull | 667 | 52.0% | +0.0066 | 1.04 | -19.1 |
| 2016-2019 late bull | 621 | 50.9% | +0.0232 | 1.13 | -11.0 |
| 2020-2021 covid era | 272 | 46.7% | +0.0065 | 1.04 | -11.7 |

### S17 Expected-move | <100% used

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 982 | 51.4% | +0.0063 | 1.03 | -16.2 |
| 2012-2015 low-vol bull | 1,005 | 51.3% | +0.0283 | 1.14 | -9.5 |
| 2016-2019 late bull | 1,004 | 50.7% | +0.0280 | 1.14 | -11.2 |
| 2020-2021 covid era | 339 | 44.5% | -0.0383 | 0.84 | -23.3 |

### S17 Expected-move | <125% used

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,027 | 51.4% | +0.0058 | 1.03 | -17.6 |
| 2012-2015 low-vol bull | 1,050 | 51.0% | +0.0264 | 1.13 | -10.3 |
| 2016-2019 late bull | 1,047 | 50.5% | +0.0277 | 1.14 | -12.2 |
| 2020-2021 covid era | 358 | 44.7% | -0.0333 | 0.86 | -23.9 |

### S17 Expected-move | <50% used

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 977 | 51.4% | +0.0066 | 1.03 | -16.5 |
| 2012-2015 low-vol bull | 998 | 51.3% | +0.0268 | 1.13 | -9.5 |
| 2016-2019 late bull | 995 | 50.8% | +0.0302 | 1.15 | -10.5 |
| 2020-2021 covid era | 330 | 44.8% | -0.0302 | 0.87 | -21.0 |

### S17 Expected-move | <75% used

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 982 | 51.4% | +0.0063 | 1.03 | -16.2 |
| 2012-2015 low-vol bull | 1,005 | 51.3% | +0.0283 | 1.14 | -9.5 |
| 2016-2019 late bull | 1,003 | 50.7% | +0.0290 | 1.15 | -11.2 |
| 2020-2021 covid era | 337 | 44.5% | -0.0356 | 0.85 | -22.3 |

### S18 Time-of-day | AFTERNOON

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 7,117 | 47.7% | -0.0015 | 0.96 | -15.5 |
| 2012-2015 low-vol bull | 7,185 | 46.8% | -0.0022 | 0.94 | -17.5 |
| 2016-2019 late bull | 7,248 | 48.1% | -0.0015 | 0.96 | -12.3 |
| 2020-2021 covid era | 2,489 | 47.9% | -0.0041 | 0.90 | -13.1 |

### S18 Time-of-day | FINAL_30

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 442 | 50.0% | +0.0021 | 1.03 | -5.0 |
| 2012-2015 low-vol bull | 450 | 48.9% | +0.0045 | 1.07 | -2.5 |
| 2016-2019 late bull | 526 | 51.5% | +0.0098 | 1.15 | -3.0 |
| 2020-2021 covid era | 178 | 55.6% | +0.0319 | 1.49 | -2.1 |

### S18 Time-of-day | MIDDAY

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 987 | 49.7% | +0.0049 | 1.03 | -14.7 |
| 2012-2015 low-vol bull | 1,015 | 52.3% | +0.0141 | 1.09 | -10.1 |
| 2016-2019 late bull | 1,017 | 51.0% | +0.0093 | 1.06 | -12.9 |
| 2020-2021 covid era | 342 | 50.3% | +0.0364 | 1.23 | -4.4 |

### S18 Time-of-day | MIDMORNING

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 3,879 | 48.7% | -0.0036 | 0.92 | -16.8 |
| 2012-2015 low-vol bull | 3,957 | 49.2% | +0.0003 | 1.01 | -5.7 |
| 2016-2019 late bull | 3,984 | 48.9% | -0.0022 | 0.95 | -11.7 |
| 2020-2021 covid era | 1,338 | 50.8% | +0.0021 | 1.05 | -4.3 |

### S18 Time-of-day | MORNING

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,962 | 46.3% | -0.0096 | 0.83 | -19.5 |
| 2012-2015 low-vol bull | 2,011 | 46.8% | -0.0122 | 0.79 | -26.0 |
| 2016-2019 late bull | 2,012 | 46.8% | -0.0080 | 0.85 | -18.0 |
| 2020-2021 covid era | 678 | 50.6% | -0.0003 | 0.99 | -4.1 |

### S18 Time-of-day | OPEN

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 986 | 50.2% | -0.0044 | 0.98 | -21.0 |
| 2012-2015 low-vol bull | 1,009 | 51.3% | +0.0285 | 1.14 | -7.5 |
| 2016-2019 late bull | 1,008 | 50.3% | +0.0265 | 1.14 | -9.7 |
| 2020-2021 covid era | 342 | 45.0% | -0.0221 | 0.90 | -22.0 |

### S19 MTF breakout | 2/4 agree

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,212 | 50.3% | +0.0058 | 1.03 | -20.9 |
| 2012-2015 low-vol bull | 1,238 | 50.1% | +0.0060 | 1.03 | -16.5 |
| 2016-2019 late bull | 1,256 | 48.2% | +0.0031 | 1.02 | -20.2 |
| 2020-2021 covid era | 440 | 49.1% | -0.0284 | 0.88 | -16.3 |

### S19 MTF breakout | 3/4 agree

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,018 | 49.8% | +0.0076 | 1.04 | -8.5 |
| 2012-2015 low-vol bull | 1,061 | 51.0% | -0.0006 | 1.00 | -20.6 |
| 2016-2019 late bull | 1,057 | 50.1% | +0.0325 | 1.19 | -11.4 |
| 2020-2021 covid era | 360 | 52.2% | +0.0020 | 1.01 | -12.6 |

### S19 MTF breakout | 4/4 agree

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 688 | 54.7% | +0.0244 | 1.18 | -7.9 |
| 2012-2015 low-vol bull | 713 | 52.2% | +0.0143 | 1.11 | -6.1 |
| 2016-2019 late bull | 717 | 53.0% | +0.0390 | 1.31 | -5.0 |
| 2020-2021 covid era | 243 | 49.8% | -0.0153 | 0.90 | -11.8 |

### S2 ORB immediate | or15

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 434 | 51.2% | -0.0039 | 0.98 | -10.1 |
| 2012-2015 low-vol bull | 461 | 51.0% | -0.0021 | 0.99 | -8.1 |
| 2016-2019 late bull | 460 | 50.4% | +0.0113 | 1.06 | -8.4 |
| 2020-2021 covid era | 151 | 49.7% | -0.0058 | 0.97 | -5.9 |

### S2 ORB immediate | or30

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 422 | 48.1% | +0.0081 | 1.03 | -12.6 |
| 2012-2015 low-vol bull | 452 | 50.0% | +0.0201 | 1.09 | -8.7 |
| 2016-2019 late bull | 447 | 46.1% | -0.0113 | 0.95 | -13.2 |
| 2020-2021 covid era | 151 | 47.0% | -0.0232 | 0.91 | -12.1 |

### S2 ORB immediate | or5

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 472 | 50.8% | +0.0189 | 1.08 | -11.9 |
| 2012-2015 low-vol bull | 468 | 52.4% | +0.0505 | 1.24 | -8.4 |
| 2016-2019 late bull | 467 | 49.9% | +0.0221 | 1.10 | -7.0 |
| 2020-2021 covid era | 158 | 46.2% | -0.0226 | 0.91 | -9.2 |

### S21 Gap continuation | gap>=0.25%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 715 | 53.1% | +0.0350 | 1.17 | -11.7 |
| 2012-2015 low-vol bull | 488 | 54.5% | +0.0489 | 1.25 | -9.4 |
| 2016-2019 late bull | 504 | 49.8% | +0.0099 | 1.04 | -9.0 |
| 2020-2021 covid era | 249 | 55.0% | +0.0311 | 1.16 | -6.7 |

### S21 Gap continuation | gap>=0.5%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 462 | 56.5% | +0.0641 | 1.32 | -7.4 |
| 2012-2015 low-vol bull | 217 | 58.5% | +0.0639 | 1.30 | -5.3 |
| 2016-2019 late bull | 220 | 53.2% | +0.0357 | 1.16 | -7.3 |
| 2020-2021 covid era | 159 | 60.4% | +0.0894 | 1.49 | -6.2 |

### S21 Gap continuation | gap>=1.0%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 217 | 61.8% | +0.0786 | 1.36 | -8.8 |
| 2012-2015 low-vol bull | 52 | 55.8% | +0.0205 | 1.08 | -6.0 |
| 2016-2019 late bull | 48 | 41.7% | -0.0964 | 0.70 | -7.0 |
| 2020-2021 covid era | 71 | 63.4% | +0.1005 | 1.58 | -3.4 |

### S22 Gap fade | gap>=0.25%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 4,674 | 48.7% | -0.0027 | 0.96 | -20.0 |
| 2012-2015 low-vol bull | 3,163 | 47.7% | +0.0014 | 1.02 | -6.2 |
| 2016-2019 late bull | 3,176 | 48.6% | +0.0043 | 1.07 | -7.3 |
| 2020-2021 covid era | 1,548 | 48.2% | +0.0014 | 1.02 | -7.4 |

### S22 Gap fade | gap>=0.5%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 4,851 | 48.3% | -0.0009 | 0.98 | -10.7 |
| 2012-2015 low-vol bull | 2,268 | 47.9% | +0.0002 | 1.00 | -5.2 |
| 2016-2019 late bull | 2,228 | 48.7% | -0.0003 | 0.99 | -6.0 |
| 2020-2021 covid era | 1,467 | 46.7% | -0.0067 | 0.87 | -10.6 |

### S22 Gap fade | gap>=1.0%

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 2,171 | 48.6% | -0.0025 | 0.95 | -11.2 |
| 2012-2015 low-vol bull | 587 | 50.4% | +0.0020 | 1.04 | -3.5 |
| 2016-2019 late bull | 482 | 48.8% | +0.0076 | 1.14 | -2.0 |
| 2020-2021 covid era | 638 | 43.7% | -0.0147 | 0.75 | -11.4 |

### S3 VWAP pullback | zoneA vwap

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 728 | 52.3% | +0.0154 | 1.08 | -10.5 |
| 2012-2015 low-vol bull | 706 | 50.3% | -0.0146 | 0.92 | -22.3 |
| 2016-2019 late bull | 725 | 52.0% | +0.0242 | 1.15 | -8.4 |
| 2020-2021 covid era | 215 | 50.2% | -0.0131 | 0.93 | -7.8 |

### S3 VWAP pullback | zoneB 0.25atr

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 992 | 52.0% | +0.0211 | 1.11 | -9.4 |
| 2012-2015 low-vol bull | 1,024 | 52.1% | +0.0157 | 1.08 | -14.3 |
| 2016-2019 late bull | 1,026 | 49.1% | +0.0169 | 1.08 | -18.4 |
| 2020-2021 covid era | 350 | 51.7% | -0.0175 | 0.92 | -14.4 |

### S3 VWAP pullback | zoneC 0.50atr

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,021 | 52.7% | +0.0273 | 1.14 | -8.0 |
| 2012-2015 low-vol bull | 1,053 | 51.9% | +0.0124 | 1.06 | -17.4 |
| 2016-2019 late bull | 1,055 | 48.9% | +0.0153 | 1.08 | -21.6 |
| 2020-2021 covid era | 360 | 50.3% | -0.0197 | 0.91 | -14.3 |

### S4 VWAP reclaim | chop<=2

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 656 | 51.2% | +0.0103 | 1.05 | -11.7 |
| 2012-2015 low-vol bull | 660 | 49.5% | +0.0375 | 1.19 | -10.3 |
| 2016-2019 late bull | 628 | 49.5% | +0.0355 | 1.19 | -7.8 |
| 2020-2021 covid era | 220 | 46.8% | -0.0310 | 0.87 | -11.1 |

### S4 VWAP reclaim | chop<=3

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 830 | 48.4% | -0.0110 | 0.95 | -20.1 |
| 2012-2015 low-vol bull | 847 | 50.2% | +0.0363 | 1.18 | -8.0 |
| 2016-2019 late bull | 805 | 49.2% | +0.0204 | 1.10 | -9.9 |
| 2020-2021 covid era | 279 | 41.9% | -0.0534 | 0.77 | -17.8 |

### S4 VWAP reclaim | chop<=4

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 927 | 48.0% | -0.0144 | 0.93 | -25.7 |
| 2012-2015 low-vol bull | 945 | 50.4% | +0.0318 | 1.16 | -10.3 |
| 2016-2019 late bull | 917 | 49.1% | +0.0186 | 1.10 | -9.4 |
| 2020-2021 covid era | 316 | 44.3% | -0.0361 | 0.84 | -16.6 |

### S4 VWAP reclaim | chop<=5

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 961 | 48.3% | -0.0116 | 0.95 | -24.9 |
| 2012-2015 low-vol bull | 988 | 50.5% | +0.0320 | 1.16 | -11.1 |
| 2016-2019 late bull | 969 | 49.3% | +0.0174 | 1.09 | -9.7 |
| 2020-2021 covid era | 331 | 44.7% | -0.0276 | 0.87 | -14.7 |

### S5 Premarket breakout | immediate

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 4 | 75.0% | +0.1751 | 3.37 | -0.3 |
| 2020-2021 covid era | 205 | 56.6% | +0.0569 | 1.39 | -4.4 |

### S5 Premarket breakout | retest

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 3 | 33.3% | -0.0354 | 0.40 | -0.2 |
| 2020-2021 covid era | 171 | 55.6% | +0.0613 | 1.43 | -3.0 |

### S6 Prev-day breakout | immediate

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 908 | 48.6% | -0.0062 | 0.92 | -10.1 |
| 2012-2015 low-vol bull | 949 | 47.4% | -0.0087 | 0.90 | -10.3 |
| 2016-2019 late bull | 911 | 51.7% | +0.0182 | 1.25 | -3.2 |
| 2020-2021 covid era | 319 | 47.6% | +0.0056 | 1.08 | -4.6 |

### S6 Prev-day breakout | retest

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,539 | 45.3% | -0.0106 | 0.79 | -16.4 |
| 2012-2015 low-vol bull | 1,520 | 44.2% | -0.0086 | 0.82 | -14.6 |
| 2016-2019 late bull | 1,443 | 48.8% | -0.0021 | 0.95 | -7.4 |
| 2020-2021 covid era | 532 | 46.4% | -0.0108 | 0.78 | -6.4 |

### S7 Failed breakout | prev-day levels

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 601 | 52.6% | +0.0302 | 1.18 | -9.3 |
| 2012-2015 low-vol bull | 624 | 49.8% | +0.0316 | 1.19 | -6.3 |
| 2016-2019 late bull | 577 | 53.4% | +0.0406 | 1.24 | -7.0 |
| 2020-2021 covid era | 201 | 50.2% | +0.0154 | 1.10 | -5.5 |

### S8 Liquidity sweep | reclaim<=10bars

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 583 | 50.1% | +0.0133 | 1.08 | -9.2 |
| 2012-2015 low-vol bull | 576 | 52.1% | +0.0365 | 1.22 | -5.4 |
| 2016-2019 late bull | 523 | 52.0% | +0.0036 | 1.02 | -7.5 |
| 2020-2021 covid era | 177 | 51.4% | +0.0460 | 1.29 | -3.7 |

### S8 Liquidity sweep | reclaim<=3bars

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 518 | 50.2% | +0.0044 | 1.03 | -10.1 |
| 2012-2015 low-vol bull | 485 | 51.3% | +0.0465 | 1.30 | -6.1 |
| 2016-2019 late bull | 443 | 49.9% | -0.0105 | 0.94 | -10.5 |
| 2020-2021 covid era | 157 | 53.5% | +0.0606 | 1.43 | -2.9 |

### S8 Liquidity sweep | reclaim<=5bars

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 546 | 50.4% | +0.0105 | 1.06 | -9.4 |
| 2012-2015 low-vol bull | 530 | 51.3% | +0.0336 | 1.20 | -5.9 |
| 2016-2019 late bull | 488 | 51.2% | +0.0037 | 1.02 | -6.7 |
| 2020-2021 covid era | 168 | 50.6% | +0.0330 | 1.21 | -3.7 |

### S9 Range reversal | range-filtered

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,431 | 50.2% | +0.0043 | 1.03 | -10.9 |
| 2012-2015 low-vol bull | 1,487 | 50.2% | +0.0017 | 1.01 | -11.7 |
| 2016-2019 late bull | 1,420 | 49.9% | -0.0073 | 0.96 | -26.6 |
| 2020-2021 covid era | 451 | 49.7% | -0.0062 | 0.96 | -6.4 |

### S9 Range reversal | unfiltered

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 8,722 | 50.7% | +0.0009 | 1.02 | -10.8 |
| 2012-2015 low-vol bull | 8,889 | 50.3% | -0.0030 | 0.93 | -32.1 |
| 2016-2019 late bull | 8,718 | 49.2% | -0.0029 | 0.93 | -26.2 |
| 2020-2021 covid era | 3,196 | 49.1% | +0.0003 | 1.01 | -8.0 |

## Where the edge sits


### BASELINE random | 2/session


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 944 | 51.2% | +0.0026 | 1.06 | -3.2 |
| EXPANSION | 200 | 45.5% | -0.0258 | 0.70 | -6.6 |
| HIGH_VOLATILITY_REVERSAL | 256 | 41.8% | -0.0127 | 0.87 | -4.8 |
| HIGH_VOLATILITY_TREND | 15 | 60.0% | +0.0461 | 1.94 | -0.4 |
| RANGE | 3,498 | 49.2% | +0.0016 | 1.03 | -7.6 |
| STRONG_BEAR_TREND | 40 | 42.5% | -0.0055 | 0.91 | -1.3 |
| STRONG_BULL_TREND | 89 | 50.6% | -0.0004 | 0.99 | -1.0 |
| UNCERTAIN | 158 | 41.8% | -0.0056 | 0.94 | -3.4 |
| WEAK_BEAR_TREND | 425 | 50.4% | +0.0072 | 1.10 | -1.9 |
| WEAK_BULL_TREND | 508 | 47.2% | -0.0073 | 0.87 | -5.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 2,049 | 49.8% | -0.0009 | 0.98 | -7.0 |
| FINAL_30 | 32 | 28.1% | -0.0467 | 0.44 | -1.5 |
| MIDDAY | 2,043 | 47.8% | +0.0006 | 1.01 | -7.4 |
| MIDMORNING | 1,061 | 50.2% | +0.0050 | 1.09 | -5.5 |
| MORNING | 519 | 47.4% | -0.0049 | 0.93 | -5.3 |
| OPEN | 429 | 48.3% | -0.0050 | 0.94 | -6.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,926 | 50.8% | +0.0010 | 1.02 | -6.7 |
| SHORT | 3,207 | 47.0% | -0.0013 | 0.98 | -9.1 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 26 | 42.3% | -0.0050 | 0.93 | -1.0 |
| stop | 84 | 0.0% | -0.5000 | 0.00 | -42.0 |
| stop_and_target_same_bar | 1 | 0.0% | -0.5000 | 0.00 | -0.5 |
| target | 80 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 5,942 | 48.8% | +0.0002 | 1.00 | -7.3 |

### LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets)


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 3,237 | 47.2% | -0.0047 | 0.90 | -15.9 |
| EXPANSION | 1,083 | 47.6% | -0.0067 | 0.91 | -11.3 |
| HIGH_VOLATILITY_REVERSAL | 1,418 | 49.5% | +0.0047 | 1.05 | -5.6 |
| HIGH_VOLATILITY_TREND | 87 | 48.3% | -0.0061 | 0.94 | -1.9 |
| RANGE | 16,325 | 49.0% | +0.0009 | 1.02 | -10.5 |
| STRONG_BEAR_TREND | 230 | 54.3% | +0.0161 | 1.28 | -1.3 |
| STRONG_BULL_TREND | 517 | 48.9% | +0.0037 | 1.10 | -2.6 |
| WEAK_BEAR_TREND | 2,080 | 48.2% | -0.0006 | 0.99 | -8.1 |
| WEAK_BULL_TREND | 2,530 | 50.2% | +0.0031 | 1.06 | -7.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 10,129 | 49.5% | +0.0002 | 1.00 | -13.6 |
| FINAL_30 | 161 | 55.9% | +0.0230 | 1.41 | -1.3 |
| MIDDAY | 9,795 | 48.7% | +0.0019 | 1.04 | -11.5 |
| MIDMORNING | 4,880 | 49.1% | +0.0026 | 1.04 | -5.3 |
| MORNING | 2,542 | 46.0% | -0.0105 | 0.85 | -32.8 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 15,077 | 51.0% | +0.0017 | 1.04 | -9.7 |
| SHORT | 12,430 | 46.3% | -0.0012 | 0.98 | -29.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 105 | 59.0% | +0.0241 | 1.42 | -2.1 |
| stop | 33 | 0.0% | -1.0000 | 0.00 | -33.0 |
| target | 8 | 100.0% | +1.5000 | inf | 0.0 |
| time_stop | 27,361 | 48.9% | +0.0010 | 1.02 | -12.1 |

### LIVE SPY_0DTE (ORB) | 5-min bars (5M)


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 3,267 | 46.8% | -0.0032 | 0.89 | -11.0 |
| EXPANSION | 1,667 | 49.6% | -0.0005 | 0.99 | -8.9 |
| HIGH_VOLATILITY_REVERSAL | 2,119 | 48.2% | -0.0007 | 0.99 | -9.2 |
| HIGH_VOLATILITY_TREND | 138 | 52.2% | +0.0084 | 1.13 | -2.2 |
| RANGE | 22,974 | 47.6% | -0.0001 | 1.00 | -14.3 |
| STRONG_BEAR_TREND | 327 | 48.6% | +0.0004 | 1.01 | -1.7 |
| STRONG_BULL_TREND | 740 | 48.0% | -0.0012 | 0.96 | -2.9 |
| WEAK_BEAR_TREND | 2,892 | 47.2% | -0.0010 | 0.98 | -7.8 |
| WEAK_BULL_TREND | 3,696 | 49.0% | +0.0012 | 1.03 | -3.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 14,535 | 48.8% | -0.0002 | 0.99 | -10.9 |
| FINAL_30 | 625 | 49.9% | +0.0060 | 1.13 | -3.4 |
| MIDDAY | 13,757 | 47.3% | +0.0003 | 1.01 | -8.1 |
| MIDMORNING | 6,298 | 47.7% | +0.0008 | 1.02 | -4.6 |
| MORNING | 2,605 | 44.3% | -0.0090 | 0.83 | -25.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 20,889 | 49.3% | +0.0002 | 1.01 | -11.3 |
| SHORT | 16,931 | 46.0% | -0.0010 | 0.98 | -26.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 10 | 70.0% | +0.0558 | 10.71 | -0.0 |
| stop | 10 | 0.0% | -1.0000 | 0.00 | -10.0 |
| target | 5 | 100.0% | +1.5000 | inf | 0.0 |
| time_stop | 37,795 | 47.8% | -0.0003 | 0.99 | -18.7 |

### LIVE SPY_EXPANSION_LEVEL | deployed rules


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 103 | 53.4% | +0.0009 | 1.01 | -2.5 |
| EXPANSION | 20 | 60.0% | +0.1288 | 2.27 | -1.2 |
| HIGH_VOLATILITY_REVERSAL | 31 | 35.5% | -0.1545 | 0.42 | -4.8 |
| HIGH_VOLATILITY_TREND | 3 | 33.3% | -0.1667 | 0.50 | -0.5 |
| RANGE | 331 | 52.3% | -0.0020 | 0.99 | -5.5 |
| STRONG_BEAR_TREND | 7 | 71.4% | +0.1649 | 2.76 | -0.7 |
| STRONG_BULL_TREND | 14 | 71.4% | +0.1477 | 4.21 | -0.4 |
| UNCERTAIN | 172 | 51.7% | -0.0064 | 0.97 | -4.1 |
| WEAK_BEAR_TREND | 51 | 56.9% | +0.0417 | 1.23 | -2.3 |
| WEAK_BULL_TREND | 86 | 47.7% | -0.0534 | 0.72 | -5.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 138 | 47.1% | -0.0500 | 0.66 | -6.9 |
| FINAL_30 | 36 | 52.8% | +0.0049 | 1.09 | -0.5 |
| MIDDAY | 157 | 54.1% | +0.0403 | 1.28 | -3.1 |
| MIDMORNING | 232 | 52.6% | -0.0155 | 0.91 | -6.9 |
| MORNING | 67 | 56.7% | +0.0269 | 1.15 | -2.6 |
| OPEN | 188 | 51.6% | -0.0077 | 0.96 | -5.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 571 | 53.9% | +0.0030 | 1.02 | -5.7 |
| SHORT | 247 | 47.8% | -0.0216 | 0.90 | -8.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 431 | 59.2% | +0.0438 | 1.75 | -1.3 |
| stop | 215 | 0.0% | -0.5000 | 0.00 | -107.5 |
| stop_and_target_same_bar | 1 | 0.0% | -0.5000 | 0.00 | -0.5 |
| target | 171 | 100.0% | +0.5000 | inf | 0.0 |

### LIVE SPY_KEY_LEVELS | deployed rules


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 2,201 | 49.6% | +0.0125 | 1.07 | -16.7 |
| EXPANSION | 33 | 39.4% | -0.0594 | 0.82 | -7.0 |
| HIGH_VOLATILITY_REVERSAL | 52 | 51.9% | +0.0265 | 1.09 | -3.7 |
| HIGH_VOLATILITY_TREND | 5 | 60.0% | +0.3312 | 8.77 | -0.2 |
| RANGE | 600 | 52.2% | +0.0371 | 1.15 | -7.8 |
| STRONG_BEAR_TREND | 4 | 50.0% | -0.0517 | 0.79 | -1.0 |
| STRONG_BULL_TREND | 3 | 33.3% | -0.1156 | 0.58 | -0.4 |
| WEAK_BEAR_TREND | 341 | 45.5% | -0.0212 | 0.92 | -22.0 |
| WEAK_BULL_TREND | 227 | 57.7% | +0.0974 | 1.57 | -3.9 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 73 | 46.6% | +0.0357 | 1.18 | -3.6 |
| FINAL_30 | 3 | 66.7% | -0.0515 | 0.38 | -0.2 |
| MIDDAY | 50 | 44.0% | -0.0142 | 0.95 | -4.4 |
| MIDMORNING | 37 | 48.6% | -0.0296 | 0.90 | -5.5 |
| MORNING | 154 | 57.1% | +0.1037 | 1.71 | -2.5 |
| OPEN | 3,149 | 50.0% | +0.0154 | 1.08 | -21.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,767 | 54.5% | +0.0324 | 1.18 | -10.9 |
| SHORT | 1,699 | 45.6% | +0.0046 | 1.02 | -20.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,204 | 53.5% | +0.0815 | 1.58 | -7.9 |
| stop | 240 | 0.0% | -1.0000 | 0.00 | -240.0 |
| target | 22 | 100.0% | +2.0000 | inf | 0.0 |

### PB1 Opening gap fade | spec thresholds


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 12 | 58.3% | +0.0485 | 2.44 | -0.2 |
| EXPANSION | 1 | 0.0% | -0.5000 | 0.00 | -0.5 |
| RANGE | 16 | 62.5% | +0.0299 | 1.74 | -0.6 |
| WEAK_BEAR_TREND | 10 | 60.0% | +0.0769 | 2.35 | -0.3 |
| WEAK_BULL_TREND | 7 | 71.4% | +0.0658 | 2.83 | -0.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MORNING | 17 | 52.9% | +0.0349 | 1.51 | -0.6 |
| OPEN | 29 | 65.5% | +0.0412 | 1.99 | -0.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 19 | 57.9% | +0.0064 | 1.12 | -0.8 |
| SHORT | 27 | 63.0% | +0.0617 | 2.26 | -0.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 1 | 0.0% | -0.5000 | 0.00 | -0.5 |
| target | 1 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 44 | 61.4% | +0.0407 | 1.96 | -0.8 |

### PB2 Momentum squeeze | eff>=0.65


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 13 | 30.8% | -0.0465 | 0.68 | -0.9 |
| EXPANSION | 4 | 75.0% | +0.1941 | 9.31 | -0.1 |
| HIGH_VOLATILITY_REVERSAL | 5 | 20.0% | -0.3129 | 0.04 | -1.6 |
| RANGE | 70 | 51.4% | -0.0039 | 0.97 | -3.1 |
| STRONG_BEAR_TREND | 1 | 0.0% | -0.5977 | 0.00 | -0.6 |
| STRONG_BULL_TREND | 6 | 33.3% | +0.0013 | 1.03 | -0.2 |
| WEAK_BEAR_TREND | 3 | 100.0% | +0.3048 | inf | 0.0 |
| WEAK_BULL_TREND | 12 | 41.7% | +0.0759 | 1.43 | -1.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 49 | 44.9% | -0.0163 | 0.87 | -3.0 |
| MIDDAY | 39 | 53.8% | -0.0026 | 0.98 | -1.5 |
| MIDMORNING | 16 | 37.5% | +0.0294 | 1.25 | -1.4 |
| MORNING | 7 | 71.4% | +0.1998 | 2.10 | -1.3 |
| OPEN | 3 | 0.0% | -0.4657 | 0.00 | -1.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 86 | 47.7% | -0.0128 | 0.90 | -3.2 |
| SHORT | 28 | 46.4% | +0.0240 | 1.17 | -1.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 105 | 49.5% | +0.0269 | 1.28 | -2.5 |
| stop | 7 | 0.0% | -0.7500 | 0.00 | -5.3 |
| target | 2 | 100.0% | +1.0000 | inf | 0.0 |

### S1 ORB retest | or15


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 2,154 | 49.0% | +0.0080 | 1.05 | -19.7 |
| EXPANSION | 11 | 36.4% | -0.0414 | 0.87 | -2.2 |
| HIGH_VOLATILITY_REVERSAL | 20 | 70.0% | +0.3346 | 4.02 | -1.5 |
| RANGE | 658 | 48.2% | -0.0253 | 0.90 | -21.8 |
| WEAK_BEAR_TREND | 276 | 43.8% | -0.0144 | 0.95 | -11.8 |
| WEAK_BULL_TREND | 205 | 48.8% | -0.0120 | 0.95 | -7.4 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 52 | 48.1% | +0.0353 | 1.28 | -3.8 |
| MIDDAY | 45 | 46.7% | +0.0320 | 1.22 | -2.3 |
| MIDMORNING | 170 | 46.5% | -0.0314 | 0.85 | -6.8 |
| MORNING | 807 | 46.0% | -0.0153 | 0.92 | -20.9 |
| OPEN | 2,250 | 49.6% | +0.0066 | 1.03 | -24.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,691 | 53.2% | +0.0169 | 1.09 | -13.5 |
| SHORT | 1,633 | 43.7% | -0.0173 | 0.92 | -45.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,599 | 52.7% | +0.0464 | 1.39 | -5.8 |
| stop | 483 | 0.0% | -0.7500 | 0.00 | -362.2 |
| target | 242 | 100.0% | +1.0000 | inf | 0.0 |

### S1 ORB retest | or30


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,441 | 47.3% | -0.0013 | 0.99 | -17.1 |
| EXPANSION | 14 | 42.9% | -0.0690 | 0.84 | -4.3 |
| HIGH_VOLATILITY_REVERSAL | 17 | 88.2% | +0.4101 | 15.89 | -0.5 |
| RANGE | 795 | 48.2% | -0.0015 | 0.99 | -17.9 |
| WEAK_BEAR_TREND | 501 | 45.5% | -0.0113 | 0.96 | -20.8 |
| WEAK_BULL_TREND | 499 | 52.9% | +0.0049 | 1.02 | -9.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 55 | 45.5% | +0.0393 | 1.39 | -3.4 |
| FINAL_30 | 1 | 100.0% | +0.0303 | inf | 0.0 |
| MIDDAY | 141 | 48.2% | +0.0056 | 1.04 | -6.5 |
| MIDMORNING | 617 | 48.3% | -0.0103 | 0.95 | -13.1 |
| MORNING | 2,453 | 48.3% | +0.0013 | 1.01 | -29.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,743 | 52.4% | +0.0064 | 1.04 | -15.3 |
| SHORT | 1,524 | 43.5% | -0.0075 | 0.97 | -36.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,049 | 51.1% | +0.0517 | 1.35 | -6.8 |
| stop | 198 | 0.0% | -1.0000 | 0.00 | -198.0 |
| target | 20 | 100.0% | +2.0000 | inf | 0.0 |

### S1 ORB retest | or5


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 458 | 50.0% | +0.0199 | 1.12 | -9.4 |
| EXPANSION | 5 | 20.0% | -0.0745 | 0.76 | -1.5 |
| HIGH_VOLATILITY_REVERSAL | 13 | 46.2% | +0.0825 | 1.29 | -1.7 |
| RANGE | 111 | 38.7% | -0.0944 | 0.64 | -11.6 |
| STRONG_BEAR_TREND | 1 | 0.0% | -0.3018 | 0.00 | -0.3 |
| UNCERTAIN | 2,578 | 50.7% | +0.0223 | 1.11 | -15.3 |
| WEAK_BEAR_TREND | 16 | 31.2% | -0.1428 | 0.51 | -2.7 |
| WEAK_BULL_TREND | 16 | 56.2% | +0.0510 | 1.34 | -1.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 29 | 27.6% | -0.0494 | 0.71 | -2.9 |
| MIDDAY | 26 | 42.3% | -0.0475 | 0.77 | -2.4 |
| MIDMORNING | 47 | 53.2% | -0.0100 | 0.94 | -3.0 |
| MORNING | 136 | 39.7% | -0.0288 | 0.86 | -9.4 |
| OPEN | 2,960 | 50.7% | +0.0210 | 1.10 | -21.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,610 | 54.3% | +0.0322 | 1.17 | -9.2 |
| SHORT | 1,588 | 45.6% | +0.0021 | 1.01 | -28.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,935 | 53.7% | +0.0859 | 1.61 | -8.0 |
| stop | 241 | 0.0% | -1.0000 | 0.00 | -241.0 |
| target | 22 | 100.0% | +2.0000 | inf | 0.0 |

### S10 VWAP reversion | 0.5atr


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| RANGE | 418 | 52.2% | +0.0279 | 1.19 | -10.7 |
| UNCERTAIN | 2 | 50.0% | +0.1250 | 1.33 | -0.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 238 | 50.8% | +0.0179 | 1.14 | -6.5 |
| FINAL_30 | 3 | 33.3% | -0.0226 | 0.72 | -0.2 |
| MIDDAY | 158 | 53.2% | +0.0306 | 1.17 | -6.8 |
| MIDMORNING | 18 | 61.1% | +0.1320 | 1.58 | -1.8 |
| MORNING | 1 | 100.0% | +0.2666 | inf | 0.0 |
| OPEN | 2 | 50.0% | +0.1250 | 1.33 | -0.8 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 251 | 58.6% | +0.0663 | 1.42 | -4.3 |
| SHORT | 169 | 42.6% | -0.0279 | 0.80 | -9.9 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 366 | 55.2% | +0.0619 | 1.64 | -2.8 |
| stop | 37 | 0.0% | -0.7500 | 0.00 | -27.8 |
| target | 17 | 100.0% | +1.0000 | inf | 0.0 |

### S10 VWAP reversion | 0.75atr


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| RANGE | 88 | 50.0% | -0.0245 | 0.67 | -3.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 65 | 53.8% | -0.0128 | 0.82 | -2.2 |
| FINAL_30 | 2 | 0.0% | -0.1424 | 0.00 | -0.3 |
| MIDDAY | 21 | 42.9% | -0.0492 | 0.35 | -1.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 64 | 48.4% | -0.0337 | 0.59 | -2.7 |
| SHORT | 24 | 54.2% | +0.0001 | 1.00 | -0.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| time_stop | 88 | 50.0% | -0.0245 | 0.67 | -3.2 |

### S11 Compression break | 3bars quiet


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 88 | 43.2% | -0.0308 | 0.74 | -4.4 |
| EXPANSION | 33 | 69.7% | +0.1090 | 2.16 | -1.4 |
| HIGH_VOLATILITY_REVERSAL | 24 | 45.8% | -0.0283 | 0.86 | -3.1 |
| HIGH_VOLATILITY_TREND | 2 | 0.0% | -0.2630 | 0.00 | -0.5 |
| RANGE | 490 | 51.8% | +0.0126 | 1.11 | -6.2 |
| STRONG_BEAR_TREND | 3 | 100.0% | +0.0819 | inf | 0.0 |
| STRONG_BULL_TREND | 10 | 40.0% | -0.0304 | 0.68 | -0.6 |
| WEAK_BEAR_TREND | 42 | 45.2% | +0.0463 | 1.34 | -2.1 |
| WEAK_BULL_TREND | 62 | 40.3% | -0.0454 | 0.71 | -3.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 255 | 48.2% | -0.0023 | 0.98 | -4.7 |
| FINAL_30 | 5 | 40.0% | -0.0542 | 0.31 | -0.3 |
| MIDDAY | 337 | 50.4% | +0.0066 | 1.06 | -5.5 |
| MIDMORNING | 126 | 51.6% | +0.0030 | 1.02 | -4.1 |
| MORNING | 31 | 54.8% | +0.1030 | 2.09 | -0.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 376 | 54.0% | +0.0045 | 1.04 | -4.8 |
| SHORT | 378 | 46.0% | +0.0085 | 1.07 | -6.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 561 | 48.7% | -0.0046 | 0.94 | -7.4 |
| stop | 89 | 0.0% | -0.5000 | 0.00 | -44.5 |
| target | 104 | 100.0% | +0.5000 | inf | 0.0 |

### S11 Compression break | 5bars quiet


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 13 | 38.5% | +0.0259 | 1.63 | -0.4 |
| EXPANSION | 5 | 60.0% | -0.0115 | 0.92 | -0.5 |
| HIGH_VOLATILITY_REVERSAL | 3 | 0.0% | -0.3011 | 0.00 | -0.9 |
| RANGE | 64 | 48.4% | +0.0405 | 1.49 | -1.9 |
| STRONG_BULL_TREND | 2 | 50.0% | +0.0142 | 1.17 | -0.2 |
| WEAK_BEAR_TREND | 4 | 25.0% | -0.1842 | 0.54 | -1.5 |
| WEAK_BULL_TREND | 10 | 50.0% | -0.0012 | 0.99 | -0.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 36 | 33.3% | -0.0204 | 0.76 | -1.5 |
| MIDDAY | 49 | 53.1% | +0.0272 | 1.28 | -1.5 |
| MIDMORNING | 13 | 46.2% | +0.0053 | 1.03 | -1.0 |
| MORNING | 3 | 66.7% | +0.1936 | 5.93 | -0.1 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 54 | 53.7% | +0.0514 | 1.79 | -0.6 |
| SHORT | 47 | 36.2% | -0.0325 | 0.78 | -3.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 100 | 46.0% | +0.0225 | 1.24 | -2.0 |
| stop | 1 | 0.0% | -1.0000 | 0.00 | -1.0 |

### S12 First pullback | 0.5atr drive


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| EXPANSION | 23 | 47.8% | -0.0005 | 1.00 | -3.8 |
| HIGH_VOLATILITY_REVERSAL | 9 | 66.7% | +0.3246 | 2.71 | -1.7 |
| RANGE | 53 | 41.5% | -0.0444 | 0.82 | -5.8 |
| STRONG_BULL_TREND | 2 | 50.0% | -0.3419 | 0.09 | -0.7 |
| WEAK_BEAR_TREND | 64 | 60.9% | +0.1402 | 1.73 | -2.6 |
| WEAK_BULL_TREND | 64 | 48.4% | +0.0165 | 1.07 | -3.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 6 | 66.7% | +0.2141 | 3.02 | -0.6 |
| MIDDAY | 25 | 44.0% | -0.0075 | 0.97 | -2.5 |
| MIDMORNING | 67 | 50.7% | +0.0545 | 1.25 | -1.9 |
| MORNING | 96 | 50.0% | +0.0461 | 1.21 | -3.6 |
| OPEN | 21 | 61.9% | +0.0343 | 1.12 | -1.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 105 | 54.3% | +0.0625 | 1.30 | -4.0 |
| SHORT | 110 | 48.2% | +0.0304 | 1.13 | -5.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 143 | 56.6% | +0.0920 | 1.83 | -2.4 |
| stop | 42 | 0.0% | -0.7500 | 0.00 | -31.5 |
| stop_and_target_same_bar | 1 | 0.0% | -0.7500 | 0.00 | -0.8 |
| target | 29 | 100.0% | +1.0000 | inf | 0.0 |

### S12 First pullback | 0.75atr drive


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| EXPANSION | 10 | 50.0% | -0.0236 | 0.90 | -2.0 |
| HIGH_VOLATILITY_REVERSAL | 5 | 40.0% | -0.0409 | 0.83 | -1.2 |
| RANGE | 1 | 0.0% | -0.2069 | 0.00 | -0.2 |
| WEAK_BEAR_TREND | 7 | 57.1% | -0.0604 | 0.72 | -1.0 |
| WEAK_BULL_TREND | 10 | 60.0% | +0.0545 | 1.27 | -0.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDDAY | 7 | 42.9% | -0.0945 | 0.61 | -1.0 |
| MIDMORNING | 9 | 44.4% | -0.0597 | 0.76 | -1.5 |
| MORNING | 10 | 60.0% | +0.1096 | 1.58 | -0.5 |
| OPEN | 7 | 57.1% | -0.0604 | 0.72 | -1.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 13 | 61.5% | +0.1031 | 1.61 | -1.2 |
| SHORT | 20 | 45.0% | -0.0933 | 0.63 | -2.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 7 | 57.1% | -0.0751 | 0.36 | -0.6 |
| stop | 13 | 0.0% | -0.5000 | 0.00 | -6.5 |
| target | 13 | 100.0% | +0.5000 | inf | 0.0 |

### S13 Structure reversal | no vwap filter


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 4,941 | 47.6% | -0.0008 | 0.98 | -12.9 |
| EXPANSION | 993 | 49.8% | +0.0007 | 1.01 | -5.3 |
| HIGH_VOLATILITY_REVERSAL | 1,425 | 48.3% | -0.0008 | 0.99 | -6.0 |
| HIGH_VOLATILITY_TREND | 77 | 45.5% | -0.0170 | 0.81 | -2.4 |
| RANGE | 18,940 | 47.9% | -0.0014 | 0.96 | -29.9 |
| STRONG_BEAR_TREND | 209 | 49.3% | -0.0029 | 0.94 | -1.5 |
| STRONG_BULL_TREND | 469 | 47.1% | +0.0011 | 1.04 | -2.0 |
| UNCERTAIN | 1,322 | 50.0% | +0.0003 | 1.01 | -7.4 |
| WEAK_BEAR_TREND | 2,089 | 49.4% | -0.0010 | 0.98 | -11.9 |
| WEAK_BULL_TREND | 2,639 | 48.3% | -0.0020 | 0.95 | -6.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 11,098 | 48.2% | -0.0007 | 0.98 | -18.1 |
| FINAL_30 | 210 | 52.4% | +0.0056 | 1.13 | -1.7 |
| MIDDAY | 10,844 | 47.7% | -0.0003 | 0.99 | -10.3 |
| MIDMORNING | 5,587 | 48.1% | -0.0033 | 0.93 | -25.4 |
| MORNING | 2,866 | 47.7% | -0.0042 | 0.92 | -13.9 |
| OPEN | 2,499 | 49.6% | +0.0006 | 1.01 | -6.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 15,824 | 49.8% | -0.0007 | 0.98 | -28.0 |
| SHORT | 17,280 | 46.7% | -0.0016 | 0.96 | -39.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 7 | 42.9% | -0.0564 | 0.19 | -0.5 |
| stop | 108 | 0.0% | -0.5000 | 0.00 | -54.0 |
| stop_and_target_same_bar | 1 | 0.0% | -0.5000 | 0.00 | -0.5 |
| target | 160 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 32,828 | 48.1% | -0.0020 | 0.95 | -70.3 |

### S13 Structure reversal | vwap confirmed


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 2,750 | 48.4% | -0.0012 | 0.98 | -8.8 |
| EXPANSION | 557 | 51.2% | -0.0031 | 0.96 | -9.8 |
| HIGH_VOLATILITY_REVERSAL | 711 | 49.1% | +0.0067 | 1.07 | -5.5 |
| HIGH_VOLATILITY_TREND | 41 | 48.8% | -0.0165 | 0.87 | -2.8 |
| RANGE | 9,791 | 47.8% | -0.0003 | 0.99 | -14.0 |
| STRONG_BEAR_TREND | 94 | 56.4% | +0.0183 | 1.34 | -1.2 |
| STRONG_BULL_TREND | 197 | 51.8% | +0.0163 | 1.53 | -2.3 |
| UNCERTAIN | 1,130 | 50.3% | +0.0030 | 1.04 | -9.3 |
| WEAK_BEAR_TREND | 1,076 | 48.8% | +0.0005 | 1.01 | -6.5 |
| WEAK_BULL_TREND | 1,308 | 51.0% | +0.0011 | 1.02 | -5.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 5,754 | 48.4% | -0.0002 | 1.00 | -13.1 |
| FINAL_30 | 113 | 44.2% | -0.0007 | 0.99 | -1.4 |
| MIDDAY | 5,521 | 48.6% | +0.0016 | 1.03 | -8.8 |
| MIDMORNING | 2,919 | 48.6% | +0.0014 | 1.02 | -12.3 |
| MORNING | 1,468 | 48.7% | -0.0015 | 0.98 | -9.0 |
| OPEN | 1,880 | 49.7% | -0.0018 | 0.98 | -10.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 9,107 | 50.5% | +0.0015 | 1.03 | -6.8 |
| SHORT | 8,548 | 46.7% | -0.0009 | 0.99 | -25.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 74 | 45.9% | +0.0060 | 1.08 | -1.1 |
| stop | 16 | 0.0% | -1.0000 | 0.00 | -16.0 |
| target | 7 | 100.0% | +1.5000 | inf | 0.0 |
| time_stop | 17,558 | 48.7% | +0.0006 | 1.01 | -14.6 |

### S14 Momentum continuation | adx20 aligned


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,569 | 49.2% | +0.0088 | 1.05 | -11.7 |
| EXPANSION | 40 | 35.0% | -0.1761 | 0.55 | -7.0 |
| HIGH_VOLATILITY_REVERSAL | 165 | 52.1% | +0.0626 | 1.26 | -3.7 |
| HIGH_VOLATILITY_TREND | 15 | 40.0% | +0.0545 | 1.23 | -1.3 |
| RANGE | 877 | 48.1% | +0.0007 | 1.00 | -13.1 |
| STRONG_BEAR_TREND | 15 | 46.7% | -0.0983 | 0.61 | -2.8 |
| STRONG_BULL_TREND | 14 | 57.1% | +0.0290 | 1.24 | -1.3 |
| UNCERTAIN | 223 | 45.7% | -0.0100 | 0.96 | -8.6 |
| WEAK_BEAR_TREND | 579 | 45.4% | -0.0171 | 0.93 | -19.8 |
| WEAK_BULL_TREND | 507 | 50.7% | -0.0209 | 0.91 | -18.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 310 | 50.3% | -0.0048 | 0.97 | -10.1 |
| FINAL_30 | 10 | 90.0% | +0.2654 | 12.37 | -0.2 |
| MIDDAY | 318 | 53.8% | +0.0526 | 1.30 | -5.3 |
| MIDMORNING | 552 | 45.5% | -0.0162 | 0.92 | -19.5 |
| MORNING | 1,612 | 47.4% | -0.0046 | 0.98 | -24.0 |
| OPEN | 1,202 | 48.8% | -0.0058 | 0.97 | -23.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,138 | 52.3% | +0.0062 | 1.03 | -15.1 |
| SHORT | 1,866 | 43.8% | -0.0100 | 0.96 | -30.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,128 | 52.8% | +0.0483 | 1.42 | -5.7 |
| stop | 590 | 0.0% | -0.7500 | 0.00 | -442.5 |
| target | 286 | 100.0% | +1.0000 | inf | 0.0 |

### S14 Momentum continuation | adx25 aligned


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,322 | 49.5% | +0.0094 | 1.06 | -10.0 |
| EXPANSION | 25 | 36.0% | -0.1731 | 0.62 | -6.2 |
| HIGH_VOLATILITY_REVERSAL | 93 | 50.5% | +0.0471 | 1.19 | -8.4 |
| HIGH_VOLATILITY_TREND | 11 | 36.4% | -0.0169 | 0.94 | -2.4 |
| RANGE | 871 | 50.4% | +0.0200 | 1.11 | -11.7 |
| STRONG_BEAR_TREND | 5 | 40.0% | +0.0128 | 1.08 | -0.8 |
| STRONG_BULL_TREND | 6 | 50.0% | +0.1876 | 4.24 | -0.2 |
| UNCERTAIN | 201 | 46.8% | +0.0059 | 1.03 | -9.3 |
| WEAK_BEAR_TREND | 531 | 44.3% | -0.0174 | 0.93 | -20.0 |
| WEAK_BULL_TREND | 478 | 51.0% | -0.0165 | 0.93 | -15.9 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 158 | 51.3% | +0.0372 | 1.29 | -2.6 |
| FINAL_30 | 4 | 75.0% | +0.4467 | 68.14 | -0.0 |
| MIDDAY | 298 | 55.0% | +0.0097 | 1.06 | -8.9 |
| MIDMORNING | 717 | 46.9% | +0.0180 | 1.10 | -9.4 |
| MORNING | 1,331 | 48.1% | -0.0076 | 0.96 | -32.2 |
| OPEN | 1,035 | 49.0% | +0.0016 | 1.01 | -16.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,927 | 52.4% | +0.0121 | 1.07 | -15.0 |
| SHORT | 1,616 | 44.7% | -0.0051 | 0.98 | -27.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,232 | 51.3% | +0.0452 | 1.32 | -7.6 |
| stop | 239 | 0.0% | -1.0000 | 0.00 | -239.0 |
| target | 72 | 100.0% | +1.5000 | inf | 0.0 |

### S14 Momentum continuation | adx25 unaligned


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,430 | 51.3% | +0.0211 | 1.13 | -12.8 |
| EXPANSION | 24 | 33.3% | -0.0657 | 0.75 | -4.4 |
| HIGH_VOLATILITY_REVERSAL | 102 | 51.0% | +0.0467 | 1.18 | -8.0 |
| HIGH_VOLATILITY_TREND | 11 | 45.5% | -0.0080 | 0.97 | -2.3 |
| RANGE | 909 | 50.8% | +0.0161 | 1.08 | -8.7 |
| STRONG_BEAR_TREND | 9 | 33.3% | -0.2129 | 0.26 | -2.2 |
| STRONG_BULL_TREND | 5 | 60.0% | +0.2680 | 5.34 | -0.2 |
| UNCERTAIN | 590 | 48.6% | +0.0185 | 1.08 | -11.9 |
| WEAK_BEAR_TREND | 270 | 43.3% | -0.0385 | 0.87 | -12.3 |
| WEAK_BULL_TREND | 229 | 51.5% | +0.0183 | 1.10 | -11.6 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 145 | 49.0% | +0.0237 | 1.15 | -5.9 |
| FINAL_30 | 1 | 0.0% | -0.0266 | 0.00 | -0.0 |
| MIDDAY | 243 | 56.4% | +0.0189 | 1.12 | -6.3 |
| MIDMORNING | 537 | 48.2% | +0.0135 | 1.08 | -11.0 |
| MORNING | 579 | 46.6% | -0.0202 | 0.91 | -22.8 |
| OPEN | 2,074 | 50.7% | +0.0233 | 1.12 | -15.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,770 | 54.4% | +0.0251 | 1.14 | -9.2 |
| SHORT | 1,809 | 45.7% | +0.0042 | 1.02 | -25.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,249 | 52.6% | +0.0560 | 1.40 | -5.7 |
| stop | 250 | 0.0% | -1.0000 | 0.00 | -250.0 |
| target | 80 | 100.0% | +1.5000 | inf | 0.0 |

### S14 Momentum continuation | adx30 aligned


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,035 | 49.9% | +0.0063 | 1.04 | -10.7 |
| EXPANSION | 30 | 36.7% | -0.1496 | 0.59 | -5.8 |
| HIGH_VOLATILITY_REVERSAL | 154 | 55.2% | +0.0679 | 1.29 | -3.8 |
| HIGH_VOLATILITY_TREND | 17 | 41.2% | -0.0128 | 0.95 | -1.9 |
| RANGE | 1,269 | 51.1% | +0.0150 | 1.09 | -11.7 |
| STRONG_BEAR_TREND | 16 | 25.0% | -0.2751 | 0.28 | -5.1 |
| STRONG_BULL_TREND | 17 | 47.1% | +0.0183 | 1.14 | -1.1 |
| UNCERTAIN | 186 | 47.3% | -0.0050 | 0.98 | -8.6 |
| WEAK_BEAR_TREND | 566 | 45.2% | -0.0020 | 0.99 | -15.3 |
| WEAK_BULL_TREND | 498 | 52.8% | -0.0029 | 0.99 | -10.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 404 | 52.7% | +0.0173 | 1.13 | -6.3 |
| FINAL_30 | 8 | 87.5% | +0.2113 | 8.64 | -0.2 |
| MIDDAY | 629 | 51.8% | -0.0029 | 0.98 | -17.3 |
| MIDMORNING | 823 | 49.2% | +0.0155 | 1.09 | -10.0 |
| MORNING | 1,076 | 48.5% | +0.0012 | 1.01 | -12.3 |
| OPEN | 848 | 48.8% | +0.0032 | 1.02 | -16.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,992 | 53.9% | +0.0127 | 1.08 | -13.8 |
| SHORT | 1,796 | 45.3% | -0.0010 | 1.00 | -16.1 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,057 | 53.7% | +0.0468 | 1.42 | -5.0 |
| stop | 486 | 0.0% | -0.7500 | 0.00 | -364.5 |
| target | 245 | 100.0% | +1.0000 | inf | 0.0 |

### S15 Momentum exhaustion | 1.0atr ext


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| HIGH_VOLATILITY_REVERSAL | 19 | 52.6% | +0.0690 | 1.51 | -0.9 |
| HIGH_VOLATILITY_TREND | 4 | 75.0% | +0.2500 | 3.00 | -0.5 |
| RANGE | 5 | 40.0% | -0.1120 | 0.47 | -0.8 |
| WEAK_BEAR_TREND | 4 | 75.0% | +0.2913 | 4.48 | -0.3 |
| WEAK_BULL_TREND | 2 | 100.0% | +0.2742 | inf | 0.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 27 | 59.3% | +0.1049 | 1.83 | -1.3 |
| FINAL_30 | 1 | 100.0% | +0.2402 | inf | 0.0 |
| MIDDAY | 5 | 40.0% | -0.0213 | 0.90 | -0.7 |
| MIDMORNING | 1 | 100.0% | +0.5000 | inf | 0.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 27 | 59.3% | +0.1102 | 1.81 | -1.3 |
| SHORT | 7 | 57.1% | +0.0701 | 1.62 | -0.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 5 | 0.0% | -0.5000 | 0.00 | -2.5 |
| target | 12 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 17 | 47.1% | -0.0020 | 0.98 | -1.2 |

### S16 Confluence | 2+ levels


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 5 | 20.0% | -0.4223 | 0.13 | -2.4 |
| EXPANSION | 71 | 62.0% | +0.1621 | 2.25 | -3.0 |
| HIGH_VOLATILITY_REVERSAL | 85 | 55.3% | +0.0529 | 1.28 | -2.9 |
| HIGH_VOLATILITY_TREND | 3 | 100.0% | +1.0000 | inf | 0.0 |
| RANGE | 98 | 41.8% | -0.0606 | 0.71 | -8.4 |
| STRONG_BEAR_TREND | 7 | 42.9% | -0.1279 | 0.35 | -1.1 |
| STRONG_BULL_TREND | 2 | 100.0% | +0.0824 | inf | 0.0 |
| UNCERTAIN | 3,305 | 49.8% | +0.0090 | 1.04 | -20.8 |
| WEAK_BEAR_TREND | 46 | 56.5% | +0.1572 | 1.73 | -4.0 |
| WEAK_BULL_TREND | 33 | 51.5% | -0.0464 | 0.77 | -3.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 143 | 51.7% | +0.0151 | 1.11 | -3.3 |
| FINAL_30 | 3 | 33.3% | +0.2271 | 14.60 | -0.1 |
| MIDDAY | 102 | 56.9% | +0.0574 | 1.31 | -2.9 |
| MIDMORNING | 62 | 46.8% | +0.0215 | 1.09 | -5.5 |
| MORNING | 20 | 70.0% | +0.3462 | 2.64 | -2.0 |
| OPEN | 3,325 | 49.7% | +0.0086 | 1.04 | -21.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,895 | 53.9% | +0.0222 | 1.11 | -14.4 |
| SHORT | 1,760 | 45.9% | +0.0020 | 1.01 | -19.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,760 | 54.9% | +0.0607 | 1.54 | -7.9 |
| stop | 581 | 0.0% | -0.7500 | 0.00 | -435.8 |
| target | 314 | 100.0% | +1.0000 | inf | 0.0 |

### S16 Confluence | 3+ levels


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 52 | 50.0% | -0.0047 | 0.97 | -3.5 |
| EXPANSION | 63 | 55.6% | +0.0211 | 1.16 | -2.4 |
| HIGH_VOLATILITY_REVERSAL | 76 | 65.8% | +0.1084 | 1.84 | -2.0 |
| HIGH_VOLATILITY_TREND | 2 | 50.0% | +0.0897 | 1.56 | -0.3 |
| RANGE | 601 | 50.4% | +0.0055 | 1.03 | -11.3 |
| STRONG_BEAR_TREND | 6 | 50.0% | -0.0334 | 0.78 | -0.5 |
| STRONG_BULL_TREND | 9 | 22.2% | -0.2306 | 0.10 | -2.1 |
| UNCERTAIN | 2,953 | 49.5% | -0.0038 | 0.98 | -35.9 |
| WEAK_BEAR_TREND | 167 | 55.1% | +0.0325 | 1.18 | -3.7 |
| WEAK_BULL_TREND | 132 | 53.0% | +0.0558 | 1.40 | -1.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 365 | 51.8% | +0.0259 | 1.22 | -4.8 |
| FINAL_30 | 8 | 12.5% | -0.1723 | 0.15 | -1.4 |
| MIDDAY | 287 | 53.7% | +0.0214 | 1.14 | -5.6 |
| MIDMORNING | 203 | 54.7% | +0.0165 | 1.09 | -6.3 |
| MORNING | 127 | 54.3% | +0.0407 | 1.22 | -5.4 |
| OPEN | 3,071 | 49.5% | -0.0035 | 0.98 | -39.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,106 | 52.1% | +0.0061 | 1.03 | -22.5 |
| SHORT | 1,955 | 48.5% | -0.0004 | 1.00 | -24.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,739 | 50.5% | +0.0040 | 1.05 | -5.8 |
| stop | 1,156 | 0.0% | -0.5000 | 0.00 | -578.0 |
| target | 1,166 | 100.0% | +0.5000 | inf | 0.0 |

### S16 Confluence | 4+ levels


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 175 | 55.4% | +0.0496 | 1.32 | -4.7 |
| EXPANSION | 9 | 55.6% | +0.1341 | 2.57 | -0.6 |
| HIGH_VOLATILITY_REVERSAL | 8 | 50.0% | +0.0521 | 1.18 | -2.1 |
| RANGE | 111 | 48.6% | +0.0467 | 1.32 | -3.6 |
| STRONG_BEAR_TREND | 2 | 50.0% | -0.0642 | 0.52 | -0.3 |
| UNCERTAIN | 1,846 | 49.8% | +0.0042 | 1.02 | -20.8 |
| WEAK_BEAR_TREND | 44 | 54.5% | +0.0574 | 1.31 | -2.5 |
| WEAK_BULL_TREND | 40 | 37.5% | -0.0932 | 0.60 | -5.3 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 30 | 50.0% | +0.0467 | 1.48 | -1.0 |
| MIDDAY | 37 | 51.4% | +0.0599 | 1.40 | -1.8 |
| MIDMORNING | 61 | 50.8% | -0.0069 | 0.95 | -2.0 |
| MORNING | 121 | 48.8% | +0.0226 | 1.13 | -4.6 |
| OPEN | 1,986 | 50.2% | +0.0081 | 1.04 | -20.8 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,143 | 54.4% | +0.0169 | 1.09 | -10.5 |
| SHORT | 1,092 | 45.6% | +0.0024 | 1.01 | -20.0 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,073 | 52.0% | +0.0381 | 1.27 | -9.4 |
| stop | 120 | 0.0% | -1.0000 | 0.00 | -120.0 |
| target | 42 | 100.0% | +1.5000 | inf | 0.0 |

### S17 Expected-move | <100% used


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 9 | 55.6% | -0.0851 | 0.58 | -1.2 |
| RANGE | 1 | 100.0% | +0.0951 | inf | 0.0 |
| UNCERTAIN | 3,320 | 50.5% | +0.0152 | 1.07 | -22.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDMORNING | 1 | 100.0% | +0.3973 | inf | 0.0 |
| MORNING | 1 | 100.0% | +0.0764 | inf | 0.0 |
| OPEN | 3,328 | 50.5% | +0.0148 | 1.07 | -23.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,685 | 54.7% | +0.0203 | 1.10 | -12.1 |
| SHORT | 1,645 | 46.1% | +0.0094 | 1.04 | -16.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,033 | 54.5% | +0.0856 | 1.60 | -9.8 |
| stop | 268 | 0.0% | -1.0000 | 0.00 | -268.0 |
| target | 29 | 100.0% | +2.0000 | inf | 0.0 |

### S17 Expected-move | <125% used


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 9 | 55.6% | -0.0851 | 0.58 | -1.2 |
| EXPANSION | 28 | 50.0% | +0.1487 | 1.75 | -3.1 |
| HIGH_VOLATILITY_REVERSAL | 26 | 42.3% | -0.0524 | 0.78 | -2.5 |
| HIGH_VOLATILITY_TREND | 1 | 0.0% | -0.2185 | 0.00 | -0.2 |
| RANGE | 43 | 41.9% | -0.0813 | 0.65 | -4.8 |
| STRONG_BEAR_TREND | 6 | 50.0% | -0.0957 | 0.45 | -1.0 |
| STRONG_BULL_TREND | 9 | 55.6% | +0.0626 | 2.11 | -0.5 |
| UNCERTAIN | 3,322 | 50.5% | +0.0157 | 1.07 | -22.8 |
| WEAK_BEAR_TREND | 26 | 50.0% | -0.0062 | 0.98 | -4.0 |
| WEAK_BULL_TREND | 12 | 58.3% | +0.0334 | 1.24 | -1.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 53 | 41.5% | +0.0120 | 1.08 | -3.9 |
| FINAL_30 | 1 | 0.0% | -0.0068 | 0.00 | -0.0 |
| MIDDAY | 59 | 52.5% | -0.0157 | 0.92 | -5.4 |
| MIDMORNING | 26 | 50.0% | +0.0153 | 1.05 | -4.7 |
| MORNING | 9 | 44.4% | -0.0749 | 0.83 | -3.0 |
| OPEN | 3,334 | 50.4% | +0.0154 | 1.07 | -22.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,741 | 54.7% | +0.0225 | 1.11 | -13.1 |
| SHORT | 1,741 | 45.9% | +0.0066 | 1.03 | -19.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,169 | 54.2% | +0.0835 | 1.58 | -10.3 |
| stop | 280 | 0.0% | -1.0000 | 0.00 | -280.0 |
| target | 33 | 100.0% | +2.0000 | inf | 0.0 |

### S17 Expected-move | <50% used


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 9 | 55.6% | -0.0851 | 0.58 | -1.2 |
| RANGE | 1 | 100.0% | +0.0951 | inf | 0.0 |
| UNCERTAIN | 3,290 | 50.5% | +0.0164 | 1.08 | -20.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDMORNING | 1 | 100.0% | +0.3973 | inf | 0.0 |
| MORNING | 1 | 100.0% | +0.0764 | inf | 0.0 |
| OPEN | 3,298 | 50.5% | +0.0160 | 1.08 | -21.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,663 | 54.7% | +0.0210 | 1.10 | -9.1 |
| SHORT | 1,637 | 46.2% | +0.0113 | 1.05 | -16.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,014 | 54.3% | +0.0837 | 1.59 | -9.8 |
| stop | 257 | 0.0% | -1.0000 | 0.00 | -257.0 |
| target | 29 | 100.0% | +2.0000 | inf | 0.0 |

### S17 Expected-move | <75% used


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 9 | 55.6% | -0.0851 | 0.58 | -1.2 |
| RANGE | 1 | 100.0% | +0.0951 | inf | 0.0 |
| UNCERTAIN | 3,317 | 50.5% | +0.0158 | 1.08 | -21.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDMORNING | 1 | 100.0% | +0.3973 | inf | 0.0 |
| MORNING | 1 | 100.0% | +0.0764 | inf | 0.0 |
| OPEN | 3,325 | 50.5% | +0.0154 | 1.07 | -22.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,683 | 54.7% | +0.0209 | 1.10 | -11.1 |
| SHORT | 1,644 | 46.2% | +0.0100 | 1.05 | -16.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,032 | 54.5% | +0.0857 | 1.60 | -9.8 |
| stop | 266 | 0.0% | -1.0000 | 0.00 | -266.0 |
| target | 29 | 100.0% | +2.0000 | inf | 0.0 |

### S18 Time-of-day | AFTERNOON


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,267 | 49.1% | -0.0006 | 0.97 | -1.9 |
| EXPANSION | 1,078 | 47.5% | +0.0011 | 1.02 | -3.7 |
| HIGH_VOLATILITY_REVERSAL | 1,827 | 47.9% | -0.0048 | 0.93 | -11.6 |
| HIGH_VOLATILITY_TREND | 85 | 54.1% | -0.0114 | 0.85 | -3.0 |
| RANGE | 17,465 | 47.4% | -0.0022 | 0.94 | -41.1 |
| STRONG_BEAR_TREND | 174 | 51.7% | +0.0122 | 1.29 | -1.3 |
| STRONG_BULL_TREND | 412 | 45.6% | -0.0010 | 0.97 | -1.7 |
| WEAK_BEAR_TREND | 728 | 48.8% | +0.0037 | 1.09 | -2.3 |
| WEAK_BULL_TREND | 1,003 | 47.2% | -0.0044 | 0.88 | -5.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 23,788 | 47.5% | -0.0022 | 0.95 | -54.1 |
| FINAL_30 | 251 | 55.8% | +0.0173 | 1.50 | -0.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 11,673 | 49.2% | -0.0014 | 0.96 | -19.5 |
| SHORT | 12,366 | 46.0% | -0.0025 | 0.94 | -35.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 109 | 0.0% | -0.5000 | 0.00 | -54.5 |
| stop_and_target_same_bar | 2 | 0.0% | -0.5000 | 0.00 | -1.0 |
| target | 124 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 23,804 | 47.5% | -0.0023 | 0.94 | -56.2 |

### S18 Time-of-day | FINAL_30


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 51 | 62.7% | +0.0337 | 2.29 | -0.4 |
| EXPANSION | 84 | 51.2% | +0.0236 | 1.31 | -1.3 |
| HIGH_VOLATILITY_REVERSAL | 156 | 49.4% | +0.0233 | 1.21 | -2.4 |
| HIGH_VOLATILITY_TREND | 4 | 25.0% | -0.1594 | 0.06 | -0.6 |
| RANGE | 1,151 | 51.5% | +0.0086 | 1.14 | -5.1 |
| STRONG_BEAR_TREND | 9 | 44.4% | -0.0492 | 0.56 | -0.9 |
| STRONG_BULL_TREND | 21 | 57.1% | +0.0138 | 1.25 | -0.7 |
| WEAK_BEAR_TREND | 65 | 40.0% | -0.0204 | 0.79 | -3.1 |
| WEAK_BULL_TREND | 55 | 41.8% | -0.0242 | 0.65 | -2.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| FINAL_30 | 1,596 | 50.8% | +0.0086 | 1.13 | -5.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 770 | 51.6% | +0.0079 | 1.12 | -3.9 |
| SHORT | 826 | 50.1% | +0.0093 | 1.13 | -2.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,593 | 50.7% | +0.0058 | 1.09 | -6.2 |
| target | 3 | 100.0% | +1.5000 | inf | 0.0 |

### S18 Time-of-day | MIDDAY


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 481 | 51.1% | +0.0058 | 1.05 | -5.7 |
| EXPANSION | 49 | 44.9% | -0.0753 | 0.75 | -8.5 |
| HIGH_VOLATILITY_REVERSAL | 97 | 48.5% | +0.0831 | 1.28 | -4.1 |
| HIGH_VOLATILITY_TREND | 19 | 47.4% | -0.0207 | 0.93 | -4.8 |
| RANGE | 2,063 | 50.7% | +0.0064 | 1.04 | -17.2 |
| STRONG_BEAR_TREND | 78 | 51.3% | +0.0089 | 1.05 | -5.8 |
| STRONG_BULL_TREND | 141 | 52.5% | -0.0173 | 0.87 | -5.6 |
| WEAK_BEAR_TREND | 205 | 56.6% | +0.0829 | 1.53 | -3.8 |
| WEAK_BULL_TREND | 228 | 50.0% | +0.0252 | 1.16 | -4.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 1 | 0.0% | -1.0000 | 0.00 | -1.0 |
| MIDDAY | 3,360 | 51.0% | +0.0125 | 1.08 | -14.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,727 | 55.4% | +0.0225 | 1.15 | -10.3 |
| SHORT | 1,634 | 46.3% | +0.0013 | 1.01 | -16.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,209 | 52.9% | +0.0461 | 1.36 | -9.0 |
| stop | 137 | 0.0% | -1.0000 | 0.00 | -137.0 |
| target | 15 | 100.0% | +2.0000 | inf | 0.0 |

### S18 Time-of-day | MIDMORNING


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 2,950 | 50.2% | +0.0021 | 1.07 | -3.0 |
| EXPANSION | 364 | 46.7% | -0.0097 | 0.87 | -7.0 |
| HIGH_VOLATILITY_REVERSAL | 173 | 52.0% | -0.0019 | 0.98 | -2.7 |
| RANGE | 5,866 | 48.4% | -0.0031 | 0.93 | -22.8 |
| WEAK_BEAR_TREND | 1,696 | 49.5% | -0.0010 | 0.98 | -6.7 |
| WEAK_BULL_TREND | 2,109 | 49.5% | -0.0003 | 0.99 | -5.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDDAY | 109 | 53.2% | +0.0044 | 1.13 | -1.0 |
| MIDMORNING | 13,049 | 49.1% | -0.0014 | 0.97 | -27.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 6,433 | 51.1% | -0.0025 | 0.94 | -21.1 |
| SHORT | 6,725 | 47.2% | -0.0004 | 0.99 | -12.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 7 | 0.0% | -0.7500 | 0.00 | -5.2 |
| target | 7 | 100.0% | +1.0000 | inf | 0.0 |
| time_stop | 13,144 | 49.1% | -0.0015 | 0.97 | -27.7 |

### S18 Time-of-day | MORNING


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 3,052 | 47.3% | -0.0057 | 0.87 | -20.0 |
| EXPANSION | 43 | 37.2% | -0.0551 | 0.53 | -2.6 |
| HIGH_VOLATILITY_REVERSAL | 6 | 50.0% | -0.0645 | 0.42 | -0.5 |
| RANGE | 1,072 | 47.7% | -0.0108 | 0.83 | -15.4 |
| WEAK_BEAR_TREND | 1,221 | 46.7% | -0.0148 | 0.79 | -18.3 |
| WEAK_BULL_TREND | 1,269 | 46.7% | -0.0077 | 0.87 | -11.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDMORNING | 3 | 66.7% | +0.0322 | 2.48 | -0.1 |
| MORNING | 6,660 | 47.0% | -0.0090 | 0.84 | -62.9 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 3,364 | 48.2% | -0.0105 | 0.81 | -35.7 |
| SHORT | 3,299 | 45.9% | -0.0074 | 0.87 | -28.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 2 | 0.0% | -1.0000 | 0.00 | -2.0 |
| time_stop | 6,661 | 47.1% | -0.0087 | 0.84 | -60.8 |

### S18 Time-of-day | OPEN


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 4 | 25.0% | -0.5422 | 0.04 | -2.2 |
| EXPANSION | 4 | 25.0% | -0.3125 | 0.44 | -1.5 |
| RANGE | 3 | 33.3% | -0.4683 | 0.06 | -1.5 |
| UNCERTAIN | 3,327 | 50.1% | +0.0150 | 1.07 | -21.3 |
| WEAK_BEAR_TREND | 5 | 40.0% | -0.1974 | 0.56 | -2.3 |
| WEAK_BULL_TREND | 2 | 50.0% | -0.3527 | 0.06 | -0.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MORNING | 1 | 0.0% | -0.7500 | 0.00 | -0.8 |
| OPEN | 3,344 | 50.1% | +0.0132 | 1.06 | -22.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,633 | 53.9% | +0.0212 | 1.11 | -11.3 |
| SHORT | 1,712 | 46.3% | +0.0052 | 1.02 | -20.3 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,515 | 54.8% | +0.0596 | 1.52 | -8.8 |
| stop | 535 | 0.0% | -0.7500 | 0.00 | -401.3 |
| target | 295 | 100.0% | +1.0000 | inf | 0.0 |

### S19 MTF breakout | 2/4 agree


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,301 | 48.8% | -0.0057 | 0.97 | -14.3 |
| EXPANSION | 94 | 41.5% | -0.0739 | 0.75 | -11.3 |
| HIGH_VOLATILITY_REVERSAL | 210 | 49.0% | +0.0140 | 1.05 | -8.5 |
| HIGH_VOLATILITY_TREND | 20 | 40.0% | -0.0336 | 0.87 | -3.1 |
| RANGE | 490 | 50.4% | +0.0146 | 1.08 | -8.4 |
| STRONG_BEAR_TREND | 18 | 44.4% | -0.0370 | 0.84 | -1.5 |
| STRONG_BULL_TREND | 22 | 59.1% | +0.0369 | 1.36 | -0.9 |
| UNCERTAIN | 1,145 | 51.3% | +0.0297 | 1.15 | -10.9 |
| WEAK_BEAR_TREND | 460 | 46.7% | -0.0166 | 0.93 | -17.5 |
| WEAK_BULL_TREND | 386 | 50.8% | -0.0411 | 0.82 | -19.9 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 356 | 51.7% | +0.0088 | 1.05 | -11.7 |
| FINAL_30 | 6 | 33.3% | -0.0028 | 0.97 | -0.5 |
| MIDDAY | 295 | 50.5% | +0.0227 | 1.11 | -5.8 |
| MIDMORNING | 124 | 43.5% | -0.0401 | 0.87 | -7.6 |
| MORNING | 1,255 | 47.7% | -0.0120 | 0.94 | -31.9 |
| OPEN | 2,110 | 50.4% | +0.0076 | 1.04 | -17.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,251 | 53.3% | +0.0120 | 1.07 | -12.6 |
| SHORT | 1,895 | 45.0% | -0.0112 | 0.95 | -34.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,155 | 54.9% | +0.0599 | 1.55 | -6.2 |
| stop | 670 | 0.0% | -0.7500 | 0.00 | -502.5 |
| stop_and_target_same_bar | 1 | 0.0% | -0.7500 | 0.00 | -0.8 |
| target | 320 | 100.0% | +1.0000 | inf | 0.0 |

### S19 MTF breakout | 3/4 agree


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,258 | 51.6% | +0.0180 | 1.12 | -7.8 |
| HIGH_VOLATILITY_REVERSAL | 96 | 49.0% | +0.0928 | 1.36 | -4.2 |
| HIGH_VOLATILITY_TREND | 4 | 100.0% | +0.4565 | inf | 0.0 |
| RANGE | 1,017 | 49.5% | +0.0026 | 1.01 | -14.4 |
| STRONG_BEAR_TREND | 6 | 16.7% | -0.0192 | 0.87 | -0.7 |
| STRONG_BULL_TREND | 7 | 28.6% | -0.2375 | 0.12 | -1.9 |
| WEAK_BEAR_TREND | 555 | 46.8% | +0.0125 | 1.05 | -17.2 |
| WEAK_BULL_TREND | 553 | 54.2% | +0.0020 | 1.01 | -11.6 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 87 | 44.8% | +0.0395 | 1.22 | -3.0 |
| FINAL_30 | 4 | 75.0% | +0.1555 | 2.39 | -0.4 |
| MIDDAY | 689 | 49.8% | +0.0168 | 1.10 | -10.2 |
| MIDMORNING | 902 | 50.3% | +0.0146 | 1.09 | -11.5 |
| MORNING | 1,814 | 51.1% | +0.0074 | 1.04 | -26.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,092 | 53.7% | +0.0149 | 1.09 | -11.4 |
| SHORT | 1,404 | 45.7% | +0.0079 | 1.04 | -17.1 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,272 | 53.3% | +0.0603 | 1.44 | -6.6 |
| stop | 201 | 0.0% | -1.0000 | 0.00 | -201.0 |
| target | 23 | 100.0% | +2.0000 | inf | 0.0 |

### S19 MTF breakout | 4/4 agree


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 306 | 55.2% | +0.0158 | 1.18 | -3.0 |
| HIGH_VOLATILITY_REVERSAL | 94 | 45.7% | +0.0436 | 1.15 | -4.5 |
| HIGH_VOLATILITY_TREND | 38 | 63.2% | +0.1255 | 1.59 | -2.6 |
| RANGE | 1,505 | 51.7% | +0.0163 | 1.12 | -10.0 |
| STRONG_BEAR_TREND | 150 | 52.7% | +0.0116 | 1.07 | -4.6 |
| STRONG_BULL_TREND | 268 | 58.2% | +0.0419 | 1.42 | -3.6 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 543 | 52.5% | +0.0216 | 1.21 | -2.8 |
| FINAL_30 | 51 | 52.9% | +0.0166 | 1.32 | -1.0 |
| MIDDAY | 1,767 | 53.0% | +0.0219 | 1.15 | -12.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,489 | 55.3% | +0.0234 | 1.22 | -8.2 |
| SHORT | 872 | 48.7% | +0.0189 | 1.10 | -6.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,281 | 54.4% | +0.0470 | 1.44 | -6.9 |
| stop | 72 | 0.0% | -1.0000 | 0.00 | -72.0 |
| target | 8 | 100.0% | +2.0000 | inf | 0.0 |

### S2 ORB immediate | or15


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 674 | 48.4% | -0.0095 | 0.95 | -15.8 |
| EXPANSION | 8 | 62.5% | +0.1250 | 1.67 | -0.5 |
| HIGH_VOLATILITY_REVERSAL | 2 | 50.0% | +0.0000 | 1.00 | -0.5 |
| RANGE | 447 | 56.6% | +0.0467 | 1.24 | -5.0 |
| WEAK_BEAR_TREND | 223 | 47.5% | -0.0367 | 0.85 | -11.6 |
| WEAK_BULL_TREND | 152 | 48.0% | -0.0370 | 0.84 | -7.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 2 | 50.0% | +0.0447 | 5.84 | -0.0 |
| MIDDAY | 11 | 54.5% | +0.0599 | 1.45 | -0.7 |
| MIDMORNING | 41 | 36.6% | -0.0858 | 0.63 | -4.0 |
| MORNING | 326 | 48.2% | -0.0194 | 0.91 | -8.0 |
| OPEN | 1,126 | 52.0% | +0.0096 | 1.05 | -10.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 731 | 52.4% | -0.0006 | 1.00 | -11.6 |
| SHORT | 775 | 49.2% | +0.0027 | 1.01 | -9.0 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 450 | 54.2% | +0.0215 | 1.24 | -3.2 |
| stop | 536 | 0.0% | -0.5000 | 0.00 | -268.0 |
| target | 520 | 100.0% | +0.5000 | inf | 0.0 |

### S2 ORB immediate | or30


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 323 | 45.5% | -0.0122 | 0.93 | -12.2 |
| EXPANSION | 16 | 37.5% | -0.1430 | 0.70 | -5.6 |
| HIGH_VOLATILITY_REVERSAL | 6 | 83.3% | +0.4119 | 8.21 | -0.3 |
| RANGE | 450 | 47.3% | +0.0097 | 1.04 | -11.6 |
| WEAK_BEAR_TREND | 350 | 47.1% | +0.0097 | 1.04 | -14.3 |
| WEAK_BULL_TREND | 327 | 52.0% | -0.0001 | 1.00 | -8.4 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 13 | 38.5% | -0.0906 | 0.44 | -1.7 |
| MIDDAY | 40 | 45.0% | -0.0085 | 0.96 | -2.7 |
| MIDMORNING | 229 | 47.6% | +0.0149 | 1.06 | -10.0 |
| MORNING | 1,190 | 48.2% | +0.0017 | 1.01 | -15.8 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 758 | 49.5% | -0.0209 | 0.91 | -21.3 |
| SHORT | 714 | 46.4% | +0.0278 | 1.11 | -13.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,310 | 52.7% | +0.0901 | 1.60 | -5.6 |
| stop | 146 | 0.0% | -1.0000 | 0.00 | -146.0 |
| target | 16 | 100.0% | +2.0000 | inf | 0.0 |

### S2 ORB immediate | or5


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 98 | 52.0% | +0.0067 | 1.04 | -3.8 |
| EXPANSION | 1 | 100.0% | +1.0000 | inf | 0.0 |
| RANGE | 27 | 40.7% | -0.0718 | 0.76 | -4.2 |
| UNCERTAIN | 1,420 | 50.7% | +0.0287 | 1.13 | -11.9 |
| WEAK_BEAR_TREND | 10 | 20.0% | -0.2128 | 0.39 | -2.8 |
| WEAK_BULL_TREND | 9 | 66.7% | +0.1139 | 1.69 | -0.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| MIDMORNING | 2 | 0.0% | -0.1754 | 0.00 | -0.4 |
| MORNING | 28 | 42.9% | -0.0562 | 0.77 | -1.9 |
| OPEN | 1,535 | 50.7% | +0.0269 | 1.12 | -11.9 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 798 | 53.6% | +0.0247 | 1.11 | -7.8 |
| SHORT | 767 | 47.3% | +0.0256 | 1.11 | -9.9 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,083 | 56.2% | +0.0760 | 1.66 | -3.5 |
| stop | 300 | 0.0% | -0.7500 | 0.00 | -225.0 |
| target | 182 | 100.0% | +1.0000 | inf | 0.0 |

### S21 Gap continuation | gap>=0.25%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 270 | 52.6% | -0.0058 | 0.97 | -9.9 |
| EXPANSION | 33 | 48.5% | -0.1031 | 0.61 | -5.8 |
| HIGH_VOLATILITY_REVERSAL | 47 | 68.1% | +0.2922 | 2.56 | -2.1 |
| HIGH_VOLATILITY_TREND | 5 | 60.0% | +0.0387 | 1.25 | -0.6 |
| RANGE | 68 | 45.6% | +0.0204 | 1.10 | -4.0 |
| STRONG_BEAR_TREND | 5 | 80.0% | +0.2071 | 53.81 | -0.0 |
| STRONG_BULL_TREND | 1 | 0.0% | -0.1413 | 0.00 | -0.1 |
| UNCERTAIN | 1,349 | 52.9% | +0.0288 | 1.13 | -14.2 |
| WEAK_BEAR_TREND | 95 | 56.8% | +0.1167 | 1.62 | -4.0 |
| WEAK_BULL_TREND | 83 | 47.0% | +0.0053 | 1.03 | -5.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 68 | 61.8% | +0.1735 | 2.25 | -2.6 |
| FINAL_30 | 2 | 50.0% | +0.0369 | 1.22 | -0.3 |
| MIDDAY | 45 | 55.6% | +0.1205 | 1.89 | -1.1 |
| MIDMORNING | 65 | 46.2% | -0.0615 | 0.73 | -6.0 |
| MORNING | 153 | 48.4% | +0.0284 | 1.15 | -8.4 |
| OPEN | 1,623 | 53.1% | +0.0271 | 1.13 | -10.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,090 | 57.2% | +0.0395 | 1.21 | -6.2 |
| SHORT | 866 | 47.5% | +0.0214 | 1.09 | -11.3 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,739 | 56.7% | +0.0912 | 1.67 | -5.1 |
| stop | 169 | 0.0% | -1.0000 | 0.00 | -169.0 |
| target | 48 | 100.0% | +1.5000 | inf | 0.0 |

### S21 Gap continuation | gap>=0.5%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 147 | 58.5% | +0.0195 | 1.10 | -6.8 |
| EXPANSION | 15 | 40.0% | -0.2842 | 0.33 | -4.5 |
| HIGH_VOLATILITY_REVERSAL | 22 | 59.1% | +0.1837 | 1.80 | -3.0 |
| HIGH_VOLATILITY_TREND | 1 | 0.0% | -0.3647 | 0.00 | -0.4 |
| RANGE | 41 | 51.2% | +0.0417 | 1.21 | -2.6 |
| STRONG_BEAR_TREND | 4 | 75.0% | +0.1921 | 40.20 | -0.0 |
| STRONG_BULL_TREND | 1 | 0.0% | -0.1413 | 0.00 | -0.1 |
| UNCERTAIN | 735 | 56.7% | +0.0628 | 1.30 | -7.0 |
| WEAK_BEAR_TREND | 57 | 61.4% | +0.1642 | 1.97 | -2.3 |
| WEAK_BULL_TREND | 35 | 57.1% | +0.1556 | 1.81 | -2.2 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 32 | 65.6% | +0.1858 | 2.53 | -3.0 |
| MIDDAY | 22 | 45.5% | -0.0150 | 0.92 | -1.6 |
| MIDMORNING | 37 | 54.1% | +0.0105 | 1.05 | -4.0 |
| MORNING | 81 | 54.3% | +0.0550 | 1.28 | -5.2 |
| OPEN | 886 | 57.1% | +0.0622 | 1.30 | -7.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 576 | 61.5% | +0.0729 | 1.42 | -6.0 |
| SHORT | 482 | 51.2% | +0.0489 | 1.20 | -8.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 948 | 62.3% | +0.1535 | 2.23 | -3.6 |
| stop | 100 | 0.0% | -1.0000 | 0.00 | -100.0 |
| target | 10 | 100.0% | +2.0000 | inf | 0.0 |

### S21 Gap continuation | gap>=1.0%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 55 | 65.5% | +0.0291 | 1.15 | -2.6 |
| EXPANSION | 11 | 27.3% | -0.4077 | 0.26 | -4.7 |
| HIGH_VOLATILITY_REVERSAL | 14 | 64.3% | +0.1412 | 1.65 | -3.0 |
| HIGH_VOLATILITY_TREND | 1 | 0.0% | -0.3647 | 0.00 | -0.4 |
| RANGE | 17 | 47.1% | -0.0259 | 0.89 | -1.6 |
| STRONG_BEAR_TREND | 1 | 100.0% | +0.2043 | inf | 0.0 |
| UNCERTAIN | 256 | 59.0% | +0.0690 | 1.31 | -7.2 |
| WEAK_BEAR_TREND | 28 | 64.3% | +0.1891 | 2.15 | -2.3 |
| WEAK_BULL_TREND | 5 | 40.0% | -0.1629 | 0.61 | -2.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 18 | 72.2% | +0.2221 | 2.59 | -2.0 |
| MIDDAY | 9 | 33.3% | -0.0706 | 0.60 | -1.0 |
| MIDMORNING | 15 | 40.0% | -0.2610 | 0.41 | -4.1 |
| MORNING | 31 | 51.6% | -0.0237 | 0.90 | -4.5 |
| OPEN | 315 | 60.3% | +0.0696 | 1.32 | -7.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 190 | 63.7% | +0.0680 | 1.34 | -4.2 |
| SHORT | 198 | 54.0% | +0.0390 | 1.15 | -7.1 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 333 | 67.0% | +0.1821 | 2.60 | -3.4 |
| stop | 50 | 0.0% | -1.0000 | 0.00 | -50.0 |
| target | 5 | 100.0% | +2.0000 | inf | 0.0 |

### S22 Gap fade | gap>=0.25%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,639 | 48.4% | -0.0007 | 0.99 | -4.6 |
| EXPANSION | 402 | 47.8% | -0.0129 | 0.86 | -10.1 |
| HIGH_VOLATILITY_REVERSAL | 550 | 48.4% | -0.0076 | 0.93 | -7.2 |
| HIGH_VOLATILITY_TREND | 25 | 52.0% | +0.0158 | 1.16 | -1.5 |
| RANGE | 6,514 | 48.3% | +0.0033 | 1.06 | -11.8 |
| STRONG_BEAR_TREND | 95 | 47.4% | -0.0249 | 0.66 | -2.9 |
| STRONG_BULL_TREND | 109 | 48.6% | +0.0148 | 1.41 | -0.7 |
| UNCERTAIN | 1,487 | 49.0% | -0.0086 | 0.91 | -22.1 |
| WEAK_BEAR_TREND | 905 | 45.5% | +0.0024 | 1.03 | -4.0 |
| WEAK_BULL_TREND | 835 | 51.3% | +0.0097 | 1.17 | -5.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 3,701 | 47.8% | -0.0005 | 0.99 | -14.9 |
| FINAL_30 | 60 | 50.0% | +0.0262 | 1.50 | -0.7 |
| MIDDAY | 3,667 | 47.1% | +0.0018 | 1.04 | -6.4 |
| MIDMORNING | 2,126 | 50.0% | +0.0061 | 1.10 | -4.1 |
| MORNING | 1,291 | 50.4% | +0.0013 | 1.02 | -8.6 |
| OPEN | 1,716 | 48.8% | -0.0077 | 0.92 | -22.8 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 6,134 | 50.5% | +0.0011 | 1.02 | -9.1 |
| SHORT | 6,427 | 46.3% | +0.0002 | 1.00 | -13.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 31 | 45.2% | -0.0141 | 0.75 | -0.8 |
| stop | 226 | 0.0% | -0.5000 | 0.00 | -113.0 |
| target | 243 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 12,061 | 48.2% | -0.0000 | 1.00 | -18.7 |

### S22 Gap fade | gap>=0.5%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,587 | 48.8% | -0.0012 | 0.97 | -5.0 |
| EXPANSION | 334 | 54.2% | +0.0080 | 1.16 | -1.7 |
| HIGH_VOLATILITY_REVERSAL | 631 | 49.8% | -0.0009 | 0.99 | -3.9 |
| HIGH_VOLATILITY_TREND | 19 | 52.6% | +0.0199 | 1.28 | -0.9 |
| RANGE | 5,766 | 47.3% | -0.0012 | 0.97 | -8.6 |
| STRONG_BEAR_TREND | 90 | 52.2% | +0.0107 | 1.29 | -0.7 |
| STRONG_BULL_TREND | 71 | 42.3% | -0.0160 | 0.61 | -1.3 |
| UNCERTAIN | 824 | 49.9% | -0.0055 | 0.92 | -9.2 |
| WEAK_BEAR_TREND | 821 | 47.7% | -0.0008 | 0.98 | -3.5 |
| WEAK_BULL_TREND | 671 | 46.6% | -0.0041 | 0.92 | -3.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 3,238 | 48.2% | -0.0005 | 0.99 | -7.9 |
| FINAL_30 | 54 | 51.9% | +0.0000 | 1.00 | -0.8 |
| MIDDAY | 3,327 | 46.2% | -0.0016 | 0.96 | -8.4 |
| MIDMORNING | 1,841 | 48.7% | +0.0011 | 1.02 | -6.0 |
| MORNING | 989 | 47.9% | -0.0069 | 0.88 | -8.4 |
| OPEN | 1,365 | 51.6% | -0.0020 | 0.97 | -8.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 5,463 | 48.9% | -0.0019 | 0.96 | -11.8 |
| SHORT | 5,351 | 47.2% | -0.0008 | 0.98 | -11.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2 | 0.0% | -0.0742 | 0.00 | -0.1 |
| stop | 6 | 0.0% | -1.0000 | 0.00 | -6.0 |
| target | 1 | 100.0% | +2.0000 | inf | 0.0 |
| time_stop | 10,805 | 48.1% | -0.0010 | 0.98 | -15.2 |

### S22 Gap fade | gap>=1.0%


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 562 | 47.3% | -0.0076 | 0.81 | -4.8 |
| EXPANSION | 122 | 53.3% | +0.0096 | 1.13 | -2.2 |
| HIGH_VOLATILITY_REVERSAL | 358 | 48.9% | +0.0020 | 1.03 | -3.2 |
| HIGH_VOLATILITY_TREND | 15 | 53.3% | +0.0455 | 1.83 | -0.6 |
| RANGE | 2,015 | 48.1% | -0.0013 | 0.97 | -6.2 |
| STRONG_BEAR_TREND | 29 | 51.7% | -0.0092 | 0.78 | -0.5 |
| STRONG_BULL_TREND | 12 | 50.0% | -0.0389 | 0.46 | -0.7 |
| UNCERTAIN | 300 | 48.7% | -0.0052 | 0.92 | -3.3 |
| WEAK_BEAR_TREND | 270 | 48.5% | -0.0004 | 0.99 | -4.9 |
| WEAK_BULL_TREND | 195 | 42.6% | -0.0168 | 0.72 | -3.3 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 1,151 | 47.3% | -0.0043 | 0.92 | -7.8 |
| FINAL_30 | 13 | 46.2% | -0.0258 | 0.57 | -0.4 |
| MIDDAY | 1,196 | 48.4% | +0.0005 | 1.01 | -4.6 |
| MIDMORNING | 652 | 48.6% | +0.0016 | 1.03 | -2.2 |
| MORNING | 363 | 44.6% | -0.0164 | 0.75 | -7.9 |
| OPEN | 503 | 51.1% | -0.0011 | 0.98 | -3.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,124 | 49.0% | -0.0030 | 0.94 | -8.9 |
| SHORT | 1,754 | 47.0% | -0.0021 | 0.95 | -8.9 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| stop | 7 | 0.0% | -0.7500 | 0.00 | -5.2 |
| target | 4 | 100.0% | +1.0000 | inf | 0.0 |
| time_stop | 3,867 | 48.1% | -0.0023 | 0.95 | -14.1 |

### S3 VWAP pullback | zoneA vwap


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 736 | 51.0% | -0.0040 | 0.98 | -10.7 |
| EXPANSION | 10 | 50.0% | -0.0227 | 0.92 | -1.5 |
| HIGH_VOLATILITY_REVERSAL | 43 | 58.1% | +0.1188 | 1.78 | -1.4 |
| HIGH_VOLATILITY_TREND | 1 | 0.0% | -0.3509 | 0.00 | -0.4 |
| RANGE | 721 | 51.6% | -0.0018 | 0.99 | -18.0 |
| STRONG_BEAR_TREND | 5 | 100.0% | +0.3023 | inf | 0.0 |
| STRONG_BULL_TREND | 2 | 50.0% | +0.0753 | 4.31 | -0.0 |
| UNCERTAIN | 567 | 53.4% | +0.0341 | 1.19 | -5.7 |
| WEAK_BEAR_TREND | 163 | 46.6% | -0.0091 | 0.96 | -6.6 |
| WEAK_BULL_TREND | 126 | 46.8% | -0.0330 | 0.86 | -12.4 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 204 | 52.5% | -0.0024 | 0.98 | -4.9 |
| FINAL_30 | 5 | 20.0% | -0.0172 | 0.74 | -0.2 |
| MIDDAY | 270 | 54.4% | +0.0270 | 1.22 | -4.8 |
| MIDMORNING | 472 | 53.0% | +0.0175 | 1.10 | -8.7 |
| MORNING | 613 | 46.5% | -0.0468 | 0.78 | -29.3 |
| OPEN | 810 | 53.2% | +0.0363 | 1.19 | -5.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,320 | 54.8% | +0.0115 | 1.07 | -14.8 |
| SHORT | 1,054 | 47.2% | +0.0005 | 1.00 | -12.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,955 | 55.8% | +0.0524 | 1.50 | -5.4 |
| stop | 289 | 0.0% | -0.7500 | 0.00 | -216.8 |
| target | 130 | 100.0% | +1.0000 | inf | 0.0 |

### S3 VWAP pullback | zoneB 0.25atr


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 989 | 49.4% | -0.0002 | 1.00 | -15.4 |
| EXPANSION | 14 | 57.1% | -0.0336 | 0.89 | -3.4 |
| HIGH_VOLATILITY_REVERSAL | 34 | 52.9% | +0.0006 | 1.00 | -3.2 |
| RANGE | 175 | 55.4% | +0.0963 | 1.45 | -3.4 |
| STRONG_BEAR_TREND | 1 | 100.0% | +0.4790 | inf | 0.0 |
| UNCERTAIN | 1,591 | 52.8% | +0.0314 | 1.16 | -13.5 |
| WEAK_BEAR_TREND | 311 | 44.7% | -0.0276 | 0.89 | -13.7 |
| WEAK_BULL_TREND | 277 | 51.3% | -0.0355 | 0.86 | -14.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 35 | 51.4% | -0.0596 | 0.73 | -3.0 |
| FINAL_30 | 1 | 0.0% | -0.4124 | 0.00 | -0.4 |
| MIDDAY | 25 | 64.0% | +0.1952 | 2.34 | -2.7 |
| MIDMORNING | 69 | 42.0% | -0.0671 | 0.69 | -4.9 |
| MORNING | 1,045 | 49.1% | +0.0058 | 1.03 | -21.8 |
| OPEN | 2,217 | 52.2% | +0.0200 | 1.10 | -13.7 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,949 | 54.5% | +0.0208 | 1.12 | -9.7 |
| SHORT | 1,443 | 46.6% | +0.0053 | 1.02 | -19.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,110 | 54.9% | +0.0801 | 1.58 | -6.1 |
| stop | 255 | 0.0% | -1.0000 | 0.00 | -255.0 |
| target | 27 | 100.0% | +2.0000 | inf | 0.0 |

### S3 VWAP pullback | zoneC 0.50atr


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 989 | 49.4% | -0.0002 | 1.00 | -15.4 |
| EXPANSION | 21 | 47.6% | -0.0170 | 0.95 | -2.8 |
| HIGH_VOLATILITY_REVERSAL | 53 | 50.9% | +0.0204 | 1.09 | -5.0 |
| RANGE | 212 | 54.2% | +0.0874 | 1.45 | -5.3 |
| STRONG_BEAR_TREND | 2 | 50.0% | -0.2605 | 0.48 | -1.0 |
| UNCERTAIN | 1,591 | 52.8% | +0.0314 | 1.16 | -13.5 |
| WEAK_BEAR_TREND | 330 | 45.2% | -0.0260 | 0.90 | -14.5 |
| WEAK_BULL_TREND | 291 | 51.5% | -0.0337 | 0.86 | -14.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 78 | 51.3% | +0.0372 | 1.27 | -4.3 |
| FINAL_30 | 2 | 50.0% | -0.1252 | 0.39 | -0.4 |
| MIDDAY | 53 | 52.8% | -0.0090 | 0.96 | -3.1 |
| MIDMORNING | 73 | 43.8% | -0.0037 | 0.98 | -4.3 |
| MORNING | 1,065 | 48.9% | +0.0026 | 1.01 | -25.2 |
| OPEN | 2,218 | 52.3% | +0.0204 | 1.10 | -13.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,991 | 54.6% | +0.0204 | 1.12 | -12.0 |
| SHORT | 1,498 | 46.3% | +0.0063 | 1.03 | -22.8 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 3,199 | 54.8% | +0.0810 | 1.58 | -6.2 |
| stop | 263 | 0.0% | -1.0000 | 0.00 | -263.0 |
| target | 27 | 100.0% | +2.0000 | inf | 0.0 |

### S4 VWAP reclaim | chop<=2


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 148 | 50.0% | +0.0385 | 1.25 | -3.5 |
| EXPANSION | 6 | 50.0% | +0.2803 | 2.08 | -1.5 |
| RANGE | 37 | 51.4% | +0.0299 | 1.13 | -2.5 |
| STRONG_BEAR_TREND | 3 | 33.3% | -0.1478 | 0.17 | -0.5 |
| UNCERTAIN | 1,861 | 49.7% | +0.0187 | 1.09 | -17.8 |
| WEAK_BEAR_TREND | 58 | 56.9% | +0.0957 | 1.54 | -1.7 |
| WEAK_BULL_TREND | 51 | 45.1% | -0.0264 | 0.89 | -5.6 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 7 | 42.9% | +0.1219 | 2.39 | -0.5 |
| MIDDAY | 13 | 30.8% | +0.0374 | 1.20 | -1.5 |
| MIDMORNING | 30 | 60.0% | +0.1524 | 2.14 | -1.5 |
| MORNING | 72 | 52.8% | +0.0431 | 1.24 | -7.5 |
| OPEN | 2,042 | 49.7% | +0.0186 | 1.09 | -19.9 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,067 | 53.8% | +0.0268 | 1.14 | -7.1 |
| SHORT | 1,097 | 45.9% | +0.0168 | 1.08 | -16.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,983 | 53.3% | +0.0832 | 1.59 | -6.0 |
| stop | 160 | 0.0% | -1.0000 | 0.00 | -160.0 |
| target | 21 | 100.0% | +2.0000 | inf | 0.0 |

### S4 VWAP reclaim | chop<=3


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 199 | 51.8% | +0.0624 | 1.40 | -3.3 |
| EXPANSION | 17 | 35.3% | -0.0981 | 0.74 | -3.2 |
| RANGE | 42 | 45.2% | -0.0567 | 0.78 | -3.1 |
| STRONG_BEAR_TREND | 3 | 33.3% | -0.1478 | 0.17 | -0.5 |
| UNCERTAIN | 2,367 | 48.3% | +0.0048 | 1.02 | -20.1 |
| WEAK_BEAR_TREND | 73 | 54.8% | +0.0826 | 1.50 | -2.4 |
| WEAK_BULL_TREND | 60 | 46.7% | -0.0374 | 0.83 | -5.3 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 14 | 42.9% | +0.0612 | 1.66 | -0.7 |
| MIDDAY | 18 | 33.3% | -0.0153 | 0.90 | -1.4 |
| MIDMORNING | 37 | 62.2% | +0.1595 | 2.11 | -1.9 |
| MORNING | 94 | 50.0% | +0.0015 | 1.01 | -10.2 |
| OPEN | 2,598 | 48.4% | +0.0064 | 1.03 | -21.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,387 | 51.8% | +0.0093 | 1.05 | -16.8 |
| SHORT | 1,374 | 45.3% | +0.0075 | 1.03 | -15.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,087 | 52.6% | +0.0504 | 1.43 | -6.4 |
| stop | 432 | 0.0% | -0.7500 | 0.00 | -324.0 |
| target | 242 | 100.0% | +1.0000 | inf | 0.0 |

### S4 VWAP reclaim | chop<=4


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 264 | 52.3% | +0.0556 | 1.36 | -3.5 |
| EXPANSION | 29 | 48.3% | +0.0327 | 1.12 | -2.6 |
| HIGH_VOLATILITY_TREND | 1 | 100.0% | +0.0697 | inf | 0.0 |
| RANGE | 52 | 42.3% | -0.0285 | 0.88 | -3.5 |
| STRONG_BEAR_TREND | 4 | 50.0% | -0.0362 | 0.73 | -0.5 |
| STRONG_BULL_TREND | 2 | 0.0% | -0.2839 | 0.00 | -0.6 |
| UNCERTAIN | 2,598 | 48.2% | +0.0008 | 1.00 | -26.4 |
| WEAK_BEAR_TREND | 86 | 58.1% | +0.1095 | 1.72 | -1.9 |
| WEAK_BULL_TREND | 69 | 44.9% | -0.0407 | 0.81 | -5.5 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 28 | 42.9% | +0.0814 | 1.77 | -1.5 |
| MIDDAY | 27 | 37.0% | +0.0087 | 1.06 | -2.3 |
| MIDMORNING | 49 | 59.2% | +0.1333 | 1.91 | -1.7 |
| MORNING | 106 | 50.9% | +0.0108 | 1.06 | -10.5 |
| OPEN | 2,895 | 48.6% | +0.0042 | 1.02 | -28.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,546 | 52.2% | +0.0121 | 1.06 | -17.1 |
| SHORT | 1,559 | 45.2% | +0.0023 | 1.01 | -19.0 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,368 | 52.8% | +0.0500 | 1.42 | -5.2 |
| stop | 476 | 0.0% | -0.7500 | 0.00 | -357.0 |
| target | 261 | 100.0% | +1.0000 | inf | 0.0 |

### S4 VWAP reclaim | chop<=5


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 288 | 51.4% | +0.0429 | 1.27 | -4.3 |
| EXPANSION | 39 | 51.3% | +0.0252 | 1.09 | -3.0 |
| HIGH_VOLATILITY_TREND | 1 | 100.0% | +0.0697 | inf | 0.0 |
| RANGE | 54 | 42.6% | -0.0368 | 0.84 | -3.9 |
| STRONG_BEAR_TREND | 5 | 40.0% | -0.0631 | 0.55 | -0.5 |
| STRONG_BULL_TREND | 3 | 33.3% | -0.1274 | 0.33 | -0.6 |
| UNCERTAIN | 2,689 | 48.6% | +0.0040 | 1.02 | -25.0 |
| WEAK_BEAR_TREND | 91 | 57.1% | +0.1006 | 1.63 | -1.9 |
| WEAK_BULL_TREND | 79 | 45.6% | -0.0313 | 0.85 | -5.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 38 | 50.0% | +0.0828 | 1.82 | -1.7 |
| MIDDAY | 35 | 37.1% | -0.0047 | 0.98 | -3.4 |
| MIDMORNING | 57 | 57.9% | +0.0927 | 1.56 | -2.9 |
| MORNING | 112 | 50.0% | +0.0175 | 1.10 | -10.6 |
| OPEN | 3,007 | 48.8% | +0.0060 | 1.03 | -28.6 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,628 | 52.5% | +0.0142 | 1.07 | -13.6 |
| SHORT | 1,621 | 45.3% | +0.0031 | 1.01 | -18.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,480 | 53.1% | +0.0513 | 1.44 | -5.3 |
| stop | 496 | 0.0% | -0.7500 | 0.00 | -372.0 |
| target | 273 | 100.0% | +1.0000 | inf | 0.0 |

### S5 Premarket breakout | immediate


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 55 | 52.7% | +0.0507 | 1.41 | -1.9 |
| HIGH_VOLATILITY_REVERSAL | 3 | 66.7% | +0.0886 | 1.43 | -0.6 |
| RANGE | 52 | 65.4% | +0.1002 | 1.85 | -2.5 |
| UNCERTAIN | 74 | 54.1% | +0.0295 | 1.17 | -3.6 |
| WEAK_BEAR_TREND | 10 | 50.0% | +0.1291 | 1.57 | -1.5 |
| WEAK_BULL_TREND | 15 | 60.0% | +0.0424 | 1.33 | -1.4 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 17 | 82.4% | +0.1450 | 8.56 | -0.2 |
| MIDDAY | 23 | 56.5% | +0.0629 | 1.61 | -1.1 |
| MIDMORNING | 25 | 60.0% | +0.0820 | 1.78 | -1.4 |
| MORNING | 36 | 52.8% | +0.0588 | 1.34 | -1.5 |
| OPEN | 108 | 53.7% | +0.0398 | 1.23 | -4.3 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 123 | 60.2% | +0.0605 | 1.49 | -2.8 |
| SHORT | 86 | 52.3% | +0.0573 | 1.33 | -2.7 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 175 | 59.4% | +0.0664 | 1.72 | -3.3 |
| stop | 19 | 0.0% | -0.7500 | 0.00 | -14.2 |
| target | 15 | 100.0% | +1.0000 | inf | 0.0 |

### S5 Premarket breakout | retest


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 63 | 54.0% | +0.0290 | 1.23 | -2.7 |
| HIGH_VOLATILITY_REVERSAL | 5 | 60.0% | +0.0485 | 1.23 | -1.1 |
| RANGE | 56 | 51.8% | +0.0395 | 1.24 | -3.4 |
| STRONG_BEAR_TREND | 2 | 50.0% | +0.0377 | 3.30 | -0.0 |
| UNCERTAIN | 19 | 57.9% | +0.0882 | 1.51 | -1.6 |
| WEAK_BEAR_TREND | 11 | 63.6% | +0.1999 | 3.55 | -0.3 |
| WEAK_BULL_TREND | 18 | 61.1% | +0.1191 | 1.97 | -1.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 20 | 65.0% | +0.0430 | 1.30 | -1.7 |
| FINAL_30 | 2 | 100.0% | +0.0589 | inf | 0.0 |
| MIDDAY | 33 | 48.5% | -0.0287 | 0.77 | -2.3 |
| MIDMORNING | 31 | 64.5% | +0.1217 | 2.12 | -1.4 |
| MORNING | 41 | 51.2% | +0.0479 | 1.26 | -2.8 |
| OPEN | 47 | 51.1% | +0.0981 | 1.69 | -1.9 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 100 | 58.0% | +0.0327 | 1.27 | -2.5 |
| SHORT | 74 | 51.4% | +0.0960 | 1.56 | -3.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 165 | 56.4% | +0.0629 | 1.56 | -2.1 |
| stop | 6 | 0.0% | -1.0000 | 0.00 | -6.0 |
| target | 3 | 100.0% | +2.0000 | inf | 0.0 |

### S6 Prev-day breakout | immediate


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 293 | 45.1% | -0.0128 | 0.79 | -4.5 |
| EXPANSION | 24 | 50.0% | +0.0731 | 1.63 | -1.7 |
| HIGH_VOLATILITY_REVERSAL | 33 | 60.6% | +0.1165 | 2.65 | -0.6 |
| HIGH_VOLATILITY_TREND | 5 | 80.0% | +0.1947 | 19.95 | -0.1 |
| RANGE | 671 | 49.6% | +0.0086 | 1.15 | -2.2 |
| STRONG_BEAR_TREND | 16 | 75.0% | +0.1064 | 6.03 | -0.3 |
| STRONG_BULL_TREND | 14 | 64.3% | +0.0186 | 1.70 | -0.3 |
| UNCERTAIN | 1,695 | 50.1% | +0.0010 | 1.01 | -13.2 |
| WEAK_BEAR_TREND | 183 | 38.8% | -0.0438 | 0.58 | -8.2 |
| WEAK_BULL_TREND | 153 | 46.4% | +0.0024 | 1.03 | -1.9 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 283 | 48.4% | +0.0091 | 1.16 | -2.5 |
| FINAL_30 | 4 | 75.0% | +0.0875 | 37.39 | -0.0 |
| MIDDAY | 279 | 47.3% | +0.0018 | 1.03 | -2.5 |
| MIDMORNING | 312 | 46.8% | +0.0027 | 1.04 | -3.3 |
| MORNING | 316 | 44.9% | -0.0100 | 0.87 | -6.1 |
| OPEN | 1,893 | 50.4% | +0.0018 | 1.02 | -11.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 1,690 | 50.8% | +0.0046 | 1.07 | -6.0 |
| SHORT | 1,397 | 46.9% | -0.0023 | 0.98 | -12.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 4 | 75.0% | +0.0420 | 1.99 | -0.2 |
| stop | 4 | 0.0% | -1.0000 | 0.00 | -4.0 |
| target | 3 | 100.0% | +1.5000 | inf | 0.0 |
| time_stop | 3,076 | 49.0% | +0.0013 | 1.02 | -15.2 |

### S6 Prev-day breakout | retest


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 819 | 48.5% | -0.0058 | 0.86 | -6.2 |
| EXPANSION | 135 | 49.6% | -0.0071 | 0.90 | -2.8 |
| HIGH_VOLATILITY_REVERSAL | 206 | 48.5% | -0.0126 | 0.84 | -4.1 |
| HIGH_VOLATILITY_TREND | 7 | 0.0% | -0.0998 | 0.00 | -0.7 |
| RANGE | 2,910 | 45.5% | -0.0059 | 0.87 | -17.4 |
| STRONG_BEAR_TREND | 22 | 45.5% | +0.0255 | 1.66 | -0.3 |
| STRONG_BULL_TREND | 32 | 50.0% | +0.0138 | 1.49 | -0.2 |
| UNCERTAIN | 181 | 42.0% | -0.0299 | 0.60 | -5.4 |
| WEAK_BEAR_TREND | 378 | 42.6% | -0.0240 | 0.64 | -9.2 |
| WEAK_BULL_TREND | 344 | 48.8% | +0.0040 | 1.10 | -2.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 1,558 | 46.5% | -0.0078 | 0.83 | -12.4 |
| FINAL_30 | 28 | 50.0% | -0.0037 | 0.94 | -0.7 |
| MIDDAY | 1,421 | 45.0% | -0.0064 | 0.83 | -10.5 |
| MIDMORNING | 970 | 47.4% | -0.0036 | 0.93 | -4.7 |
| MORNING | 576 | 47.4% | -0.0042 | 0.93 | -4.3 |
| OPEN | 481 | 43.7% | -0.0230 | 0.69 | -11.4 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,644 | 47.1% | -0.0060 | 0.85 | -16.4 |
| SHORT | 2,390 | 45.0% | -0.0093 | 0.84 | -22.4 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2 | 50.0% | -0.1166 | 0.05 | -0.2 |
| stop | 3 | 0.0% | -1.0000 | 0.00 | -3.0 |
| target | 1 | 100.0% | +2.0000 | inf | 0.0 |
| time_stop | 5,028 | 46.1% | -0.0073 | 0.85 | -37.0 |

### S7 Failed breakout | prev-day levels


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 405 | 48.1% | +0.0038 | 1.02 | -12.2 |
| EXPANSION | 32 | 59.4% | +0.1164 | 1.56 | -4.0 |
| HIGH_VOLATILITY_REVERSAL | 51 | 49.0% | +0.1587 | 1.97 | -1.1 |
| HIGH_VOLATILITY_TREND | 5 | 20.0% | -0.3130 | 0.17 | -1.6 |
| RANGE | 755 | 53.4% | +0.0363 | 1.25 | -8.6 |
| STRONG_BEAR_TREND | 7 | 42.9% | -0.0141 | 0.90 | -0.6 |
| STRONG_BULL_TREND | 11 | 54.5% | -0.0777 | 0.48 | -1.3 |
| UNCERTAIN | 356 | 51.4% | +0.0258 | 1.14 | -7.1 |
| WEAK_BEAR_TREND | 207 | 52.2% | +0.0639 | 1.32 | -3.0 |
| WEAK_BULL_TREND | 174 | 53.4% | +0.0215 | 1.12 | -7.3 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 280 | 50.4% | +0.0106 | 1.09 | -8.2 |
| FINAL_30 | 6 | 50.0% | +0.0063 | 1.34 | -0.1 |
| MIDDAY | 303 | 54.5% | +0.0535 | 1.42 | -4.5 |
| MIDMORNING | 413 | 52.1% | +0.0233 | 1.13 | -9.7 |
| MORNING | 395 | 52.9% | +0.0482 | 1.26 | -10.6 |
| OPEN | 606 | 50.0% | +0.0274 | 1.14 | -5.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 944 | 55.4% | +0.0458 | 1.26 | -6.3 |
| SHORT | 1,059 | 48.4% | +0.0200 | 1.13 | -8.3 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,864 | 53.5% | +0.0582 | 1.46 | -4.5 |
| stop | 101 | 0.0% | -1.0000 | 0.00 | -101.0 |
| target | 38 | 100.0% | +1.5000 | inf | 0.0 |

### S8 Liquidity sweep | reclaim<=10bars


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 343 | 52.2% | +0.0173 | 1.11 | -5.9 |
| EXPANSION | 32 | 65.6% | +0.0948 | 1.52 | -2.5 |
| HIGH_VOLATILITY_REVERSAL | 38 | 52.6% | +0.1575 | 1.78 | -3.9 |
| HIGH_VOLATILITY_TREND | 3 | 33.3% | -0.1081 | 0.14 | -0.4 |
| RANGE | 678 | 52.8% | +0.0375 | 1.26 | -7.4 |
| STRONG_BEAR_TREND | 9 | 55.6% | +0.0169 | 1.17 | -0.6 |
| STRONG_BULL_TREND | 7 | 42.9% | -0.1125 | 0.31 | -0.8 |
| UNCERTAIN | 423 | 49.2% | -0.0046 | 0.98 | -13.6 |
| WEAK_BEAR_TREND | 181 | 55.2% | +0.0461 | 1.23 | -6.5 |
| WEAK_BULL_TREND | 145 | 41.4% | -0.0487 | 0.76 | -10.8 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 245 | 53.1% | +0.0322 | 1.33 | -6.5 |
| FINAL_30 | 2 | 0.0% | -0.0609 | 0.00 | -0.1 |
| MIDDAY | 311 | 54.3% | +0.0494 | 1.37 | -2.8 |
| MIDMORNING | 358 | 46.6% | -0.0061 | 0.97 | -9.9 |
| MORNING | 334 | 53.9% | +0.0308 | 1.17 | -7.9 |
| OPEN | 609 | 50.7% | +0.0124 | 1.06 | -7.5 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 879 | 54.8% | +0.0229 | 1.13 | -7.3 |
| SHORT | 980 | 48.3% | +0.0190 | 1.12 | -9.3 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,749 | 54.1% | +0.0696 | 1.56 | -6.6 |
| stop | 101 | 0.0% | -1.0000 | 0.00 | -101.0 |
| target | 9 | 100.0% | +2.0000 | inf | 0.0 |

### S8 Liquidity sweep | reclaim<=3bars


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 336 | 50.9% | -0.0028 | 0.98 | -6.7 |
| EXPANSION | 35 | 62.9% | +0.1013 | 1.61 | -2.1 |
| HIGH_VOLATILITY_REVERSAL | 46 | 54.3% | +0.1084 | 1.53 | -3.0 |
| HIGH_VOLATILITY_TREND | 4 | 50.0% | -0.0570 | 0.39 | -0.4 |
| RANGE | 682 | 51.3% | +0.0241 | 1.16 | -7.2 |
| STRONG_BEAR_TREND | 8 | 50.0% | +0.0381 | 1.57 | -0.4 |
| STRONG_BULL_TREND | 8 | 37.5% | -0.1140 | 0.30 | -0.9 |
| UNCERTAIN | 203 | 45.3% | -0.0105 | 0.95 | -10.1 |
| WEAK_BEAR_TREND | 150 | 56.7% | +0.0590 | 1.31 | -3.9 |
| WEAK_BULL_TREND | 131 | 45.8% | -0.0018 | 0.99 | -4.3 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 262 | 51.5% | +0.0230 | 1.23 | -4.2 |
| FINAL_30 | 4 | 25.0% | -0.0344 | 0.52 | -0.2 |
| MIDDAY | 329 | 53.5% | +0.0378 | 1.26 | -6.3 |
| MIDMORNING | 321 | 47.7% | +0.0111 | 1.06 | -6.6 |
| MORNING | 309 | 53.7% | +0.0315 | 1.18 | -6.3 |
| OPEN | 378 | 48.4% | -0.0051 | 0.97 | -13.1 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 766 | 54.4% | +0.0165 | 1.09 | -9.8 |
| SHORT | 837 | 47.4% | +0.0204 | 1.14 | -9.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,503 | 52.6% | +0.0464 | 1.37 | -6.2 |
| stop | 76 | 0.0% | -1.0000 | 0.00 | -76.0 |
| target | 24 | 100.0% | +1.5000 | inf | 0.0 |

### S8 Liquidity sweep | reclaim<=5bars


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 344 | 50.3% | -0.0019 | 0.99 | -6.4 |
| EXPANSION | 35 | 62.9% | +0.0940 | 1.58 | -2.1 |
| HIGH_VOLATILITY_REVERSAL | 42 | 52.4% | +0.1418 | 1.73 | -2.5 |
| HIGH_VOLATILITY_TREND | 3 | 33.3% | -0.1081 | 0.14 | -0.4 |
| RANGE | 683 | 52.6% | +0.0314 | 1.21 | -7.0 |
| STRONG_BEAR_TREND | 8 | 62.5% | +0.0701 | 2.16 | -0.3 |
| STRONG_BULL_TREND | 6 | 33.3% | -0.1339 | 0.27 | -0.8 |
| UNCERTAIN | 296 | 47.6% | -0.0036 | 0.98 | -13.2 |
| WEAK_BEAR_TREND | 167 | 55.1% | +0.0513 | 1.27 | -7.2 |
| WEAK_BULL_TREND | 148 | 43.9% | -0.0409 | 0.79 | -9.7 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 249 | 51.8% | +0.0294 | 1.29 | -5.3 |
| FINAL_30 | 4 | 25.0% | -0.0344 | 0.52 | -0.2 |
| MIDDAY | 314 | 55.7% | +0.0449 | 1.33 | -3.6 |
| MIDMORNING | 353 | 46.2% | -0.0085 | 0.96 | -12.8 |
| MORNING | 324 | 53.4% | +0.0384 | 1.22 | -5.6 |
| OPEN | 488 | 49.4% | +0.0003 | 1.00 | -11.9 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 818 | 54.8% | +0.0189 | 1.10 | -7.6 |
| SHORT | 914 | 47.5% | +0.0169 | 1.11 | -8.5 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 1,614 | 52.9% | +0.0489 | 1.39 | -5.4 |
| stop | 90 | 0.0% | -1.0000 | 0.00 | -90.0 |
| target | 28 | 100.0% | +1.5000 | inf | 0.0 |

### S9 Range reversal | range-filtered


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 1,269 | 51.6% | +0.0115 | 1.07 | -7.1 |
| RANGE | 2,392 | 49.6% | -0.0023 | 0.99 | -24.7 |
| UNCERTAIN | 1,128 | 49.4% | -0.0121 | 0.94 | -15.1 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 706 | 52.3% | +0.0170 | 1.15 | -4.4 |
| FINAL_30 | 13 | 38.5% | -0.0424 | 0.62 | -0.9 |
| MIDDAY | 761 | 49.0% | -0.0110 | 0.93 | -20.8 |
| MIDMORNING | 569 | 48.7% | +0.0025 | 1.01 | -11.3 |
| MORNING | 645 | 52.7% | +0.0158 | 1.10 | -8.5 |
| OPEN | 2,095 | 49.4% | -0.0092 | 0.95 | -32.2 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 2,302 | 52.7% | +0.0038 | 1.02 | -14.4 |
| SHORT | 2,487 | 47.6% | -0.0054 | 0.97 | -22.6 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 2,360 | 50.7% | +0.0034 | 1.04 | -11.4 |
| stop | 1,227 | 0.0% | -0.5000 | 0.00 | -613.5 |
| target | 1,202 | 100.0% | +0.5000 | inf | 0.0 |

### S9 Range reversal | unfiltered


**Regime**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| COMPRESSION | 3,823 | 49.0% | +0.0010 | 1.03 | -4.6 |
| EXPANSION | 1,037 | 48.2% | -0.0033 | 0.94 | -6.2 |
| HIGH_VOLATILITY_REVERSAL | 1,278 | 49.3% | -0.0049 | 0.93 | -9.9 |
| HIGH_VOLATILITY_TREND | 136 | 52.2% | -0.0012 | 0.98 | -4.5 |
| RANGE | 15,502 | 50.2% | -0.0017 | 0.95 | -36.2 |
| STRONG_BEAR_TREND | 295 | 52.5% | +0.0059 | 1.14 | -1.2 |
| STRONG_BULL_TREND | 813 | 51.2% | -0.0003 | 0.99 | -3.8 |
| UNCERTAIN | 1,128 | 48.3% | +0.0023 | 1.04 | -3.1 |
| WEAK_BEAR_TREND | 2,395 | 51.1% | -0.0018 | 0.97 | -11.2 |
| WEAK_BULL_TREND | 3,118 | 49.8% | -0.0035 | 0.91 | -17.0 |

**Time of day**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| AFTERNOON | 9,481 | 50.1% | -0.0003 | 0.99 | -18.1 |
| FINAL_30 | 163 | 41.7% | -0.0185 | 0.70 | -3.7 |
| MIDDAY | 9,312 | 49.9% | -0.0034 | 0.91 | -38.8 |
| MIDMORNING | 5,207 | 50.1% | -0.0032 | 0.93 | -20.4 |
| MORNING | 2,873 | 50.8% | +0.0014 | 1.03 | -6.5 |
| OPEN | 2,489 | 49.1% | +0.0023 | 1.04 | -5.0 |

**Direction**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| LONG | 11,535 | 51.9% | -0.0024 | 0.95 | -35.6 |
| SHORT | 17,990 | 48.7% | -0.0009 | 0.97 | -33.2 |

**Exit reason**

| | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| session_close | 8 | 25.0% | -0.0078 | 0.81 | -0.3 |
| stop | 141 | 0.0% | -0.5000 | 0.00 | -70.5 |
| target | 155 | 100.0% | +0.5000 | inf | 0.0 |
| time_stop | 29,221 | 49.9% | -0.0017 | 0.96 | -54.9 |

## Every combination tested

864 (variant x exit-policy) pairs. Listed in full so the size of the search is visible - a best result picked from a large grid deserves more scepticism than one picked from a small grid.

| Strategy | Variant | Exit | Trades | Win% | Expectancy (ATR) | PF |
|---|---|---|---|---|---|---|
| BASELINE random | 2/session | `t0.5/s0.5/m30` | 6,133 | 48.8% | -0.0002 | 1.00 |
| BASELINE random | 2/session | `t1.0/s0.75/m30` | 6,131 | 48.8% | -0.0003 | 1.00 |
| BASELINE random | 2/session | `t1.5/s1.0/m30` | 6,129 | 48.8% | -0.0006 | 0.99 |
| BASELINE random | 2/session | `t2.0/s1.0/m30` | 6,129 | 48.8% | -0.0006 | 0.99 |
| BASELINE random | 2/session | `t0.5/s0.5/m15` | 6,392 | 48.6% | -0.0015 | 0.96 |
| BASELINE random | 2/session | `t1.5/s1.0/m15` | 6,392 | 48.6% | -0.0017 | 0.96 |
| BASELINE random | 2/session | `t2.0/s1.0/m15` | 6,392 | 48.6% | -0.0017 | 0.96 |
| BASELINE random | 2/session | `t1.0/s0.75/m15` | 6,392 | 48.6% | -0.0018 | 0.96 |
| BASELINE random | 2/session | `t0.5/s0.5/m-` | 3,935 | 48.8% | -0.0042 | 0.97 |
| BASELINE random | 2/session | `t2.0/s1.0/m-` | 3,392 | 49.2% | -0.0101 | 0.94 |
| BASELINE random | 2/session | `t1.0/s0.75/m-` | 3,502 | 48.8% | -0.0108 | 0.94 |
| BASELINE random | 2/session | `t1.5/s1.0/m-` | 3,397 | 49.2% | -0.0109 | 0.94 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.5/s1.0/m30` | 27,507 | 48.9% | +0.0004 | 1.01 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t2.0/s1.0/m30` | 27,505 | 48.8% | +0.0002 | 1.00 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.0/s0.75/m30` | 27,534 | 48.8% | -0.0000 | 1.00 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.5/s1.0/m15` | 49,052 | 47.9% | -0.0005 | 0.99 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t2.0/s1.0/m15` | 49,050 | 47.9% | -0.0005 | 0.99 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t2.0/s1.0/m-` | 3,503 | 48.2% | -0.0006 | 1.00 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.0/s0.75/m15` | 49,069 | 47.9% | -0.0006 | 0.98 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t0.5/s0.5/m30` | 27,767 | 48.7% | -0.0007 | 0.99 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t0.5/s0.5/m15` | 49,189 | 47.8% | -0.0010 | 0.98 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.5/s1.0/m-` | 3,542 | 48.3% | -0.0011 | 0.99 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t1.0/s0.75/m-` | 3,948 | 47.7% | -0.0050 | 0.98 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | `t0.5/s0.5/m-` | 5,771 | 48.7% | -0.0086 | 0.95 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.5/s1.0/m15` | 37,820 | 47.8% | -0.0004 | 0.99 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t2.0/s1.0/m15` | 37,820 | 47.8% | -0.0005 | 0.99 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.0/s0.75/m15` | 37,835 | 47.7% | -0.0008 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.5/s1.0/m30` | 23,456 | 48.2% | -0.0009 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t2.0/s1.0/m30` | 23,455 | 48.1% | -0.0012 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t0.5/s0.5/m15` | 37,920 | 47.7% | -0.0012 | 0.97 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t0.5/s0.5/m30` | 23,658 | 48.0% | -0.0012 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.0/s0.75/m30` | 23,474 | 48.1% | -0.0013 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.5/s1.0/m-` | 3,502 | 48.8% | -0.0015 | 0.99 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t0.5/s0.5/m-` | 5,495 | 49.6% | -0.0038 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t2.0/s1.0/m-` | 3,466 | 48.6% | -0.0041 | 0.98 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | `t1.0/s0.75/m-` | 3,880 | 48.0% | -0.0045 | 0.98 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t0.5/s0.5/m-` | 818 | 52.1% | -0.0044 | 0.97 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.5/s1.0/m15` | 1,877 | 47.3% | -0.0048 | 0.89 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t2.0/s1.0/m15` | 1,877 | 47.3% | -0.0048 | 0.89 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.0/s0.75/m15` | 1,878 | 47.2% | -0.0051 | 0.89 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t0.5/s0.5/m15` | 1,881 | 47.1% | -0.0055 | 0.88 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.5/s1.0/m30` | 1,321 | 47.5% | -0.0077 | 0.88 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t2.0/s1.0/m30` | 1,321 | 47.5% | -0.0077 | 0.88 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t0.5/s0.5/m30` | 1,329 | 47.1% | -0.0083 | 0.88 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.0/s0.75/m30` | 1,323 | 47.4% | -0.0083 | 0.88 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.0/s0.75/m-` | 752 | 51.2% | -0.0271 | 0.86 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t2.0/s1.0/m-` | 744 | 51.9% | -0.0286 | 0.85 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | `t1.5/s1.0/m-` | 744 | 51.9% | -0.0317 | 0.84 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t2.0/s1.0/m-` | 3,466 | 50.1% | +0.0188 | 1.09 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.0/s0.75/m-` | 3,809 | 50.1% | +0.0188 | 1.10 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.5/s1.0/m-` | 3,480 | 50.2% | +0.0186 | 1.09 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t0.5/s0.5/m-` | 5,539 | 50.7% | +0.0107 | 1.06 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t0.5/s0.5/m30` | 28,439 | 48.9% | +0.0006 | 1.01 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.5/s1.0/m30` | 28,295 | 48.7% | -0.0005 | 0.99 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t2.0/s1.0/m30` | 28,294 | 48.7% | -0.0006 | 0.99 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.0/s0.75/m30` | 28,303 | 48.7% | -0.0006 | 0.99 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t0.5/s0.5/m15` | 49,545 | 47.8% | -0.0010 | 0.97 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.0/s0.75/m15` | 49,487 | 47.8% | -0.0012 | 0.97 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t1.5/s1.0/m15` | 49,480 | 47.8% | -0.0012 | 0.97 |
| LIVE SPY_KEY_LEVELS | deployed rules | `t2.0/s1.0/m15` | 49,480 | 47.8% | -0.0013 | 0.97 |
| PB1 Opening gap fade | spec thresholds | `t0.5/s0.5/m15` | 46 | 60.9% | +0.0389 | 1.76 |
| PB1 Opening gap fade | spec thresholds | `t1.5/s1.0/m15` | 46 | 60.9% | +0.0321 | 1.59 |
| PB1 Opening gap fade | spec thresholds | `t2.0/s1.0/m15` | 46 | 60.9% | +0.0321 | 1.59 |
| PB1 Opening gap fade | spec thresholds | `t1.0/s0.75/m15` | 46 | 60.9% | +0.0297 | 1.52 |
| PB1 Opening gap fade | spec thresholds | `t0.5/s0.5/m30` | 46 | 60.9% | +0.0294 | 1.36 |
| PB1 Opening gap fade | spec thresholds | `t1.5/s1.0/m30` | 46 | 58.7% | +0.0171 | 1.20 |
| PB1 Opening gap fade | spec thresholds | `t2.0/s1.0/m30` | 46 | 58.7% | +0.0171 | 1.20 |
| PB1 Opening gap fade | spec thresholds | `t1.0/s0.75/m30` | 46 | 58.7% | +0.0144 | 1.17 |
| PB1 Opening gap fade | spec thresholds | `t0.5/s0.5/m-` | 46 | 47.8% | -0.0179 | 0.93 |
| PB1 Opening gap fade | spec thresholds | `t1.0/s0.75/m-` | 46 | 39.1% | -0.1068 | 0.65 |
| PB1 Opening gap fade | spec thresholds | `t2.0/s1.0/m-` | 46 | 39.1% | -0.1614 | 0.54 |
| PB1 Opening gap fade | spec thresholds | `t1.5/s1.0/m-` | 46 | 39.1% | -0.1723 | 0.51 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.0/s0.75/m-` | 114 | 47.4% | -0.0038 | 0.97 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.5/s1.0/m-` | 114 | 48.2% | -0.0078 | 0.94 |
| PB2 Momentum squeeze | eff>=0.65 | `t2.0/s1.0/m-` | 114 | 48.2% | -0.0078 | 0.94 |
| PB2 Momentum squeeze | eff>=0.65 | `t0.5/s0.5/m-` | 114 | 45.6% | -0.0204 | 0.85 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.5/s1.0/m30` | 114 | 44.7% | -0.0224 | 0.68 |
| PB2 Momentum squeeze | eff>=0.65 | `t2.0/s1.0/m30` | 114 | 44.7% | -0.0224 | 0.68 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.5/s1.0/m15` | 114 | 43.9% | -0.0233 | 0.56 |
| PB2 Momentum squeeze | eff>=0.65 | `t2.0/s1.0/m15` | 114 | 43.9% | -0.0233 | 0.56 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.0/s0.75/m15` | 114 | 43.0% | -0.0308 | 0.49 |
| PB2 Momentum squeeze | eff>=0.65 | `t1.0/s0.75/m30` | 114 | 43.9% | -0.0314 | 0.59 |
| PB2 Momentum squeeze | eff>=0.65 | `t0.5/s0.5/m30` | 114 | 43.0% | -0.0339 | 0.57 |
| PB2 Momentum squeeze | eff>=0.65 | `t0.5/s0.5/m15` | 114 | 42.1% | -0.0361 | 0.43 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.0/s0.75/m15` | 24 | 33.3% | -0.0489 | 0.35 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.5/s1.0/m15` | 24 | 33.3% | -0.0489 | 0.35 |
| PB2 Momentum squeeze | eff>=0.75 | `t2.0/s1.0/m15` | 24 | 33.3% | -0.0489 | 0.35 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.5/s1.0/m-` | 24 | 50.0% | -0.0519 | 0.64 |
| PB2 Momentum squeeze | eff>=0.75 | `t2.0/s1.0/m-` | 24 | 50.0% | -0.0519 | 0.64 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.0/s0.75/m30` | 24 | 41.7% | -0.0549 | 0.44 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.5/s1.0/m30` | 24 | 41.7% | -0.0549 | 0.44 |
| PB2 Momentum squeeze | eff>=0.75 | `t2.0/s1.0/m30` | 24 | 41.7% | -0.0549 | 0.44 |
| PB2 Momentum squeeze | eff>=0.75 | `t0.5/s0.5/m30` | 24 | 37.5% | -0.0803 | 0.28 |
| PB2 Momentum squeeze | eff>=0.75 | `t0.5/s0.5/m15` | 24 | 29.2% | -0.0845 | 0.19 |
| PB2 Momentum squeeze | eff>=0.75 | `t1.0/s0.75/m-` | 24 | 45.8% | -0.0880 | 0.51 |
| PB2 Momentum squeeze | eff>=0.75 | `t0.5/s0.5/m-` | 24 | 41.7% | -0.1015 | 0.46 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.5/s1.0/m-` | 4 | 75.0% | -0.0589 | 0.49 |
| PB2 Momentum squeeze | eff>=0.85 | `t2.0/s1.0/m-` | 4 | 75.0% | -0.0589 | 0.49 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.0/s0.75/m15` | 4 | 25.0% | -0.1642 | 0.03 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.5/s1.0/m15` | 4 | 25.0% | -0.1642 | 0.03 |
| PB2 Momentum squeeze | eff>=0.85 | `t2.0/s1.0/m15` | 4 | 25.0% | -0.1642 | 0.03 |
| PB2 Momentum squeeze | eff>=0.85 | `t0.5/s0.5/m30` | 4 | 25.0% | -0.1955 | 0.09 |
| PB2 Momentum squeeze | eff>=0.85 | `t0.5/s0.5/m15` | 4 | 25.0% | -0.2109 | 0.02 |
| PB2 Momentum squeeze | eff>=0.85 | `t0.5/s0.5/m-` | 4 | 50.0% | -0.2131 | 0.15 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.0/s0.75/m30` | 4 | 25.0% | -0.2379 | 0.08 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.5/s1.0/m30` | 4 | 25.0% | -0.2379 | 0.08 |
| PB2 Momentum squeeze | eff>=0.85 | `t2.0/s1.0/m30` | 4 | 25.0% | -0.2379 | 0.08 |
| PB2 Momentum squeeze | eff>=0.85 | `t1.0/s0.75/m-` | 4 | 50.0% | -0.3381 | 0.10 |
| S1 ORB retest | or15 | `t1.0/s0.75/m-` | 3,324 | 48.5% | +0.0001 | 1.00 |
| S1 ORB retest | or15 | `t1.5/s1.0/m-` | 3,291 | 48.8% | +0.0000 | 1.00 |
| S1 ORB retest | or15 | `t2.0/s1.0/m-` | 3,291 | 48.7% | -0.0009 | 1.00 |
| S1 ORB retest | or15 | `t0.5/s0.5/m30` | 6,265 | 49.4% | -0.0010 | 0.98 |
| S1 ORB retest | or15 | `t1.0/s0.75/m30` | 6,261 | 49.4% | -0.0014 | 0.98 |
| S1 ORB retest | or15 | `t1.5/s1.0/m30` | 6,260 | 49.5% | -0.0017 | 0.97 |
| S1 ORB retest | or15 | `t2.0/s1.0/m30` | 6,260 | 49.5% | -0.0017 | 0.97 |
| S1 ORB retest | or15 | `t1.0/s0.75/m15` | 7,640 | 47.9% | -0.0024 | 0.95 |
| S1 ORB retest | or15 | `t1.5/s1.0/m15` | 7,640 | 47.9% | -0.0026 | 0.95 |
| S1 ORB retest | or15 | `t2.0/s1.0/m15` | 7,640 | 47.9% | -0.0026 | 0.95 |
| S1 ORB retest | or15 | `t0.5/s0.5/m15` | 7,641 | 47.9% | -0.0027 | 0.94 |
| S1 ORB retest | or15 | `t0.5/s0.5/m-` | 3,505 | 49.5% | -0.0037 | 0.98 |
| S1 ORB retest | or30 | `t2.0/s1.0/m-` | 3,267 | 48.3% | -0.0001 | 1.00 |
| S1 ORB retest | or30 | `t1.5/s1.0/m-` | 3,267 | 48.3% | -0.0004 | 1.00 |
| S1 ORB retest | or30 | `t0.5/s0.5/m30` | 6,696 | 48.7% | -0.0018 | 0.97 |
| S1 ORB retest | or30 | `t1.0/s0.75/m30` | 6,688 | 48.7% | -0.0023 | 0.96 |
| S1 ORB retest | or30 | `t1.5/s1.0/m30` | 6,688 | 48.7% | -0.0025 | 0.96 |
| S1 ORB retest | or30 | `t0.5/s0.5/m15` | 8,269 | 47.3% | -0.0027 | 0.94 |
| S1 ORB retest | or30 | `t1.0/s0.75/m15` | 8,266 | 47.4% | -0.0028 | 0.94 |
| S1 ORB retest | or30 | `t2.0/s1.0/m30` | 6,688 | 48.7% | -0.0028 | 0.95 |
| S1 ORB retest | or30 | `t1.5/s1.0/m15` | 8,266 | 47.4% | -0.0030 | 0.93 |
| S1 ORB retest | or30 | `t2.0/s1.0/m15` | 8,266 | 47.4% | -0.0030 | 0.93 |
| S1 ORB retest | or30 | `t1.0/s0.75/m-` | 3,300 | 47.9% | -0.0038 | 0.98 |
| S1 ORB retest | or30 | `t0.5/s0.5/m-` | 3,431 | 48.9% | -0.0078 | 0.96 |
| S1 ORB retest | or5 | `t2.0/s1.0/m-` | 3,198 | 50.0% | +0.0172 | 1.08 |
| S1 ORB retest | or5 | `t1.5/s1.0/m-` | 3,198 | 50.0% | +0.0155 | 1.08 |
| S1 ORB retest | or5 | `t1.0/s0.75/m-` | 3,240 | 49.5% | +0.0136 | 1.07 |
| S1 ORB retest | or5 | `t0.5/s0.5/m-` | 3,422 | 49.8% | +0.0029 | 1.02 |
| S1 ORB retest | or5 | `t0.5/s0.5/m30` | 5,543 | 50.0% | +0.0027 | 1.04 |
| S1 ORB retest | or5 | `t2.0/s1.0/m30` | 5,541 | 50.0% | +0.0026 | 1.04 |
| S1 ORB retest | or5 | `t1.5/s1.0/m30` | 5,541 | 50.0% | +0.0026 | 1.04 |
| S1 ORB retest | or5 | `t1.0/s0.75/m30` | 5,541 | 50.0% | +0.0025 | 1.04 |
| S1 ORB retest | or5 | `t1.0/s0.75/m15` | 6,545 | 49.8% | +0.0010 | 1.02 |
| S1 ORB retest | or5 | `t1.5/s1.0/m15` | 6,544 | 49.8% | +0.0009 | 1.02 |
| S1 ORB retest | or5 | `t2.0/s1.0/m15` | 6,544 | 49.8% | +0.0009 | 1.02 |
| S1 ORB retest | or5 | `t0.5/s0.5/m15` | 6,546 | 49.8% | +0.0007 | 1.01 |
| S10 VWAP reversion | 0.5atr | `t1.0/s0.75/m-` | 420 | 52.1% | +0.0284 | 1.19 |
| S10 VWAP reversion | 0.5atr | `t2.0/s1.0/m-` | 409 | 52.1% | +0.0283 | 1.18 |
| S10 VWAP reversion | 0.5atr | `t1.5/s1.0/m-` | 409 | 52.1% | +0.0269 | 1.17 |
| S10 VWAP reversion | 0.5atr | `t0.5/s0.5/m-` | 454 | 49.6% | +0.0061 | 1.04 |
| S10 VWAP reversion | 0.5atr | `t0.5/s0.5/m30` | 712 | 54.1% | +0.0057 | 1.08 |
| S10 VWAP reversion | 0.5atr | `t1.0/s0.75/m30` | 703 | 54.2% | +0.0049 | 1.07 |
| S10 VWAP reversion | 0.5atr | `t1.0/s0.75/m15` | 950 | 54.8% | +0.0024 | 1.05 |
| S10 VWAP reversion | 0.5atr | `t0.5/s0.5/m15` | 957 | 54.8% | +0.0018 | 1.03 |
| S10 VWAP reversion | 0.5atr | `t1.5/s1.0/m30` | 702 | 54.0% | +0.0014 | 1.02 |
| S10 VWAP reversion | 0.5atr | `t2.0/s1.0/m30` | 702 | 54.0% | +0.0014 | 1.02 |
| S10 VWAP reversion | 0.5atr | `t1.5/s1.0/m15` | 950 | 54.6% | +0.0000 | 1.00 |
| S10 VWAP reversion | 0.5atr | `t2.0/s1.0/m15` | 950 | 54.6% | -0.0014 | 0.97 |
| S10 VWAP reversion | 0.75atr | `t1.0/s0.75/m15` | 88 | 50.0% | -0.0245 | 0.67 |
| S10 VWAP reversion | 0.75atr | `t1.5/s1.0/m15` | 88 | 50.0% | -0.0245 | 0.67 |
| S10 VWAP reversion | 0.75atr | `t2.0/s1.0/m15` | 88 | 50.0% | -0.0245 | 0.67 |
| S10 VWAP reversion | 0.75atr | `t1.0/s0.75/m-` | 54 | 50.0% | -0.0250 | 0.87 |
| S10 VWAP reversion | 0.75atr | `t0.5/s0.5/m15` | 91 | 51.6% | -0.0289 | 0.65 |
| S10 VWAP reversion | 0.75atr | `t1.5/s1.0/m30` | 69 | 46.4% | -0.0335 | 0.65 |
| S10 VWAP reversion | 0.75atr | `t2.0/s1.0/m30` | 69 | 46.4% | -0.0335 | 0.65 |
| S10 VWAP reversion | 0.75atr | `t0.5/s0.5/m30` | 72 | 44.4% | -0.0451 | 0.60 |
| S10 VWAP reversion | 0.75atr | `t1.0/s0.75/m30` | 70 | 45.7% | -0.0453 | 0.58 |
| S10 VWAP reversion | 0.75atr | `t1.5/s1.0/m-` | 52 | 48.1% | -0.0578 | 0.72 |
| S10 VWAP reversion | 0.75atr | `t2.0/s1.0/m-` | 52 | 48.1% | -0.0578 | 0.72 |
| S10 VWAP reversion | 0.75atr | `t0.5/s0.5/m-` | 57 | 43.9% | -0.0581 | 0.70 |
| S10 VWAP reversion | 1.0atr | `t1.5/s1.0/m-` | 7 | 71.4% | +0.2378 | 5.18 |
| S10 VWAP reversion | 1.0atr | `t2.0/s1.0/m-` | 7 | 71.4% | +0.2378 | 5.18 |
| S10 VWAP reversion | 1.0atr | `t1.0/s0.75/m-` | 7 | 71.4% | +0.2150 | 4.78 |
| S10 VWAP reversion | 1.0atr | `t1.0/s0.75/m30` | 9 | 44.4% | +0.0033 | 1.03 |
| S10 VWAP reversion | 1.0atr | `t1.5/s1.0/m30` | 9 | 44.4% | +0.0033 | 1.03 |
| S10 VWAP reversion | 1.0atr | `t2.0/s1.0/m30` | 9 | 44.4% | +0.0033 | 1.03 |
| S10 VWAP reversion | 1.0atr | `t0.5/s0.5/m-` | 7 | 57.1% | -0.0049 | 0.97 |
| S10 VWAP reversion | 1.0atr | `t0.5/s0.5/m30` | 9 | 44.4% | -0.0128 | 0.89 |
| S10 VWAP reversion | 1.0atr | `t0.5/s0.5/m15` | 10 | 60.0% | -0.0156 | 0.85 |
| S10 VWAP reversion | 1.0atr | `t1.0/s0.75/m15` | 10 | 60.0% | -0.0281 | 0.73 |
| S10 VWAP reversion | 1.0atr | `t1.5/s1.0/m15` | 10 | 60.0% | -0.0281 | 0.73 |
| S10 VWAP reversion | 1.0atr | `t2.0/s1.0/m15` | 10 | 60.0% | -0.0281 | 0.73 |
| S10 VWAP reversion | 1.25atr | `t1.0/s0.75/m-` | 2 | 100.0% | +0.3529 | inf |
| S10 VWAP reversion | 1.25atr | `t1.5/s1.0/m-` | 2 | 100.0% | +0.3529 | inf |
| S10 VWAP reversion | 1.25atr | `t2.0/s1.0/m-` | 2 | 100.0% | +0.3529 | inf |
| S10 VWAP reversion | 1.25atr | `t0.5/s0.5/m-` | 2 | 100.0% | +0.2960 | inf |
| S10 VWAP reversion | 1.25atr | `t0.5/s0.5/m15` | 2 | 100.0% | +0.2236 | inf |
| S10 VWAP reversion | 1.25atr | `t1.0/s0.75/m15` | 2 | 100.0% | +0.2236 | inf |
| S10 VWAP reversion | 1.25atr | `t1.5/s1.0/m15` | 2 | 100.0% | +0.2236 | inf |
| S10 VWAP reversion | 1.25atr | `t2.0/s1.0/m15` | 2 | 100.0% | +0.2236 | inf |
| S10 VWAP reversion | 1.25atr | `t0.5/s0.5/m30` | 2 | 50.0% | +0.2056 | 12.17 |
| S10 VWAP reversion | 1.25atr | `t1.0/s0.75/m30` | 2 | 50.0% | +0.2056 | 12.17 |
| S10 VWAP reversion | 1.25atr | `t1.5/s1.0/m30` | 2 | 50.0% | +0.2056 | 12.17 |
| S10 VWAP reversion | 1.25atr | `t2.0/s1.0/m30` | 2 | 50.0% | +0.2056 | 12.17 |
| S11 Compression break | 10bars quiet | `t0.5/s0.5/m30` | 5 | 60.0% | +0.0176 | 2.71 |
| S11 Compression break | 10bars quiet | `t1.0/s0.75/m30` | 5 | 60.0% | +0.0176 | 2.71 |
| S11 Compression break | 10bars quiet | `t1.5/s1.0/m30` | 5 | 60.0% | +0.0176 | 2.71 |
| S11 Compression break | 10bars quiet | `t2.0/s1.0/m30` | 5 | 60.0% | +0.0176 | 2.71 |
| S11 Compression break | 10bars quiet | `t0.5/s0.5/m15` | 6 | 33.3% | -0.0072 | 0.65 |
| S11 Compression break | 10bars quiet | `t1.0/s0.75/m15` | 6 | 33.3% | -0.0072 | 0.65 |
| S11 Compression break | 10bars quiet | `t1.5/s1.0/m15` | 6 | 33.3% | -0.0072 | 0.65 |
| S11 Compression break | 10bars quiet | `t2.0/s1.0/m15` | 6 | 33.3% | -0.0072 | 0.65 |
| S11 Compression break | 10bars quiet | `t0.5/s0.5/m-` | 4 | 50.0% | -0.0543 | 0.32 |
| S11 Compression break | 10bars quiet | `t1.0/s0.75/m-` | 4 | 50.0% | -0.0543 | 0.32 |
| S11 Compression break | 10bars quiet | `t1.5/s1.0/m-` | 4 | 50.0% | -0.0543 | 0.32 |
| S11 Compression break | 10bars quiet | `t2.0/s1.0/m-` | 4 | 50.0% | -0.0543 | 0.32 |
| S11 Compression break | 3bars quiet | `t0.5/s0.5/m-` | 754 | 50.0% | +0.0065 | 1.06 |
| S11 Compression break | 3bars quiet | `t0.5/s0.5/m30` | 887 | 48.6% | +0.0044 | 1.10 |
| S11 Compression break | 3bars quiet | `t1.5/s1.0/m-` | 738 | 48.8% | +0.0037 | 1.03 |
| S11 Compression break | 3bars quiet | `t1.0/s0.75/m30` | 887 | 48.6% | +0.0035 | 1.08 |
| S11 Compression break | 3bars quiet | `t1.5/s1.0/m30` | 887 | 48.6% | +0.0032 | 1.07 |
| S11 Compression break | 3bars quiet | `t2.0/s1.0/m30` | 887 | 48.6% | +0.0032 | 1.07 |
| S11 Compression break | 3bars quiet | `t2.0/s1.0/m-` | 738 | 48.6% | +0.0007 | 1.01 |
| S11 Compression break | 3bars quiet | `t0.5/s0.5/m15` | 909 | 46.5% | -0.0004 | 0.99 |
| S11 Compression break | 3bars quiet | `t1.0/s0.75/m15` | 909 | 46.5% | -0.0007 | 0.98 |
| S11 Compression break | 3bars quiet | `t1.5/s1.0/m15` | 909 | 46.5% | -0.0007 | 0.98 |
| S11 Compression break | 3bars quiet | `t2.0/s1.0/m15` | 909 | 46.5% | -0.0007 | 0.98 |
| S11 Compression break | 3bars quiet | `t1.0/s0.75/m-` | 740 | 48.6% | -0.0015 | 0.99 |
| S11 Compression break | 5bars quiet | `t1.5/s1.0/m-` | 101 | 45.5% | +0.0123 | 1.12 |
| S11 Compression break | 5bars quiet | `t2.0/s1.0/m-` | 101 | 45.5% | +0.0123 | 1.12 |
| S11 Compression break | 5bars quiet | `t1.0/s0.75/m-` | 101 | 45.5% | +0.0108 | 1.10 |
| S11 Compression break | 5bars quiet | `t0.5/s0.5/m30` | 107 | 48.6% | +0.0090 | 1.21 |
| S11 Compression break | 5bars quiet | `t1.0/s0.75/m30` | 107 | 48.6% | +0.0090 | 1.21 |
| S11 Compression break | 5bars quiet | `t1.5/s1.0/m30` | 107 | 48.6% | +0.0090 | 1.21 |
| S11 Compression break | 5bars quiet | `t2.0/s1.0/m30` | 107 | 48.6% | +0.0090 | 1.21 |
| S11 Compression break | 5bars quiet | `t0.5/s0.5/m15` | 110 | 49.1% | +0.0045 | 1.15 |
| S11 Compression break | 5bars quiet | `t1.0/s0.75/m15` | 110 | 49.1% | +0.0045 | 1.15 |
| S11 Compression break | 5bars quiet | `t1.5/s1.0/m15` | 110 | 49.1% | +0.0045 | 1.15 |
| S11 Compression break | 5bars quiet | `t2.0/s1.0/m15` | 110 | 49.1% | +0.0045 | 1.15 |
| S11 Compression break | 5bars quiet | `t0.5/s0.5/m-` | 101 | 44.6% | -0.0063 | 0.94 |
| S12 First pullback | 0.5atr drive | `t1.0/s0.75/m-` | 215 | 51.2% | +0.0460 | 1.21 |
| S12 First pullback | 0.5atr drive | `t1.5/s1.0/m-` | 215 | 51.6% | +0.0335 | 1.13 |
| S12 First pullback | 0.5atr drive | `t0.5/s0.5/m-` | 215 | 54.0% | +0.0311 | 1.17 |
| S12 First pullback | 0.5atr drive | `t2.0/s1.0/m-` | 215 | 51.2% | +0.0258 | 1.10 |
| S12 First pullback | 0.5atr drive | `t0.5/s0.5/m30` | 215 | 50.7% | +0.0025 | 1.03 |
| S12 First pullback | 0.5atr drive | `t1.5/s1.0/m30` | 215 | 51.2% | -0.0011 | 0.99 |
| S12 First pullback | 0.5atr drive | `t2.0/s1.0/m30` | 215 | 51.2% | -0.0011 | 0.99 |
| S12 First pullback | 0.5atr drive | `t1.0/s0.75/m30` | 215 | 50.7% | -0.0040 | 0.96 |
| S12 First pullback | 0.5atr drive | `t0.5/s0.5/m15` | 215 | 48.4% | -0.0074 | 0.89 |
| S12 First pullback | 0.5atr drive | `t1.0/s0.75/m15` | 215 | 47.9% | -0.0119 | 0.84 |
| S12 First pullback | 0.5atr drive | `t1.5/s1.0/m15` | 215 | 47.9% | -0.0130 | 0.82 |
| S12 First pullback | 0.5atr drive | `t2.0/s1.0/m15` | 215 | 47.9% | -0.0130 | 0.82 |
| S12 First pullback | 0.75atr drive | `t0.5/s0.5/m-` | 33 | 51.5% | -0.0159 | 0.93 |
| S12 First pullback | 0.75atr drive | `t0.5/s0.5/m30` | 33 | 48.5% | -0.0292 | 0.80 |
| S12 First pullback | 0.75atr drive | `t0.5/s0.5/m15` | 33 | 45.5% | -0.0300 | 0.69 |
| S12 First pullback | 0.75atr drive | `t1.0/s0.75/m15` | 33 | 45.5% | -0.0363 | 0.65 |
| S12 First pullback | 0.75atr drive | `t1.5/s1.0/m15` | 33 | 45.5% | -0.0439 | 0.61 |
| S12 First pullback | 0.75atr drive | `t2.0/s1.0/m15` | 33 | 45.5% | -0.0439 | 0.61 |
| S12 First pullback | 0.75atr drive | `t2.0/s1.0/m-` | 33 | 51.5% | -0.0521 | 0.83 |
| S12 First pullback | 0.75atr drive | `t1.5/s1.0/m30` | 33 | 51.5% | -0.0539 | 0.66 |
| S12 First pullback | 0.75atr drive | `t2.0/s1.0/m30` | 33 | 51.5% | -0.0539 | 0.66 |
| S12 First pullback | 0.75atr drive | `t1.0/s0.75/m-` | 33 | 51.5% | -0.0589 | 0.78 |
| S12 First pullback | 0.75atr drive | `t1.5/s1.0/m-` | 33 | 51.5% | -0.0682 | 0.78 |
| S12 First pullback | 0.75atr drive | `t1.0/s0.75/m30` | 33 | 48.5% | -0.0696 | 0.59 |
| S12 First pullback | 1.0atr drive | `t0.5/s0.5/m30` | 14 | 35.7% | -0.0912 | 0.57 |
| S12 First pullback | 1.0atr drive | `t0.5/s0.5/m15` | 14 | 21.4% | -0.1016 | 0.37 |
| S12 First pullback | 1.0atr drive | `t1.0/s0.75/m15` | 14 | 21.4% | -0.1258 | 0.29 |
| S12 First pullback | 1.0atr drive | `t1.0/s0.75/m-` | 14 | 42.9% | -0.1323 | 0.61 |
| S12 First pullback | 1.0atr drive | `t1.5/s1.0/m15` | 14 | 21.4% | -0.1436 | 0.27 |
| S12 First pullback | 1.0atr drive | `t2.0/s1.0/m15` | 14 | 21.4% | -0.1436 | 0.27 |
| S12 First pullback | 1.0atr drive | `t2.0/s1.0/m-` | 14 | 42.9% | -0.1452 | 0.62 |
| S12 First pullback | 1.0atr drive | `t1.5/s1.0/m-` | 14 | 42.9% | -0.1474 | 0.62 |
| S12 First pullback | 1.0atr drive | `t1.0/s0.75/m30` | 14 | 35.7% | -0.1478 | 0.37 |
| S12 First pullback | 1.0atr drive | `t1.5/s1.0/m30` | 14 | 35.7% | -0.1657 | 0.35 |
| S12 First pullback | 1.0atr drive | `t2.0/s1.0/m30` | 14 | 35.7% | -0.1657 | 0.35 |
| S12 First pullback | 1.0atr drive | `t0.5/s0.5/m-` | 14 | 35.7% | -0.1766 | 0.41 |
| S13 Structure reversal | no vwap filter | `t0.5/s0.5/m15` | 33,104 | 48.1% | -0.0012 | 0.97 |
| S13 Structure reversal | no vwap filter | `t1.0/s0.75/m15` | 33,068 | 48.1% | -0.0013 | 0.97 |
| S13 Structure reversal | no vwap filter | `t1.5/s1.0/m15` | 33,060 | 48.1% | -0.0015 | 0.96 |
| S13 Structure reversal | no vwap filter | `t2.0/s1.0/m15` | 33,059 | 48.1% | -0.0015 | 0.96 |
| S13 Structure reversal | no vwap filter | `t0.5/s0.5/m30` | 23,818 | 48.7% | -0.0020 | 0.97 |
| S13 Structure reversal | no vwap filter | `t1.0/s0.75/m30` | 23,700 | 48.6% | -0.0024 | 0.96 |
| S13 Structure reversal | no vwap filter | `t2.0/s1.0/m30` | 23,679 | 48.6% | -0.0025 | 0.96 |
| S13 Structure reversal | no vwap filter | `t1.5/s1.0/m30` | 23,681 | 48.6% | -0.0025 | 0.96 |
| S13 Structure reversal | no vwap filter | `t0.5/s0.5/m-` | 5,954 | 49.0% | -0.0041 | 0.98 |
| S13 Structure reversal | no vwap filter | `t1.0/s0.75/m-` | 4,021 | 48.2% | -0.0105 | 0.95 |
| S13 Structure reversal | no vwap filter | `t2.0/s1.0/m-` | 3,573 | 48.3% | -0.0134 | 0.94 |
| S13 Structure reversal | no vwap filter | `t1.5/s1.0/m-` | 3,604 | 48.1% | -0.0166 | 0.92 |
| S13 Structure reversal | vwap confirmed | `t1.5/s1.0/m30` | 17,655 | 48.6% | +0.0003 | 1.01 |
| S13 Structure reversal | vwap confirmed | `t2.0/s1.0/m30` | 17,652 | 48.6% | +0.0003 | 1.01 |
| S13 Structure reversal | vwap confirmed | `t0.5/s0.5/m30` | 17,718 | 48.7% | +0.0001 | 1.00 |
| S13 Structure reversal | vwap confirmed | `t1.0/s0.75/m30` | 17,659 | 48.6% | -0.0000 | 1.00 |
| S13 Structure reversal | vwap confirmed | `t0.5/s0.5/m-` | 5,501 | 49.5% | -0.0001 | 1.00 |
| S13 Structure reversal | vwap confirmed | `t1.5/s1.0/m15` | 22,466 | 47.4% | -0.0002 | 0.99 |
| S13 Structure reversal | vwap confirmed | `t2.0/s1.0/m15` | 22,465 | 47.4% | -0.0002 | 0.99 |
| S13 Structure reversal | vwap confirmed | `t1.0/s0.75/m15` | 22,467 | 47.4% | -0.0003 | 0.99 |
| S13 Structure reversal | vwap confirmed | `t0.5/s0.5/m15` | 22,482 | 47.4% | -0.0004 | 0.99 |
| S13 Structure reversal | vwap confirmed | `t1.0/s0.75/m-` | 3,906 | 47.7% | -0.0015 | 0.99 |
| S13 Structure reversal | vwap confirmed | `t2.0/s1.0/m-` | 3,529 | 47.4% | -0.0105 | 0.95 |
| S13 Structure reversal | vwap confirmed | `t1.5/s1.0/m-` | 3,558 | 47.5% | -0.0112 | 0.95 |
| S14 Momentum continuation | adx20 aligned | `t1.0/s0.75/m-` | 4,004 | 48.4% | -0.0013 | 0.99 |
| S14 Momentum continuation | adx20 aligned | `t0.5/s0.5/m30` | 20,703 | 48.1% | -0.0018 | 0.97 |
| S14 Momentum continuation | adx20 aligned | `t1.5/s1.0/m30` | 20,541 | 48.1% | -0.0018 | 0.97 |
| S14 Momentum continuation | adx20 aligned | `t2.0/s1.0/m30` | 20,538 | 48.1% | -0.0019 | 0.97 |
| S14 Momentum continuation | adx20 aligned | `t1.0/s0.75/m30` | 20,550 | 48.1% | -0.0019 | 0.97 |
| S14 Momentum continuation | adx20 aligned | `t2.0/s1.0/m15` | 28,959 | 46.3% | -0.0019 | 0.95 |
| S14 Momentum continuation | adx20 aligned | `t1.5/s1.0/m15` | 28,961 | 46.3% | -0.0020 | 0.95 |
| S14 Momentum continuation | adx20 aligned | `t1.0/s0.75/m15` | 28,965 | 46.3% | -0.0021 | 0.95 |
| S14 Momentum continuation | adx20 aligned | `t0.5/s0.5/m15` | 29,012 | 46.3% | -0.0022 | 0.95 |
| S14 Momentum continuation | adx20 aligned | `t0.5/s0.5/m-` | 5,901 | 49.6% | -0.0027 | 0.98 |
| S14 Momentum continuation | adx20 aligned | `t2.0/s1.0/m-` | 3,544 | 48.4% | -0.0027 | 0.99 |
| S14 Momentum continuation | adx20 aligned | `t1.5/s1.0/m-` | 3,589 | 48.4% | -0.0031 | 0.98 |
| S14 Momentum continuation | adx25 aligned | `t1.5/s1.0/m-` | 3,543 | 48.9% | +0.0042 | 1.02 |
| S14 Momentum continuation | adx25 aligned | `t2.0/s1.0/m-` | 3,499 | 49.0% | +0.0036 | 1.02 |
| S14 Momentum continuation | adx25 aligned | `t1.0/s0.75/m-` | 3,928 | 48.7% | +0.0010 | 1.01 |
| S14 Momentum continuation | adx25 aligned | `t0.5/s0.5/m-` | 5,604 | 49.7% | -0.0001 | 1.00 |
| S14 Momentum continuation | adx25 aligned | `t1.5/s1.0/m30` | 15,651 | 47.6% | -0.0022 | 0.96 |
| S14 Momentum continuation | adx25 aligned | `t2.0/s1.0/m30` | 15,649 | 47.6% | -0.0024 | 0.96 |
| S14 Momentum continuation | adx25 aligned | `t0.5/s0.5/m30` | 15,767 | 47.6% | -0.0027 | 0.95 |
| S14 Momentum continuation | adx25 aligned | `t1.5/s1.0/m15` | 21,162 | 45.5% | -0.0030 | 0.93 |
| S14 Momentum continuation | adx25 aligned | `t1.0/s0.75/m30` | 15,657 | 47.6% | -0.0030 | 0.95 |
| S14 Momentum continuation | adx25 aligned | `t2.0/s1.0/m15` | 21,160 | 45.5% | -0.0030 | 0.93 |
| S14 Momentum continuation | adx25 aligned | `t1.0/s0.75/m15` | 21,166 | 45.5% | -0.0033 | 0.92 |
| S14 Momentum continuation | adx25 aligned | `t0.5/s0.5/m15` | 21,208 | 45.5% | -0.0035 | 0.92 |
| S14 Momentum continuation | adx25 unaligned | `t1.5/s1.0/m-` | 3,579 | 50.0% | +0.0145 | 1.07 |
| S14 Momentum continuation | adx25 unaligned | `t2.0/s1.0/m-` | 3,539 | 49.9% | +0.0128 | 1.07 |
| S14 Momentum continuation | adx25 unaligned | `t0.5/s0.5/m-` | 6,051 | 50.1% | +0.0034 | 1.02 |
| S14 Momentum continuation | adx25 unaligned | `t1.0/s0.75/m-` | 4,044 | 49.2% | +0.0028 | 1.01 |
| S14 Momentum continuation | adx25 unaligned | `t1.5/s1.0/m30` | 21,038 | 47.5% | -0.0031 | 0.95 |
| S14 Momentum continuation | adx25 unaligned | `t2.0/s1.0/m30` | 21,034 | 47.5% | -0.0032 | 0.94 |
| S14 Momentum continuation | adx25 unaligned | `t0.5/s0.5/m30` | 21,230 | 47.5% | -0.0033 | 0.94 |
| S14 Momentum continuation | adx25 unaligned | `t1.0/s0.75/m30` | 21,057 | 47.5% | -0.0035 | 0.94 |
| S14 Momentum continuation | adx25 unaligned | `t1.5/s1.0/m15` | 31,832 | 46.0% | -0.0037 | 0.91 |
| S14 Momentum continuation | adx25 unaligned | `t2.0/s1.0/m15` | 31,830 | 46.0% | -0.0038 | 0.91 |
| S14 Momentum continuation | adx25 unaligned | `t0.5/s0.5/m15` | 31,911 | 45.9% | -0.0040 | 0.91 |
| S14 Momentum continuation | adx25 unaligned | `t1.0/s0.75/m15` | 31,842 | 46.0% | -0.0040 | 0.91 |
| S14 Momentum continuation | adx30 aligned | `t1.0/s0.75/m-` | 3,788 | 49.8% | +0.0062 | 1.03 |
| S14 Momentum continuation | adx30 aligned | `t1.5/s1.0/m-` | 3,471 | 49.7% | +0.0057 | 1.03 |
| S14 Momentum continuation | adx30 aligned | `t2.0/s1.0/m-` | 3,435 | 49.7% | +0.0024 | 1.01 |
| S14 Momentum continuation | adx30 aligned | `t0.5/s0.5/m-` | 5,203 | 50.0% | +0.0014 | 1.01 |
| S14 Momentum continuation | adx30 aligned | `t1.5/s1.0/m30` | 11,319 | 46.3% | -0.0034 | 0.94 |
| S14 Momentum continuation | adx30 aligned | `t2.0/s1.0/m30` | 11,318 | 46.2% | -0.0037 | 0.94 |
| S14 Momentum continuation | adx30 aligned | `t1.0/s0.75/m30` | 11,327 | 46.2% | -0.0042 | 0.93 |
| S14 Momentum continuation | adx30 aligned | `t0.5/s0.5/m30` | 11,416 | 46.3% | -0.0043 | 0.93 |
| S14 Momentum continuation | adx30 aligned | `t1.5/s1.0/m15` | 14,770 | 44.4% | -0.0044 | 0.90 |
| S14 Momentum continuation | adx30 aligned | `t2.0/s1.0/m15` | 14,770 | 44.4% | -0.0044 | 0.90 |
| S14 Momentum continuation | adx30 aligned | `t1.0/s0.75/m15` | 14,774 | 44.4% | -0.0045 | 0.90 |
| S14 Momentum continuation | adx30 aligned | `t0.5/s0.5/m15` | 14,801 | 44.4% | -0.0046 | 0.90 |
| S15 Momentum exhaustion | 1.0atr ext | `t2.0/s1.0/m-` | 27 | 55.6% | +0.1456 | 1.70 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.0/s0.75/m-` | 28 | 53.6% | +0.1298 | 1.73 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.5/s1.0/m-` | 27 | 55.6% | +0.1085 | 1.52 |
| S15 Momentum exhaustion | 1.0atr ext | `t0.5/s0.5/m30` | 34 | 58.8% | +0.1019 | 1.77 |
| S15 Momentum exhaustion | 1.0atr ext | `t0.5/s0.5/m-` | 32 | 53.1% | +0.0907 | 1.55 |
| S15 Momentum exhaustion | 1.0atr ext | `t0.5/s0.5/m15` | 37 | 56.8% | +0.0840 | 2.01 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.0/s0.75/m30` | 32 | 56.2% | +0.0834 | 1.59 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.0/s0.75/m15` | 37 | 56.8% | +0.0720 | 1.87 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.5/s1.0/m15` | 37 | 56.8% | +0.0406 | 1.45 |
| S15 Momentum exhaustion | 1.0atr ext | `t2.0/s1.0/m15` | 37 | 56.8% | +0.0406 | 1.45 |
| S15 Momentum exhaustion | 1.0atr ext | `t1.5/s1.0/m30` | 32 | 53.1% | +0.0372 | 1.24 |
| S15 Momentum exhaustion | 1.0atr ext | `t2.0/s1.0/m30` | 32 | 53.1% | +0.0372 | 1.24 |
| S15 Momentum exhaustion | 1.5atr ext | `t0.5/s0.5/m-` | 1 | 100.0% | +0.5000 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t1.0/s0.75/m-` | 1 | 100.0% | +0.4919 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t1.5/s1.0/m-` | 1 | 100.0% | +0.4919 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t2.0/s1.0/m-` | 1 | 100.0% | +0.4919 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t0.5/s0.5/m30` | 1 | 100.0% | +0.3100 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t1.0/s0.75/m30` | 1 | 100.0% | +0.3100 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t1.5/s1.0/m30` | 1 | 100.0% | +0.3100 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t2.0/s1.0/m30` | 1 | 100.0% | +0.3100 | inf |
| S15 Momentum exhaustion | 1.5atr ext | `t0.5/s0.5/m15` | 2 | 50.0% | +0.0438 | 1.36 |
| S15 Momentum exhaustion | 1.5atr ext | `t1.0/s0.75/m15` | 2 | 50.0% | +0.0438 | 1.36 |
| S15 Momentum exhaustion | 1.5atr ext | `t1.5/s1.0/m15` | 2 | 50.0% | +0.0438 | 1.36 |
| S15 Momentum exhaustion | 1.5atr ext | `t2.0/s1.0/m15` | 2 | 50.0% | +0.0438 | 1.36 |
| S16 Confluence | 2+ levels | `t1.0/s0.75/m-` | 3,655 | 50.0% | +0.0125 | 1.06 |
| S16 Confluence | 2+ levels | `t2.0/s1.0/m-` | 3,432 | 50.4% | +0.0099 | 1.05 |
| S16 Confluence | 2+ levels | `t1.5/s1.0/m-` | 3,440 | 50.4% | +0.0082 | 1.04 |
| S16 Confluence | 2+ levels | `t0.5/s0.5/m-` | 5,172 | 50.1% | +0.0039 | 1.02 |
| S16 Confluence | 2+ levels | `t1.5/s1.0/m30` | 28,022 | 48.6% | -0.0017 | 0.97 |
| S16 Confluence | 2+ levels | `t0.5/s0.5/m15` | 48,959 | 48.1% | -0.0017 | 0.96 |
| S16 Confluence | 2+ levels | `t2.0/s1.0/m30` | 28,022 | 48.6% | -0.0017 | 0.97 |
| S16 Confluence | 2+ levels | `t0.5/s0.5/m30` | 28,116 | 48.6% | -0.0018 | 0.97 |
| S16 Confluence | 2+ levels | `t1.0/s0.75/m15` | 48,920 | 48.1% | -0.0018 | 0.96 |
| S16 Confluence | 2+ levels | `t1.0/s0.75/m30` | 28,025 | 48.6% | -0.0018 | 0.97 |
| S16 Confluence | 2+ levels | `t1.5/s1.0/m15` | 48,918 | 48.0% | -0.0018 | 0.96 |
| S16 Confluence | 2+ levels | `t2.0/s1.0/m15` | 48,918 | 48.0% | -0.0018 | 0.95 |
| S16 Confluence | 3+ levels | `t0.5/s0.5/m-` | 4,061 | 50.4% | +0.0030 | 1.02 |
| S16 Confluence | 3+ levels | `t1.5/s1.0/m30` | 19,571 | 48.8% | -0.0011 | 0.98 |
| S16 Confluence | 3+ levels | `t2.0/s1.0/m30` | 19,571 | 48.8% | -0.0011 | 0.98 |
| S16 Confluence | 3+ levels | `t1.0/s0.75/m30` | 19,571 | 48.8% | -0.0011 | 0.98 |
| S16 Confluence | 3+ levels | `t0.5/s0.5/m30` | 19,600 | 48.7% | -0.0016 | 0.97 |
| S16 Confluence | 3+ levels | `t1.5/s1.0/m15` | 32,683 | 47.9% | -0.0018 | 0.95 |
| S16 Confluence | 3+ levels | `t2.0/s1.0/m15` | 32,683 | 47.9% | -0.0019 | 0.95 |
| S16 Confluence | 3+ levels | `t1.0/s0.75/m15` | 32,683 | 47.9% | -0.0019 | 0.95 |
| S16 Confluence | 3+ levels | `t0.5/s0.5/m15` | 32,696 | 47.9% | -0.0020 | 0.95 |
| S16 Confluence | 3+ levels | `t1.0/s0.75/m-` | 3,291 | 48.8% | -0.0027 | 0.99 |
| S16 Confluence | 3+ levels | `t2.0/s1.0/m-` | 3,208 | 48.9% | -0.0056 | 0.97 |
| S16 Confluence | 3+ levels | `t1.5/s1.0/m-` | 3,210 | 48.9% | -0.0071 | 0.97 |
| S16 Confluence | 4+ levels | `t1.5/s1.0/m-` | 2,235 | 50.1% | +0.0098 | 1.05 |
| S16 Confluence | 4+ levels | `t2.0/s1.0/m-` | 2,234 | 50.1% | +0.0093 | 1.05 |
| S16 Confluence | 4+ levels | `t1.0/s0.75/m-` | 2,247 | 49.6% | +0.0078 | 1.04 |
| S16 Confluence | 4+ levels | `t0.5/s0.5/m-` | 2,474 | 51.0% | +0.0070 | 1.04 |
| S16 Confluence | 4+ levels | `t2.0/s1.0/m30` | 10,604 | 49.7% | +0.0026 | 1.05 |
| S16 Confluence | 4+ levels | `t1.5/s1.0/m30` | 10,604 | 49.7% | +0.0026 | 1.05 |
| S16 Confluence | 4+ levels | `t1.0/s0.75/m30` | 10,604 | 49.7% | +0.0025 | 1.05 |
| S16 Confluence | 4+ levels | `t0.5/s0.5/m30` | 10,609 | 49.7% | +0.0020 | 1.04 |
| S16 Confluence | 4+ levels | `t1.5/s1.0/m15` | 16,838 | 48.1% | -0.0009 | 0.97 |
| S16 Confluence | 4+ levels | `t1.0/s0.75/m15` | 16,838 | 48.1% | -0.0010 | 0.97 |
| S16 Confluence | 4+ levels | `t2.0/s1.0/m15` | 16,838 | 48.1% | -0.0010 | 0.97 |
| S16 Confluence | 4+ levels | `t0.5/s0.5/m15` | 16,840 | 48.1% | -0.0011 | 0.97 |
| S17 Expected-move | <100% used | `t2.0/s1.0/m-` | 3,330 | 50.5% | +0.0149 | 1.07 |
| S17 Expected-move | <100% used | `t1.5/s1.0/m-` | 3,330 | 50.5% | +0.0137 | 1.07 |
| S17 Expected-move | <100% used | `t1.0/s0.75/m-` | 3,636 | 49.7% | +0.0125 | 1.06 |
| S17 Expected-move | <100% used | `t0.5/s0.5/m-` | 5,552 | 50.7% | +0.0058 | 1.03 |
| S17 Expected-move | <100% used | `t1.0/s0.75/m30` | 31,523 | 48.4% | +0.0004 | 1.01 |
| S17 Expected-move | <100% used | `t2.0/s1.0/m30` | 31,508 | 48.4% | +0.0004 | 1.01 |
| S17 Expected-move | <100% used | `t1.5/s1.0/m30` | 31,508 | 48.4% | +0.0004 | 1.01 |
| S17 Expected-move | <100% used | `t0.5/s0.5/m30` | 31,656 | 48.3% | -0.0001 | 1.00 |
| S17 Expected-move | <100% used | `t2.0/s1.0/m15` | 54,827 | 47.8% | -0.0005 | 0.99 |
| S17 Expected-move | <100% used | `t1.0/s0.75/m15` | 54,834 | 47.8% | -0.0005 | 0.99 |
| S17 Expected-move | <100% used | `t1.5/s1.0/m15` | 54,827 | 47.8% | -0.0005 | 0.99 |
| S17 Expected-move | <100% used | `t0.5/s0.5/m15` | 54,879 | 47.8% | -0.0006 | 0.99 |
| S17 Expected-move | <125% used | `t2.0/s1.0/m-` | 3,482 | 50.3% | +0.0146 | 1.07 |
| S17 Expected-move | <125% used | `t1.5/s1.0/m-` | 3,482 | 50.4% | +0.0131 | 1.06 |
| S17 Expected-move | <125% used | `t1.0/s0.75/m-` | 3,885 | 49.6% | +0.0109 | 1.05 |
| S17 Expected-move | <125% used | `t0.5/s0.5/m-` | 6,007 | 50.8% | +0.0059 | 1.03 |
| S17 Expected-move | <125% used | `t2.0/s1.0/m30` | 33,983 | 48.4% | +0.0002 | 1.00 |
| S17 Expected-move | <125% used | `t1.5/s1.0/m30` | 33,983 | 48.4% | +0.0002 | 1.00 |
| S17 Expected-move | <125% used | `t1.0/s0.75/m30` | 34,008 | 48.4% | +0.0001 | 1.00 |
| S17 Expected-move | <125% used | `t0.5/s0.5/m30` | 34,180 | 48.3% | -0.0002 | 1.00 |
| S17 Expected-move | <125% used | `t2.0/s1.0/m15` | 59,168 | 48.0% | -0.0003 | 0.99 |
| S17 Expected-move | <125% used | `t1.5/s1.0/m15` | 59,168 | 48.0% | -0.0003 | 0.99 |
| S17 Expected-move | <125% used | `t1.0/s0.75/m15` | 59,182 | 48.0% | -0.0003 | 0.99 |
| S17 Expected-move | <125% used | `t0.5/s0.5/m15` | 59,249 | 47.9% | -0.0005 | 0.99 |
| S17 Expected-move | <50% used | `t2.0/s1.0/m-` | 3,300 | 50.5% | +0.0162 | 1.08 |
| S17 Expected-move | <50% used | `t1.0/s0.75/m-` | 3,300 | 50.1% | +0.0149 | 1.07 |
| S17 Expected-move | <50% used | `t1.5/s1.0/m-` | 3,300 | 50.6% | +0.0149 | 1.07 |
| S17 Expected-move | <50% used | `t0.5/s0.5/m-` | 3,300 | 50.8% | +0.0100 | 1.05 |
| S17 Expected-move | <50% used | `t1.5/s1.0/m30` | 15,518 | 48.9% | -0.0001 | 1.00 |
| S17 Expected-move | <50% used | `t2.0/s1.0/m30` | 15,518 | 48.9% | -0.0001 | 1.00 |
| S17 Expected-move | <50% used | `t1.0/s0.75/m30` | 15,518 | 48.9% | -0.0002 | 1.00 |
| S17 Expected-move | <50% used | `t0.5/s0.5/m30` | 15,518 | 48.8% | -0.0002 | 1.00 |
| S17 Expected-move | <50% used | `t1.5/s1.0/m15` | 26,516 | 48.0% | -0.0008 | 0.98 |
| S17 Expected-move | <50% used | `t2.0/s1.0/m15` | 26,516 | 48.0% | -0.0008 | 0.98 |
| S17 Expected-move | <50% used | `t1.0/s0.75/m15` | 26,516 | 48.0% | -0.0008 | 0.98 |
| S17 Expected-move | <50% used | `t0.5/s0.5/m15` | 26,516 | 48.0% | -0.0009 | 0.98 |
| S17 Expected-move | <75% used | `t2.0/s1.0/m-` | 3,327 | 50.5% | +0.0155 | 1.07 |
| S17 Expected-move | <75% used | `t1.0/s0.75/m-` | 3,327 | 50.1% | +0.0153 | 1.07 |
| S17 Expected-move | <75% used | `t1.5/s1.0/m-` | 3,327 | 50.6% | +0.0143 | 1.07 |
| S17 Expected-move | <75% used | `t0.5/s0.5/m-` | 4,579 | 50.8% | +0.0077 | 1.04 |
| S17 Expected-move | <75% used | `t1.0/s0.75/m30` | 25,969 | 48.4% | +0.0002 | 1.00 |
| S17 Expected-move | <75% used | `t1.5/s1.0/m30` | 25,969 | 48.4% | +0.0001 | 1.00 |
| S17 Expected-move | <75% used | `t2.0/s1.0/m30` | 25,969 | 48.4% | +0.0001 | 1.00 |
| S17 Expected-move | <75% used | `t0.5/s0.5/m30` | 26,055 | 48.3% | +0.0000 | 1.00 |
| S17 Expected-move | <75% used | `t1.0/s0.75/m15` | 44,979 | 47.7% | -0.0005 | 0.99 |
| S17 Expected-move | <75% used | `t2.0/s1.0/m15` | 44,979 | 47.7% | -0.0005 | 0.99 |
| S17 Expected-move | <75% used | `t1.5/s1.0/m15` | 44,979 | 47.7% | -0.0005 | 0.99 |
| S17 Expected-move | <75% used | `t0.5/s0.5/m15` | 44,998 | 47.7% | -0.0005 | 0.99 |
| S18 Time-of-day | AFTERNOON | `t0.5/s0.5/m15` | 24,039 | 47.6% | -0.0020 | 0.95 |
| S18 Time-of-day | AFTERNOON | `t2.0/s1.0/m15` | 23,978 | 47.6% | -0.0021 | 0.95 |
| S18 Time-of-day | AFTERNOON | `t1.0/s0.75/m15` | 23,987 | 47.6% | -0.0022 | 0.94 |
| S18 Time-of-day | AFTERNOON | `t1.5/s1.0/m15` | 23,979 | 47.6% | -0.0023 | 0.94 |
| S18 Time-of-day | AFTERNOON | `t0.5/s0.5/m30` | 13,386 | 47.7% | -0.0029 | 0.95 |
| S18 Time-of-day | AFTERNOON | `t1.5/s1.0/m30` | 13,242 | 47.8% | -0.0030 | 0.95 |
| S18 Time-of-day | AFTERNOON | `t2.0/s1.0/m30` | 13,241 | 47.8% | -0.0031 | 0.94 |
| S18 Time-of-day | AFTERNOON | `t1.0/s0.75/m30` | 13,265 | 47.8% | -0.0031 | 0.94 |
| S18 Time-of-day | AFTERNOON | `t0.5/s0.5/m-` | 4,051 | 47.3% | -0.0104 | 0.92 |
| S18 Time-of-day | AFTERNOON | `t1.0/s0.75/m-` | 3,461 | 46.9% | -0.0127 | 0.91 |
| S18 Time-of-day | AFTERNOON | `t2.0/s1.0/m-` | 3,350 | 47.2% | -0.0129 | 0.91 |
| S18 Time-of-day | AFTERNOON | `t1.5/s1.0/m-` | 3,355 | 47.2% | -0.0133 | 0.90 |
| S18 Time-of-day | FINAL_30 | `t1.5/s1.0/m30` | 1,596 | 50.8% | +0.0086 | 1.13 |
| S18 Time-of-day | FINAL_30 | `t1.5/s1.0/m-` | 1,596 | 50.8% | +0.0086 | 1.13 |
| S18 Time-of-day | FINAL_30 | `t2.0/s1.0/m30` | 1,596 | 50.8% | +0.0079 | 1.12 |
| S18 Time-of-day | FINAL_30 | `t2.0/s1.0/m-` | 1,596 | 50.8% | +0.0079 | 1.12 |
| S18 Time-of-day | FINAL_30 | `t1.0/s0.75/m30` | 1,596 | 50.8% | +0.0070 | 1.10 |
| S18 Time-of-day | FINAL_30 | `t1.0/s0.75/m-` | 1,596 | 50.8% | +0.0070 | 1.10 |
| S18 Time-of-day | FINAL_30 | `t0.5/s0.5/m30` | 1,596 | 50.6% | +0.0038 | 1.05 |
| S18 Time-of-day | FINAL_30 | `t0.5/s0.5/m-` | 1,596 | 50.6% | +0.0038 | 1.05 |
| S18 Time-of-day | FINAL_30 | `t1.5/s1.0/m15` | 1,596 | 50.0% | +0.0021 | 1.05 |
| S18 Time-of-day | FINAL_30 | `t1.0/s0.75/m15` | 1,596 | 50.0% | +0.0017 | 1.04 |
| S18 Time-of-day | FINAL_30 | `t0.5/s0.5/m15` | 1,596 | 49.9% | +0.0013 | 1.03 |
| S18 Time-of-day | FINAL_30 | `t2.0/s1.0/m15` | 1,596 | 49.9% | +0.0011 | 1.02 |
| S18 Time-of-day | MIDDAY | `t2.0/s1.0/m-` | 3,361 | 51.0% | +0.0122 | 1.08 |
| S18 Time-of-day | MIDDAY | `t1.5/s1.0/m-` | 3,362 | 51.0% | +0.0109 | 1.07 |
| S18 Time-of-day | MIDDAY | `t1.0/s0.75/m-` | 3,420 | 50.6% | +0.0100 | 1.06 |
| S18 Time-of-day | MIDDAY | `t0.5/s0.5/m-` | 3,894 | 50.5% | +0.0057 | 1.04 |
| S18 Time-of-day | MIDDAY | `t1.5/s1.0/m30` | 13,310 | 48.5% | -0.0016 | 0.97 |
| S18 Time-of-day | MIDDAY | `t0.5/s0.5/m30` | 13,396 | 48.4% | -0.0016 | 0.97 |
| S18 Time-of-day | MIDDAY | `t2.0/s1.0/m30` | 13,310 | 48.5% | -0.0017 | 0.97 |
| S18 Time-of-day | MIDDAY | `t1.0/s0.75/m30` | 13,318 | 48.5% | -0.0017 | 0.97 |
| S18 Time-of-day | MIDDAY | `t0.5/s0.5/m15` | 23,974 | 47.1% | -0.0018 | 0.95 |
| S18 Time-of-day | MIDDAY | `t1.0/s0.75/m15` | 23,944 | 47.0% | -0.0020 | 0.94 |
| S18 Time-of-day | MIDDAY | `t1.5/s1.0/m15` | 23,942 | 47.0% | -0.0021 | 0.94 |
| S18 Time-of-day | MIDDAY | `t2.0/s1.0/m15` | 23,942 | 47.0% | -0.0021 | 0.94 |
| S18 Time-of-day | MIDMORNING | `t1.0/s0.75/m15` | 13,158 | 49.1% | -0.0014 | 0.97 |
| S18 Time-of-day | MIDMORNING | `t1.5/s1.0/m15` | 13,157 | 49.1% | -0.0016 | 0.96 |
| S18 Time-of-day | MIDMORNING | `t1.0/s0.75/m-` | 3,383 | 49.7% | -0.0017 | 0.99 |
| S18 Time-of-day | MIDMORNING | `t2.0/s1.0/m15` | 13,157 | 49.1% | -0.0017 | 0.96 |
| S18 Time-of-day | MIDMORNING | `t0.5/s0.5/m15` | 13,170 | 49.0% | -0.0022 | 0.95 |
| S18 Time-of-day | MIDMORNING | `t0.5/s0.5/m30` | 6,782 | 48.7% | -0.0022 | 0.97 |
| S18 Time-of-day | MIDMORNING | `t1.0/s0.75/m30` | 6,679 | 48.6% | -0.0027 | 0.96 |
| S18 Time-of-day | MIDMORNING | `t1.5/s1.0/m30` | 6,670 | 48.6% | -0.0028 | 0.96 |
| S18 Time-of-day | MIDMORNING | `t2.0/s1.0/m30` | 6,669 | 48.6% | -0.0030 | 0.95 |
| S18 Time-of-day | MIDMORNING | `t1.5/s1.0/m-` | 3,349 | 50.0% | -0.0045 | 0.98 |
| S18 Time-of-day | MIDMORNING | `t2.0/s1.0/m-` | 3,349 | 49.9% | -0.0049 | 0.97 |
| S18 Time-of-day | MIDMORNING | `t0.5/s0.5/m-` | 3,646 | 50.2% | -0.0050 | 0.97 |
| S18 Time-of-day | MORNING | `t1.5/s1.0/m15` | 6,663 | 47.1% | -0.0090 | 0.84 |
| S18 Time-of-day | MORNING | `t2.0/s1.0/m15` | 6,663 | 47.1% | -0.0090 | 0.84 |
| S18 Time-of-day | MORNING | `t1.0/s0.75/m15` | 6,666 | 47.1% | -0.0093 | 0.84 |
| S18 Time-of-day | MORNING | `t0.5/s0.5/m15` | 6,691 | 47.0% | -0.0094 | 0.83 |
| S18 Time-of-day | MORNING | `t0.5/s0.5/m30` | 3,452 | 46.9% | -0.0121 | 0.85 |
| S18 Time-of-day | MORNING | `t1.5/s1.0/m30` | 3,337 | 46.9% | -0.0136 | 0.83 |
| S18 Time-of-day | MORNING | `t2.0/s1.0/m30` | 3,337 | 46.9% | -0.0136 | 0.83 |
| S18 Time-of-day | MORNING | `t1.0/s0.75/m30` | 3,348 | 46.9% | -0.0138 | 0.83 |
| S18 Time-of-day | MORNING | `t0.5/s0.5/m-` | 3,452 | 48.0% | -0.0145 | 0.92 |
| S18 Time-of-day | MORNING | `t2.0/s1.0/m-` | 3,337 | 47.8% | -0.0146 | 0.93 |
| S18 Time-of-day | MORNING | `t1.5/s1.0/m-` | 3,337 | 47.8% | -0.0172 | 0.92 |
| S18 Time-of-day | MORNING | `t1.0/s0.75/m-` | 3,348 | 47.1% | -0.0200 | 0.90 |
| S18 Time-of-day | OPEN | `t1.0/s0.75/m-` | 3,345 | 50.0% | +0.0130 | 1.06 |
| S18 Time-of-day | OPEN | `t2.0/s1.0/m-` | 3,338 | 50.4% | +0.0129 | 1.06 |
| S18 Time-of-day | OPEN | `t1.5/s1.0/m-` | 3,339 | 50.5% | +0.0117 | 1.06 |
| S18 Time-of-day | OPEN | `t0.5/s0.5/m-` | 3,439 | 50.9% | +0.0083 | 1.04 |
| S18 Time-of-day | OPEN | `t0.5/s0.5/m15` | 6,620 | 50.8% | +0.0001 | 1.00 |
| S18 Time-of-day | OPEN | `t2.0/s1.0/m15` | 6,611 | 50.8% | -0.0002 | 1.00 |
| S18 Time-of-day | OPEN | `t1.5/s1.0/m15` | 6,611 | 50.8% | -0.0003 | 1.00 |
| S18 Time-of-day | OPEN | `t1.0/s0.75/m15` | 6,611 | 50.8% | -0.0003 | 0.99 |
| S18 Time-of-day | OPEN | `t1.5/s1.0/m30` | 3,339 | 49.9% | -0.0013 | 0.99 |
| S18 Time-of-day | OPEN | `t2.0/s1.0/m30` | 3,338 | 49.9% | -0.0013 | 0.98 |
| S18 Time-of-day | OPEN | `t0.5/s0.5/m30` | 3,439 | 49.8% | -0.0014 | 0.98 |
| S18 Time-of-day | OPEN | `t1.0/s0.75/m30` | 3,345 | 49.8% | -0.0018 | 0.98 |
| S19 MTF breakout | 2/4 agree | `t1.0/s0.75/m-` | 4,146 | 49.5% | +0.0014 | 1.01 |
| S19 MTF breakout | 2/4 agree | `t2.0/s1.0/m-` | 3,584 | 49.9% | +0.0009 | 1.00 |
| S19 MTF breakout | 2/4 agree | `t1.5/s1.0/m30` | 34,538 | 48.8% | -0.0004 | 0.99 |
| S19 MTF breakout | 2/4 agree | `t2.0/s1.0/m30` | 34,534 | 48.8% | -0.0004 | 0.99 |
| S19 MTF breakout | 2/4 agree | `t1.0/s0.75/m15` | 60,049 | 47.7% | -0.0007 | 0.98 |
| S19 MTF breakout | 2/4 agree | `t1.5/s1.0/m15` | 60,029 | 47.7% | -0.0007 | 0.98 |
| S19 MTF breakout | 2/4 agree | `t1.0/s0.75/m30` | 34,572 | 48.8% | -0.0008 | 0.99 |
| S19 MTF breakout | 2/4 agree | `t2.0/s1.0/m15` | 60,029 | 47.7% | -0.0008 | 0.98 |
| S19 MTF breakout | 2/4 agree | `t0.5/s0.5/m15` | 60,150 | 47.7% | -0.0011 | 0.97 |
| S19 MTF breakout | 2/4 agree | `t0.5/s0.5/m30` | 34,833 | 48.8% | -0.0013 | 0.98 |
| S19 MTF breakout | 2/4 agree | `t1.5/s1.0/m-` | 3,632 | 49.7% | -0.0013 | 0.99 |
| S19 MTF breakout | 2/4 agree | `t0.5/s0.5/m-` | 6,431 | 49.9% | -0.0024 | 0.99 |
| S19 MTF breakout | 3/4 agree | `t2.0/s1.0/m-` | 3,496 | 50.5% | +0.0121 | 1.07 |
| S19 MTF breakout | 3/4 agree | `t1.5/s1.0/m-` | 3,532 | 50.5% | +0.0109 | 1.06 |
| S19 MTF breakout | 3/4 agree | `t1.0/s0.75/m-` | 3,913 | 50.4% | +0.0099 | 1.05 |
| S19 MTF breakout | 3/4 agree | `t0.5/s0.5/m-` | 5,555 | 51.2% | +0.0080 | 1.05 |
| S19 MTF breakout | 3/4 agree | `t2.0/s1.0/m30` | 24,299 | 48.9% | +0.0002 | 1.00 |
| S19 MTF breakout | 3/4 agree | `t1.5/s1.0/m30` | 24,301 | 48.9% | +0.0001 | 1.00 |
| S19 MTF breakout | 3/4 agree | `t1.0/s0.75/m30` | 24,314 | 48.8% | -0.0000 | 1.00 |
| S19 MTF breakout | 3/4 agree | `t0.5/s0.5/m30` | 24,462 | 48.8% | -0.0003 | 0.99 |
| S19 MTF breakout | 3/4 agree | `t1.5/s1.0/m15` | 37,145 | 47.4% | -0.0008 | 0.98 |
| S19 MTF breakout | 3/4 agree | `t2.0/s1.0/m15` | 37,144 | 47.4% | -0.0009 | 0.98 |
| S19 MTF breakout | 3/4 agree | `t0.5/s0.5/m15` | 37,202 | 47.4% | -0.0009 | 0.98 |
| S19 MTF breakout | 3/4 agree | `t1.0/s0.75/m15` | 37,155 | 47.4% | -0.0010 | 0.98 |
| S19 MTF breakout | 4/4 agree | `t2.0/s1.0/m-` | 2,361 | 52.9% | +0.0217 | 1.16 |
| S19 MTF breakout | 4/4 agree | `t1.5/s1.0/m-` | 2,370 | 53.0% | +0.0206 | 1.16 |
| S19 MTF breakout | 4/4 agree | `t1.0/s0.75/m-` | 2,416 | 52.7% | +0.0203 | 1.15 |
| S19 MTF breakout | 4/4 agree | `t0.5/s0.5/m-` | 2,763 | 51.9% | +0.0109 | 1.08 |
| S19 MTF breakout | 4/4 agree | `t1.5/s1.0/m30` | 6,721 | 47.9% | +0.0002 | 1.00 |
| S19 MTF breakout | 4/4 agree | `t2.0/s1.0/m30` | 6,719 | 47.8% | -0.0003 | 0.99 |
| S19 MTF breakout | 4/4 agree | `t1.0/s0.75/m30` | 6,727 | 47.9% | -0.0004 | 0.99 |
| S19 MTF breakout | 4/4 agree | `t0.5/s0.5/m30` | 6,761 | 47.7% | -0.0008 | 0.98 |
| S19 MTF breakout | 4/4 agree | `t1.5/s1.0/m15` | 9,274 | 46.1% | -0.0013 | 0.96 |
| S19 MTF breakout | 4/4 agree | `t2.0/s1.0/m15` | 9,274 | 46.1% | -0.0018 | 0.95 |
| S19 MTF breakout | 4/4 agree | `t1.0/s0.75/m15` | 9,280 | 46.0% | -0.0019 | 0.95 |
| S19 MTF breakout | 4/4 agree | `t0.5/s0.5/m15` | 9,294 | 46.0% | -0.0021 | 0.94 |
| S2 ORB immediate | or15 | `t0.5/s0.5/m-` | 1,506 | 50.7% | +0.0011 | 1.01 |
| S2 ORB immediate | or15 | `t1.0/s0.75/m-` | 1,506 | 49.1% | +0.0002 | 1.00 |
| S2 ORB immediate | or15 | `t1.5/s1.0/m-` | 1,506 | 49.6% | -0.0020 | 0.99 |
| S2 ORB immediate | or15 | `t2.0/s1.0/m-` | 1,506 | 49.5% | -0.0048 | 0.98 |
| S2 ORB immediate | or15 | `t0.5/s0.5/m30` | 1,506 | 50.6% | -0.0063 | 0.93 |
| S2 ORB immediate | or15 | `t1.0/s0.75/m30` | 1,506 | 50.5% | -0.0066 | 0.92 |
| S2 ORB immediate | or15 | `t1.5/s1.0/m30` | 1,506 | 50.5% | -0.0075 | 0.91 |
| S2 ORB immediate | or15 | `t2.0/s1.0/m30` | 1,506 | 50.5% | -0.0075 | 0.91 |
| S2 ORB immediate | or15 | `t1.0/s0.75/m15` | 1,506 | 48.0% | -0.0095 | 0.86 |
| S2 ORB immediate | or15 | `t0.5/s0.5/m15` | 1,506 | 47.9% | -0.0096 | 0.86 |
| S2 ORB immediate | or15 | `t1.5/s1.0/m15` | 1,506 | 48.0% | -0.0099 | 0.85 |
| S2 ORB immediate | or15 | `t2.0/s1.0/m15` | 1,506 | 48.0% | -0.0099 | 0.85 |
| S2 ORB immediate | or30 | `t2.0/s1.0/m-` | 1,472 | 48.0% | +0.0027 | 1.01 |
| S2 ORB immediate | or30 | `t1.5/s1.0/m-` | 1,472 | 48.0% | +0.0017 | 1.01 |
| S2 ORB immediate | or30 | `t0.5/s0.5/m30` | 1,472 | 49.0% | +0.0014 | 1.02 |
| S2 ORB immediate | or30 | `t2.0/s1.0/m30` | 1,472 | 49.0% | -0.0002 | 1.00 |
| S2 ORB immediate | or30 | `t1.5/s1.0/m30` | 1,472 | 49.0% | -0.0003 | 1.00 |
| S2 ORB immediate | or30 | `t1.0/s0.75/m30` | 1,472 | 49.0% | -0.0014 | 0.98 |
| S2 ORB immediate | or30 | `t0.5/s0.5/m-` | 1,472 | 49.4% | -0.0027 | 0.99 |
| S2 ORB immediate | or30 | `t1.0/s0.75/m15` | 1,472 | 48.0% | -0.0037 | 0.94 |
| S2 ORB immediate | or30 | `t0.5/s0.5/m15` | 1,472 | 47.8% | -0.0037 | 0.94 |
| S2 ORB immediate | or30 | `t1.5/s1.0/m15` | 1,472 | 48.0% | -0.0040 | 0.93 |
| S2 ORB immediate | or30 | `t2.0/s1.0/m15` | 1,472 | 48.0% | -0.0040 | 0.93 |
| S2 ORB immediate | or30 | `t1.0/s0.75/m-` | 1,472 | 47.6% | -0.0044 | 0.98 |
| S2 ORB immediate | or5 | `t1.0/s0.75/m-` | 1,565 | 50.5% | +0.0251 | 1.11 |
| S2 ORB immediate | or5 | `t2.0/s1.0/m-` | 1,565 | 50.8% | +0.0245 | 1.11 |
| S2 ORB immediate | or5 | `t1.5/s1.0/m-` | 1,565 | 50.9% | +0.0226 | 1.10 |
| S2 ORB immediate | or5 | `t0.5/s0.5/m-` | 1,565 | 51.1% | +0.0116 | 1.06 |
| S2 ORB immediate | or5 | `t0.5/s0.5/m30` | 1,565 | 50.0% | -0.0038 | 0.96 |
| S2 ORB immediate | or5 | `t1.0/s0.75/m30` | 1,565 | 49.9% | -0.0045 | 0.95 |
| S2 ORB immediate | or5 | `t1.5/s1.0/m30` | 1,565 | 49.9% | -0.0050 | 0.95 |
| S2 ORB immediate | or5 | `t2.0/s1.0/m30` | 1,565 | 49.9% | -0.0050 | 0.95 |
| S2 ORB immediate | or5 | `t1.0/s0.75/m15` | 1,565 | 48.8% | -0.0063 | 0.91 |
| S2 ORB immediate | or5 | `t1.5/s1.0/m15` | 1,565 | 48.8% | -0.0066 | 0.90 |
| S2 ORB immediate | or5 | `t2.0/s1.0/m15` | 1,565 | 48.8% | -0.0066 | 0.90 |
| S2 ORB immediate | or5 | `t0.5/s0.5/m15` | 1,565 | 48.8% | -0.0067 | 0.90 |
| S21 Gap continuation | gap>=0.25% | `t1.5/s1.0/m-` | 1,956 | 52.9% | +0.0315 | 1.15 |
| S21 Gap continuation | gap>=0.25% | `t2.0/s1.0/m-` | 1,936 | 52.4% | +0.0312 | 1.15 |
| S21 Gap continuation | gap>=0.25% | `t1.0/s0.75/m-` | 2,144 | 51.6% | +0.0267 | 1.13 |
| S21 Gap continuation | gap>=0.25% | `t0.5/s0.5/m-` | 3,112 | 52.5% | +0.0195 | 1.11 |
| S21 Gap continuation | gap>=0.25% | `t1.5/s1.0/m30` | 13,342 | 50.5% | +0.0039 | 1.07 |
| S21 Gap continuation | gap>=0.25% | `t2.0/s1.0/m30` | 13,340 | 50.5% | +0.0037 | 1.07 |
| S21 Gap continuation | gap>=0.25% | `t1.0/s0.75/m30` | 13,350 | 50.5% | +0.0035 | 1.06 |
| S21 Gap continuation | gap>=0.25% | `t0.5/s0.5/m30` | 13,441 | 50.5% | +0.0030 | 1.05 |
| S21 Gap continuation | gap>=0.25% | `t1.5/s1.0/m15` | 21,842 | 49.7% | +0.0016 | 1.04 |
| S21 Gap continuation | gap>=0.25% | `t2.0/s1.0/m15` | 21,841 | 49.7% | +0.0016 | 1.04 |
| S21 Gap continuation | gap>=0.25% | `t1.0/s0.75/m15` | 21,847 | 49.7% | +0.0014 | 1.03 |
| S21 Gap continuation | gap>=0.25% | `t0.5/s0.5/m15` | 21,883 | 49.7% | +0.0010 | 1.02 |
| S21 Gap continuation | gap>=0.5% | `t2.0/s1.0/m-` | 1,058 | 56.8% | +0.0620 | 1.30 |
| S21 Gap continuation | gap>=0.5% | `t1.5/s1.0/m-` | 1,067 | 57.2% | +0.0617 | 1.30 |
| S21 Gap continuation | gap>=0.5% | `t1.0/s0.75/m-` | 1,184 | 55.2% | +0.0512 | 1.25 |
| S21 Gap continuation | gap>=0.5% | `t0.5/s0.5/m-` | 1,752 | 55.1% | +0.0356 | 1.21 |
| S21 Gap continuation | gap>=0.5% | `t1.0/s0.75/m30` | 7,460 | 51.7% | +0.0060 | 1.11 |
| S21 Gap continuation | gap>=0.5% | `t1.5/s1.0/m30` | 7,455 | 51.8% | +0.0060 | 1.11 |
| S21 Gap continuation | gap>=0.5% | `t2.0/s1.0/m30` | 7,454 | 51.8% | +0.0056 | 1.10 |
| S21 Gap continuation | gap>=0.5% | `t0.5/s0.5/m30` | 7,514 | 51.9% | +0.0048 | 1.08 |
| S21 Gap continuation | gap>=0.5% | `t1.5/s1.0/m15` | 12,280 | 50.2% | +0.0020 | 1.05 |
| S21 Gap continuation | gap>=0.5% | `t2.0/s1.0/m15` | 12,280 | 50.2% | +0.0020 | 1.05 |
| S21 Gap continuation | gap>=0.5% | `t1.0/s0.75/m15` | 12,281 | 50.2% | +0.0019 | 1.05 |
| S21 Gap continuation | gap>=0.5% | `t0.5/s0.5/m15` | 12,304 | 50.2% | +0.0013 | 1.03 |
| S21 Gap continuation | gap>=1.0% | `t2.0/s1.0/m-` | 388 | 58.8% | +0.0532 | 1.23 |
| S21 Gap continuation | gap>=1.0% | `t1.5/s1.0/m-` | 391 | 59.3% | +0.0518 | 1.23 |
| S21 Gap continuation | gap>=1.0% | `t1.0/s0.75/m-` | 437 | 56.5% | +0.0427 | 1.19 |
| S21 Gap continuation | gap>=1.0% | `t0.5/s0.5/m-` | 659 | 55.7% | +0.0292 | 1.16 |
| S21 Gap continuation | gap>=1.0% | `t1.0/s0.75/m30` | 2,722 | 52.1% | +0.0028 | 1.05 |
| S21 Gap continuation | gap>=1.0% | `t1.5/s1.0/m30` | 2,720 | 52.2% | +0.0027 | 1.05 |
| S21 Gap continuation | gap>=1.0% | `t2.0/s1.0/m30` | 2,720 | 52.2% | +0.0027 | 1.05 |
| S21 Gap continuation | gap>=1.0% | `t0.5/s0.5/m30` | 2,748 | 52.1% | +0.0008 | 1.01 |
| S21 Gap continuation | gap>=1.0% | `t1.5/s1.0/m15` | 4,487 | 50.5% | -0.0004 | 0.99 |
| S21 Gap continuation | gap>=1.0% | `t2.0/s1.0/m15` | 4,487 | 50.5% | -0.0004 | 0.99 |
| S21 Gap continuation | gap>=1.0% | `t1.0/s0.75/m15` | 4,487 | 50.5% | -0.0005 | 0.99 |
| S21 Gap continuation | gap>=1.0% | `t0.5/s0.5/m15` | 4,496 | 50.4% | -0.0014 | 0.97 |
| S22 Gap fade | gap>=0.25% | `t0.5/s0.5/m30` | 12,561 | 48.4% | +0.0006 | 1.01 |
| S22 Gap fade | gap>=0.25% | `t2.0/s1.0/m30` | 12,469 | 48.4% | +0.0006 | 1.01 |
| S22 Gap fade | gap>=0.25% | `t1.5/s1.0/m30` | 12,469 | 48.4% | +0.0005 | 1.01 |
| S22 Gap fade | gap>=0.25% | `t1.0/s0.75/m30` | 12,477 | 48.3% | +0.0003 | 1.00 |
| S22 Gap fade | gap>=0.25% | `t0.5/s0.5/m15` | 20,350 | 48.1% | -0.0001 | 1.00 |
| S22 Gap fade | gap>=0.25% | `t1.0/s0.75/m15` | 20,321 | 48.0% | -0.0002 | 0.99 |
| S22 Gap fade | gap>=0.25% | `t2.0/s1.0/m15` | 20,319 | 48.0% | -0.0003 | 0.99 |
| S22 Gap fade | gap>=0.25% | `t1.5/s1.0/m15` | 20,319 | 48.0% | -0.0003 | 0.99 |
| S22 Gap fade | gap>=0.25% | `t0.5/s0.5/m-` | 3,124 | 48.0% | -0.0081 | 0.96 |
| S22 Gap fade | gap>=0.25% | `t1.0/s0.75/m-` | 2,159 | 46.4% | -0.0160 | 0.93 |
| S22 Gap fade | gap>=0.25% | `t1.5/s1.0/m-` | 1,967 | 46.9% | -0.0218 | 0.91 |
| S22 Gap fade | gap>=0.25% | `t2.0/s1.0/m-` | 1,938 | 46.7% | -0.0235 | 0.90 |
| S22 Gap fade | gap>=0.5% | `t2.0/s1.0/m15` | 10,814 | 48.1% | -0.0013 | 0.97 |
| S22 Gap fade | gap>=0.5% | `t1.0/s0.75/m15` | 10,815 | 48.1% | -0.0014 | 0.97 |
| S22 Gap fade | gap>=0.5% | `t1.5/s1.0/m15` | 10,814 | 48.1% | -0.0014 | 0.97 |
| S22 Gap fade | gap>=0.5% | `t0.5/s0.5/m15` | 10,836 | 48.1% | -0.0014 | 0.97 |
| S22 Gap fade | gap>=0.5% | `t2.0/s1.0/m30` | 6,653 | 48.0% | -0.0022 | 0.97 |
| S22 Gap fade | gap>=0.5% | `t1.5/s1.0/m30` | 6,653 | 48.0% | -0.0024 | 0.96 |
| S22 Gap fade | gap>=0.5% | `t0.5/s0.5/m30` | 6,719 | 47.9% | -0.0027 | 0.96 |
| S22 Gap fade | gap>=0.5% | `t1.0/s0.75/m30` | 6,658 | 48.0% | -0.0027 | 0.96 |
| S22 Gap fade | gap>=0.5% | `t0.5/s0.5/m-` | 1,740 | 45.7% | -0.0295 | 0.86 |
| S22 Gap fade | gap>=0.5% | `t1.0/s0.75/m-` | 1,194 | 42.4% | -0.0459 | 0.82 |
| S22 Gap fade | gap>=0.5% | `t1.5/s1.0/m-` | 1,078 | 42.3% | -0.0570 | 0.79 |
| S22 Gap fade | gap>=0.5% | `t2.0/s1.0/m-` | 1,065 | 42.0% | -0.0601 | 0.78 |
| S22 Gap fade | gap>=1.0% | `t1.0/s0.75/m15` | 3,878 | 48.1% | -0.0026 | 0.95 |
| S22 Gap fade | gap>=1.0% | `t2.0/s1.0/m15` | 3,877 | 48.1% | -0.0027 | 0.95 |
| S22 Gap fade | gap>=1.0% | `t1.5/s1.0/m15` | 3,877 | 48.1% | -0.0028 | 0.94 |
| S22 Gap fade | gap>=1.0% | `t0.5/s0.5/m15` | 3,892 | 48.1% | -0.0031 | 0.94 |
| S22 Gap fade | gap>=1.0% | `t2.0/s1.0/m30` | 2,386 | 47.4% | -0.0053 | 0.93 |
| S22 Gap fade | gap>=1.0% | `t1.5/s1.0/m30` | 2,386 | 47.4% | -0.0057 | 0.92 |
| S22 Gap fade | gap>=1.0% | `t1.0/s0.75/m30` | 2,388 | 47.4% | -0.0058 | 0.92 |
| S22 Gap fade | gap>=1.0% | `t0.5/s0.5/m30` | 2,427 | 47.4% | -0.0064 | 0.92 |
| S22 Gap fade | gap>=1.0% | `t0.5/s0.5/m-` | 690 | 43.2% | -0.0477 | 0.79 |
| S22 Gap fade | gap>=1.0% | `t1.0/s0.75/m-` | 449 | 38.5% | -0.0644 | 0.77 |
| S22 Gap fade | gap>=1.0% | `t1.5/s1.0/m-` | 391 | 38.1% | -0.0743 | 0.75 |
| S22 Gap fade | gap>=1.0% | `t2.0/s1.0/m-` | 386 | 38.1% | -0.0793 | 0.73 |
| S3 VWAP pullback | zoneA vwap | `t1.0/s0.75/m-` | 2,374 | 51.4% | +0.0066 | 1.04 |
| S3 VWAP pullback | zoneA vwap | `t2.0/s1.0/m-` | 2,347 | 51.6% | +0.0041 | 1.02 |
| S3 VWAP pullback | zoneA vwap | `t1.5/s1.0/m15` | 4,066 | 49.9% | +0.0011 | 1.02 |
| S3 VWAP pullback | zoneA vwap | `t2.0/s1.0/m15` | 4,066 | 49.9% | +0.0011 | 1.02 |
| S3 VWAP pullback | zoneA vwap | `t1.5/s1.0/m-` | 2,347 | 51.6% | +0.0011 | 1.01 |
| S3 VWAP pullback | zoneA vwap | `t1.0/s0.75/m15` | 4,066 | 49.8% | +0.0009 | 1.02 |
| S3 VWAP pullback | zoneA vwap | `t1.5/s1.0/m30` | 3,715 | 50.3% | +0.0005 | 1.01 |
| S3 VWAP pullback | zoneA vwap | `t2.0/s1.0/m30` | 3,715 | 50.3% | +0.0005 | 1.01 |
| S3 VWAP pullback | zoneA vwap | `t0.5/s0.5/m-` | 2,522 | 50.9% | +0.0005 | 1.00 |
| S3 VWAP pullback | zoneA vwap | `t0.5/s0.5/m15` | 4,066 | 49.8% | +0.0004 | 1.01 |
| S3 VWAP pullback | zoneA vwap | `t0.5/s0.5/m30` | 3,722 | 50.1% | +0.0003 | 1.00 |
| S3 VWAP pullback | zoneA vwap | `t1.0/s0.75/m30` | 3,716 | 50.2% | +0.0002 | 1.00 |
| S3 VWAP pullback | zoneB 0.25atr | `t2.0/s1.0/m-` | 3,392 | 51.1% | +0.0142 | 1.07 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.0/s0.75/m-` | 3,613 | 50.6% | +0.0133 | 1.07 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.5/s1.0/m-` | 3,402 | 51.1% | +0.0120 | 1.06 |
| S3 VWAP pullback | zoneB 0.25atr | `t0.5/s0.5/m-` | 5,008 | 51.0% | +0.0058 | 1.03 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.5/s1.0/m30` | 22,683 | 49.3% | +0.0009 | 1.02 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.0/s0.75/m30` | 22,689 | 49.3% | +0.0009 | 1.02 |
| S3 VWAP pullback | zoneB 0.25atr | `t2.0/s1.0/m30` | 22,683 | 49.3% | +0.0009 | 1.02 |
| S3 VWAP pullback | zoneB 0.25atr | `t0.5/s0.5/m30` | 22,743 | 49.3% | +0.0007 | 1.01 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.5/s1.0/m15` | 34,311 | 47.9% | +0.0002 | 1.01 |
| S3 VWAP pullback | zoneB 0.25atr | `t1.0/s0.75/m15` | 34,315 | 47.9% | +0.0002 | 1.01 |
| S3 VWAP pullback | zoneB 0.25atr | `t2.0/s1.0/m15` | 34,311 | 47.9% | +0.0002 | 1.00 |
| S3 VWAP pullback | zoneB 0.25atr | `t0.5/s0.5/m15` | 34,334 | 47.9% | -0.0000 | 1.00 |
| S3 VWAP pullback | zoneC 0.50atr | `t2.0/s1.0/m-` | 3,489 | 51.0% | +0.0143 | 1.07 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.5/s1.0/m-` | 3,515 | 51.1% | +0.0135 | 1.07 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.0/s0.75/m-` | 3,951 | 50.7% | +0.0133 | 1.07 |
| S3 VWAP pullback | zoneC 0.50atr | `t0.5/s0.5/m-` | 5,959 | 50.8% | +0.0044 | 1.03 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.5/s1.0/m30` | 26,457 | 48.9% | +0.0004 | 1.01 |
| S3 VWAP pullback | zoneC 0.50atr | `t2.0/s1.0/m30` | 26,457 | 48.9% | +0.0003 | 1.01 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.0/s0.75/m30` | 26,472 | 48.9% | +0.0002 | 1.00 |
| S3 VWAP pullback | zoneC 0.50atr | `t0.5/s0.5/m30` | 26,597 | 48.9% | +0.0001 | 1.00 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.5/s1.0/m15` | 40,988 | 47.5% | -0.0005 | 0.99 |
| S3 VWAP pullback | zoneC 0.50atr | `t2.0/s1.0/m15` | 40,988 | 47.5% | -0.0005 | 0.99 |
| S3 VWAP pullback | zoneC 0.50atr | `t1.0/s0.75/m15` | 40,997 | 47.5% | -0.0005 | 0.99 |
| S3 VWAP pullback | zoneC 0.50atr | `t0.5/s0.5/m15` | 41,035 | 47.5% | -0.0007 | 0.98 |
| S4 VWAP reclaim | chop<=2 | `t2.0/s1.0/m-` | 2,164 | 49.8% | +0.0217 | 1.11 |
| S4 VWAP reclaim | chop<=2 | `t1.0/s0.75/m-` | 2,168 | 49.4% | +0.0211 | 1.11 |
| S4 VWAP reclaim | chop<=2 | `t1.5/s1.0/m-` | 2,165 | 49.8% | +0.0202 | 1.10 |
| S4 VWAP reclaim | chop<=2 | `t0.5/s0.5/m-` | 2,196 | 49.5% | +0.0024 | 1.01 |
| S4 VWAP reclaim | chop<=2 | `t0.5/s0.5/m30` | 2,269 | 50.4% | -0.0019 | 0.98 |
| S4 VWAP reclaim | chop<=2 | `t1.5/s1.0/m30` | 2,268 | 50.3% | -0.0019 | 0.98 |
| S4 VWAP reclaim | chop<=2 | `t2.0/s1.0/m30` | 2,268 | 50.3% | -0.0019 | 0.98 |
| S4 VWAP reclaim | chop<=2 | `t1.0/s0.75/m30` | 2,268 | 50.3% | -0.0027 | 0.97 |
| S4 VWAP reclaim | chop<=2 | `t0.5/s0.5/m15` | 2,371 | 49.1% | -0.0063 | 0.90 |
| S4 VWAP reclaim | chop<=2 | `t1.5/s1.0/m15` | 2,370 | 49.0% | -0.0065 | 0.89 |
| S4 VWAP reclaim | chop<=2 | `t1.0/s0.75/m15` | 2,370 | 49.0% | -0.0068 | 0.89 |
| S4 VWAP reclaim | chop<=2 | `t2.0/s1.0/m15` | 2,370 | 49.0% | -0.0068 | 0.89 |
| S4 VWAP reclaim | chop<=3 | `t1.0/s0.75/m-` | 2,761 | 48.5% | +0.0084 | 1.04 |
| S4 VWAP reclaim | chop<=3 | `t2.0/s1.0/m-` | 2,750 | 48.8% | +0.0080 | 1.04 |
| S4 VWAP reclaim | chop<=3 | `t1.5/s1.0/m-` | 2,753 | 48.8% | +0.0064 | 1.03 |
| S4 VWAP reclaim | chop<=3 | `t1.5/s1.0/m30` | 3,099 | 49.1% | -0.0055 | 0.94 |
| S4 VWAP reclaim | chop<=3 | `t2.0/s1.0/m30` | 3,099 | 49.1% | -0.0055 | 0.94 |
| S4 VWAP reclaim | chop<=3 | `t0.5/s0.5/m30` | 3,101 | 49.1% | -0.0056 | 0.93 |
| S4 VWAP reclaim | chop<=3 | `t1.0/s0.75/m30` | 3,099 | 49.1% | -0.0061 | 0.93 |
| S4 VWAP reclaim | chop<=3 | `t0.5/s0.5/m15` | 3,413 | 48.4% | -0.0074 | 0.88 |
| S4 VWAP reclaim | chop<=3 | `t1.5/s1.0/m15` | 3,412 | 48.3% | -0.0077 | 0.87 |
| S4 VWAP reclaim | chop<=3 | `t1.0/s0.75/m15` | 3,412 | 48.3% | -0.0078 | 0.87 |
| S4 VWAP reclaim | chop<=3 | `t2.0/s1.0/m15` | 3,412 | 48.3% | -0.0079 | 0.87 |
| S4 VWAP reclaim | chop<=3 | `t0.5/s0.5/m-` | 2,858 | 48.3% | -0.0086 | 0.96 |
| S4 VWAP reclaim | chop<=4 | `t1.0/s0.75/m-` | 3,105 | 48.7% | +0.0072 | 1.04 |
| S4 VWAP reclaim | chop<=4 | `t2.0/s1.0/m-` | 3,075 | 48.9% | +0.0062 | 1.03 |
| S4 VWAP reclaim | chop<=4 | `t1.5/s1.0/m-` | 3,078 | 49.0% | +0.0050 | 1.02 |
| S4 VWAP reclaim | chop<=4 | `t0.5/s0.5/m15` | 4,332 | 48.4% | -0.0067 | 0.89 |
| S4 VWAP reclaim | chop<=4 | `t1.5/s1.0/m15` | 4,330 | 48.4% | -0.0067 | 0.89 |
| S4 VWAP reclaim | chop<=4 | `t1.0/s0.75/m15` | 4,330 | 48.4% | -0.0068 | 0.88 |
| S4 VWAP reclaim | chop<=4 | `t2.0/s1.0/m15` | 4,330 | 48.4% | -0.0069 | 0.88 |
| S4 VWAP reclaim | chop<=4 | `t0.5/s0.5/m-` | 3,261 | 48.6% | -0.0070 | 0.96 |
| S4 VWAP reclaim | chop<=4 | `t1.5/s1.0/m30` | 3,757 | 48.3% | -0.0085 | 0.90 |
| S4 VWAP reclaim | chop<=4 | `t2.0/s1.0/m30` | 3,757 | 48.3% | -0.0085 | 0.90 |
| S4 VWAP reclaim | chop<=4 | `t0.5/s0.5/m30` | 3,762 | 48.4% | -0.0088 | 0.90 |
| S4 VWAP reclaim | chop<=4 | `t1.0/s0.75/m30` | 3,757 | 48.3% | -0.0089 | 0.89 |
| S4 VWAP reclaim | chop<=5 | `t1.0/s0.75/m-` | 3,249 | 48.9% | +0.0087 | 1.04 |
| S4 VWAP reclaim | chop<=5 | `t2.0/s1.0/m-` | 3,204 | 49.2% | +0.0080 | 1.04 |
| S4 VWAP reclaim | chop<=5 | `t1.5/s1.0/m-` | 3,209 | 49.2% | +0.0064 | 1.03 |
| S4 VWAP reclaim | chop<=5 | `t0.5/s0.5/m-` | 3,473 | 49.1% | -0.0034 | 0.98 |
| S4 VWAP reclaim | chop<=5 | `t1.5/s1.0/m15` | 5,167 | 48.8% | -0.0044 | 0.92 |
| S4 VWAP reclaim | chop<=5 | `t0.5/s0.5/m15` | 5,169 | 48.8% | -0.0044 | 0.92 |
| S4 VWAP reclaim | chop<=5 | `t2.0/s1.0/m15` | 5,167 | 48.8% | -0.0045 | 0.92 |
| S4 VWAP reclaim | chop<=5 | `t1.0/s0.75/m15` | 5,167 | 48.8% | -0.0046 | 0.92 |
| S4 VWAP reclaim | chop<=5 | `t0.5/s0.5/m30` | 4,307 | 48.5% | -0.0074 | 0.91 |
| S4 VWAP reclaim | chop<=5 | `t1.5/s1.0/m30` | 4,303 | 48.4% | -0.0074 | 0.91 |
| S4 VWAP reclaim | chop<=5 | `t2.0/s1.0/m30` | 4,303 | 48.4% | -0.0074 | 0.91 |
| S4 VWAP reclaim | chop<=5 | `t1.0/s0.75/m30` | 4,303 | 48.4% | -0.0078 | 0.91 |
| S5 Premarket breakout | immediate | `t1.0/s0.75/m-` | 209 | 56.9% | +0.0592 | 1.41 |
| S5 Premarket breakout | immediate | `t2.0/s1.0/m-` | 205 | 57.1% | +0.0574 | 1.39 |
| S5 Premarket breakout | immediate | `t1.5/s1.0/m-` | 205 | 57.1% | +0.0476 | 1.32 |
| S5 Premarket breakout | immediate | `t0.5/s0.5/m-` | 213 | 56.8% | +0.0471 | 1.35 |
| S5 Premarket breakout | immediate | `t1.5/s1.0/m30` | 235 | 50.2% | +0.0005 | 1.01 |
| S5 Premarket breakout | immediate | `t2.0/s1.0/m30` | 235 | 50.2% | +0.0005 | 1.01 |
| S5 Premarket breakout | immediate | `t0.5/s0.5/m30` | 235 | 50.6% | +0.0005 | 1.01 |
| S5 Premarket breakout | immediate | `t1.0/s0.75/m30` | 235 | 50.2% | -0.0005 | 0.99 |
| S5 Premarket breakout | immediate | `t0.5/s0.5/m15` | 237 | 43.5% | -0.0120 | 0.76 |
| S5 Premarket breakout | immediate | `t1.0/s0.75/m15` | 237 | 43.5% | -0.0128 | 0.75 |
| S5 Premarket breakout | immediate | `t1.5/s1.0/m15` | 237 | 43.5% | -0.0128 | 0.75 |
| S5 Premarket breakout | immediate | `t2.0/s1.0/m15` | 237 | 43.5% | -0.0128 | 0.75 |
| S5 Premarket breakout | retest | `t2.0/s1.0/m-` | 174 | 55.2% | +0.0596 | 1.42 |
| S5 Premarket breakout | retest | `t1.5/s1.0/m-` | 174 | 55.2% | +0.0540 | 1.38 |
| S5 Premarket breakout | retest | `t1.0/s0.75/m-` | 179 | 55.3% | +0.0537 | 1.39 |
| S5 Premarket breakout | retest | `t0.5/s0.5/m-` | 187 | 54.0% | +0.0412 | 1.31 |
| S5 Premarket breakout | retest | `t1.5/s1.0/m30` | 394 | 49.5% | -0.0052 | 0.91 |
| S5 Premarket breakout | retest | `t2.0/s1.0/m30` | 394 | 49.5% | -0.0052 | 0.91 |
| S5 Premarket breakout | retest | `t1.0/s0.75/m15` | 476 | 46.4% | -0.0053 | 0.88 |
| S5 Premarket breakout | retest | `t1.5/s1.0/m15` | 476 | 46.4% | -0.0053 | 0.88 |
| S5 Premarket breakout | retest | `t2.0/s1.0/m15` | 476 | 46.4% | -0.0053 | 0.88 |
| S5 Premarket breakout | retest | `t1.0/s0.75/m30` | 394 | 49.5% | -0.0062 | 0.90 |
| S5 Premarket breakout | retest | `t0.5/s0.5/m15` | 476 | 46.4% | -0.0066 | 0.85 |
| S5 Premarket breakout | retest | `t0.5/s0.5/m30` | 394 | 49.5% | -0.0068 | 0.89 |
| S6 Prev-day breakout | immediate | `t1.5/s1.0/m30` | 3,087 | 49.0% | +0.0015 | 1.02 |
| S6 Prev-day breakout | immediate | `t2.0/s1.0/m30` | 3,087 | 49.0% | +0.0014 | 1.02 |
| S6 Prev-day breakout | immediate | `t2.0/s1.0/m15` | 3,089 | 48.4% | +0.0013 | 1.02 |
| S6 Prev-day breakout | immediate | `t1.5/s1.0/m15` | 3,089 | 48.4% | +0.0012 | 1.02 |
| S6 Prev-day breakout | immediate | `t0.5/s0.5/m15` | 3,090 | 48.4% | +0.0011 | 1.02 |
| S6 Prev-day breakout | immediate | `t1.0/s0.75/m15` | 3,089 | 48.4% | +0.0010 | 1.02 |
| S6 Prev-day breakout | immediate | `t0.5/s0.5/m30` | 3,089 | 49.0% | +0.0008 | 1.01 |
| S6 Prev-day breakout | immediate | `t1.0/s0.75/m30` | 3,087 | 49.0% | +0.0008 | 1.01 |
| S6 Prev-day breakout | immediate | `t0.5/s0.5/m-` | 3,055 | 50.0% | -0.0035 | 0.98 |
| S6 Prev-day breakout | immediate | `t2.0/s1.0/m-` | 2,919 | 49.6% | -0.0045 | 0.98 |
| S6 Prev-day breakout | immediate | `t1.5/s1.0/m-` | 2,919 | 49.6% | -0.0058 | 0.97 |
| S6 Prev-day breakout | immediate | `t1.0/s0.75/m-` | 2,971 | 49.0% | -0.0071 | 0.97 |
| S6 Prev-day breakout | retest | `t2.0/s1.0/m15` | 5,034 | 46.1% | -0.0076 | 0.84 |
| S6 Prev-day breakout | retest | `t1.5/s1.0/m15` | 5,034 | 46.1% | -0.0077 | 0.84 |
| S6 Prev-day breakout | retest | `t1.0/s0.75/m15` | 5,034 | 46.0% | -0.0082 | 0.83 |
| S6 Prev-day breakout | retest | `t0.5/s0.5/m15` | 5,036 | 46.0% | -0.0083 | 0.83 |
| S6 Prev-day breakout | retest | `t2.0/s1.0/m30` | 4,170 | 47.7% | -0.0085 | 0.87 |
| S6 Prev-day breakout | retest | `t1.5/s1.0/m30` | 4,170 | 47.7% | -0.0086 | 0.87 |
| S6 Prev-day breakout | retest | `t1.0/s0.75/m30` | 4,171 | 47.7% | -0.0097 | 0.86 |
| S6 Prev-day breakout | retest | `t0.5/s0.5/m30` | 4,177 | 47.7% | -0.0098 | 0.86 |
| S6 Prev-day breakout | retest | `t2.0/s1.0/m-` | 1,952 | 47.0% | -0.0182 | 0.91 |
| S6 Prev-day breakout | retest | `t1.5/s1.0/m-` | 1,952 | 47.0% | -0.0199 | 0.90 |
| S6 Prev-day breakout | retest | `t1.0/s0.75/m-` | 2,002 | 46.5% | -0.0254 | 0.87 |
| S6 Prev-day breakout | retest | `t0.5/s0.5/m-` | 2,159 | 46.6% | -0.0285 | 0.84 |
| S7 Failed breakout | prev-day levels | `t1.5/s1.0/m-` | 2,003 | 51.7% | +0.0322 | 1.19 |
| S7 Failed breakout | prev-day levels | `t2.0/s1.0/m-` | 2,000 | 51.6% | +0.0314 | 1.19 |
| S7 Failed breakout | prev-day levels | `t1.0/s0.75/m-` | 2,051 | 51.1% | +0.0268 | 1.16 |
| S7 Failed breakout | prev-day levels | `t0.5/s0.5/m-` | 2,273 | 52.4% | +0.0267 | 1.18 |
| S7 Failed breakout | prev-day levels | `t0.5/s0.5/m30` | 4,377 | 51.4% | +0.0097 | 1.17 |
| S7 Failed breakout | prev-day levels | `t1.5/s1.0/m30` | 4,369 | 51.4% | +0.0093 | 1.16 |
| S7 Failed breakout | prev-day levels | `t2.0/s1.0/m30` | 4,369 | 51.4% | +0.0093 | 1.16 |
| S7 Failed breakout | prev-day levels | `t1.0/s0.75/m30` | 4,370 | 51.4% | +0.0087 | 1.15 |
| S7 Failed breakout | prev-day levels | `t0.5/s0.5/m15` | 5,255 | 50.7% | +0.0045 | 1.10 |
| S7 Failed breakout | prev-day levels | `t1.5/s1.0/m15` | 5,253 | 50.7% | +0.0043 | 1.10 |
| S7 Failed breakout | prev-day levels | `t2.0/s1.0/m15` | 5,253 | 50.7% | +0.0043 | 1.10 |
| S7 Failed breakout | prev-day levels | `t1.0/s0.75/m15` | 5,254 | 50.6% | +0.0039 | 1.09 |
| S8 Liquidity sweep | reclaim<=10bars | `t2.0/s1.0/m-` | 1,859 | 51.4% | +0.0209 | 1.12 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.5/s1.0/m-` | 1,861 | 51.4% | +0.0207 | 1.12 |
| S8 Liquidity sweep | reclaim<=10bars | `t0.5/s0.5/m-` | 2,089 | 51.3% | +0.0168 | 1.11 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.0/s0.75/m-` | 1,905 | 50.8% | +0.0155 | 1.09 |
| S8 Liquidity sweep | reclaim<=10bars | `t0.5/s0.5/m30` | 3,750 | 50.6% | +0.0037 | 1.06 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.5/s1.0/m30` | 3,739 | 50.5% | +0.0027 | 1.04 |
| S8 Liquidity sweep | reclaim<=10bars | `t2.0/s1.0/m30` | 3,739 | 50.5% | +0.0027 | 1.04 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.0/s0.75/m30` | 3,741 | 50.5% | +0.0027 | 1.04 |
| S8 Liquidity sweep | reclaim<=10bars | `t0.5/s0.5/m15` | 4,429 | 50.0% | +0.0020 | 1.05 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.5/s1.0/m15` | 4,422 | 50.0% | +0.0018 | 1.04 |
| S8 Liquidity sweep | reclaim<=10bars | `t2.0/s1.0/m15` | 4,422 | 50.0% | +0.0018 | 1.04 |
| S8 Liquidity sweep | reclaim<=10bars | `t1.0/s0.75/m15` | 4,423 | 50.0% | +0.0017 | 1.04 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.5/s1.0/m-` | 1,603 | 50.8% | +0.0185 | 1.11 |
| S8 Liquidity sweep | reclaim<=3bars | `t0.5/s0.5/m-` | 1,745 | 51.3% | +0.0185 | 1.12 |
| S8 Liquidity sweep | reclaim<=3bars | `t2.0/s1.0/m-` | 1,603 | 50.8% | +0.0184 | 1.11 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.0/s0.75/m-` | 1,629 | 50.0% | +0.0107 | 1.06 |
| S8 Liquidity sweep | reclaim<=3bars | `t0.5/s0.5/m30` | 2,811 | 51.1% | +0.0052 | 1.09 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.5/s1.0/m30` | 2,800 | 51.0% | +0.0034 | 1.06 |
| S8 Liquidity sweep | reclaim<=3bars | `t2.0/s1.0/m30` | 2,800 | 51.0% | +0.0034 | 1.06 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.0/s0.75/m30` | 2,803 | 51.0% | +0.0032 | 1.05 |
| S8 Liquidity sweep | reclaim<=3bars | `t0.5/s0.5/m15` | 3,170 | 50.1% | +0.0029 | 1.07 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.5/s1.0/m15` | 3,164 | 50.1% | +0.0029 | 1.07 |
| S8 Liquidity sweep | reclaim<=3bars | `t2.0/s1.0/m15` | 3,164 | 50.1% | +0.0029 | 1.07 |
| S8 Liquidity sweep | reclaim<=3bars | `t1.0/s0.75/m15` | 3,166 | 50.1% | +0.0023 | 1.05 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.5/s1.0/m-` | 1,732 | 50.9% | +0.0178 | 1.11 |
| S8 Liquidity sweep | reclaim<=5bars | `t2.0/s1.0/m-` | 1,731 | 50.9% | +0.0177 | 1.10 |
| S8 Liquidity sweep | reclaim<=5bars | `t0.5/s0.5/m-` | 1,921 | 51.2% | +0.0169 | 1.11 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.0/s0.75/m-` | 1,765 | 50.3% | +0.0126 | 1.07 |
| S8 Liquidity sweep | reclaim<=5bars | `t0.5/s0.5/m30` | 3,286 | 51.2% | +0.0058 | 1.10 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.5/s1.0/m30` | 3,273 | 51.2% | +0.0047 | 1.08 |
| S8 Liquidity sweep | reclaim<=5bars | `t2.0/s1.0/m30` | 3,273 | 51.2% | +0.0047 | 1.08 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.0/s0.75/m30` | 3,275 | 51.2% | +0.0047 | 1.08 |
| S8 Liquidity sweep | reclaim<=5bars | `t0.5/s0.5/m15` | 3,770 | 49.9% | +0.0028 | 1.06 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.5/s1.0/m15` | 3,763 | 49.9% | +0.0028 | 1.06 |
| S8 Liquidity sweep | reclaim<=5bars | `t2.0/s1.0/m15` | 3,763 | 49.9% | +0.0028 | 1.06 |
| S8 Liquidity sweep | reclaim<=5bars | `t1.0/s0.75/m15` | 3,764 | 49.9% | +0.0026 | 1.06 |
| S9 Range reversal | range-filtered | `t0.5/s0.5/m-` | 4,789 | 50.1% | -0.0010 | 0.99 |
| S9 Range reversal | range-filtered | `t0.5/s0.5/m15` | 20,901 | 49.9% | -0.0011 | 0.97 |
| S9 Range reversal | range-filtered | `t1.0/s0.75/m15` | 20,880 | 49.8% | -0.0018 | 0.95 |
| S9 Range reversal | range-filtered | `t1.5/s1.0/m15` | 20,878 | 49.8% | -0.0019 | 0.95 |
| S9 Range reversal | range-filtered | `t2.0/s1.0/m15` | 20,878 | 49.8% | -0.0020 | 0.95 |
| S9 Range reversal | range-filtered | `t0.5/s0.5/m30` | 14,394 | 49.1% | -0.0024 | 0.96 |
| S9 Range reversal | range-filtered | `t1.0/s0.75/m30` | 14,324 | 49.0% | -0.0036 | 0.93 |
| S9 Range reversal | range-filtered | `t2.0/s1.0/m30` | 14,320 | 49.0% | -0.0038 | 0.93 |
| S9 Range reversal | range-filtered | `t1.5/s1.0/m30` | 14,320 | 49.0% | -0.0039 | 0.93 |
| S9 Range reversal | range-filtered | `t1.0/s0.75/m-` | 3,468 | 49.0% | -0.0096 | 0.95 |
| S9 Range reversal | range-filtered | `t2.0/s1.0/m-` | 3,282 | 49.5% | -0.0120 | 0.94 |
| S9 Range reversal | range-filtered | `t1.5/s1.0/m-` | 3,288 | 49.5% | -0.0135 | 0.93 |
| S9 Range reversal | unfiltered | `t0.5/s0.5/m15` | 29,525 | 50.0% | -0.0015 | 0.96 |
| S9 Range reversal | unfiltered | `t0.5/s0.5/m-` | 5,939 | 49.8% | -0.0019 | 0.99 |
| S9 Range reversal | unfiltered | `t1.0/s0.75/m15` | 29,469 | 49.9% | -0.0022 | 0.95 |
| S9 Range reversal | unfiltered | `t1.5/s1.0/m15` | 29,460 | 49.8% | -0.0024 | 0.94 |
| S9 Range reversal | unfiltered | `t2.0/s1.0/m15` | 29,460 | 49.8% | -0.0024 | 0.94 |
| S9 Range reversal | unfiltered | `t0.5/s0.5/m30` | 19,359 | 49.0% | -0.0026 | 0.96 |
| S9 Range reversal | unfiltered | `t1.0/s0.75/m30` | 19,194 | 48.9% | -0.0036 | 0.94 |
| S9 Range reversal | unfiltered | `t2.0/s1.0/m30` | 19,165 | 48.8% | -0.0039 | 0.93 |
| S9 Range reversal | unfiltered | `t1.5/s1.0/m30` | 19,166 | 48.8% | -0.0040 | 0.93 |
| S9 Range reversal | unfiltered | `t1.0/s0.75/m-` | 4,061 | 48.7% | -0.0105 | 0.95 |
| S9 Range reversal | unfiltered | `t2.0/s1.0/m-` | 3,573 | 49.3% | -0.0133 | 0.94 |
| S9 Range reversal | unfiltered | `t1.5/s1.0/m-` | 3,603 | 49.1% | -0.0173 | 0.92 |

## Method and its limits

- Signals evaluate on a closed bar; fills happen at the **next** bar's open.
- When a bar contains both the stop and the target, the **stop** is taken - 1-minute OHLC cannot resolve the order, and assuming otherwise inflates results.
- One position at a time, forced flat at 15:59.
- No commission or slippage is modelled yet. Real fills are worse than these.
- Expectancy is in ATR, not dollars, so 2008 and 2021 are comparable.
- **This measures the underlying entry only.** A positive underlying edge is a necessary but not sufficient condition for a profitable 0DTE option trade; theta and spread can erase a real move. Phase 5 models that separately.

