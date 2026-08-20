# Fixed-Clock Exit Study

What is each strategy's entry worth on a pure clock?

Owner's question: take every signal all 15 strategies fire, ignore what
each one does about exits, and just hold for a fixed number of minutes -
5, 10, 15, 20, 25, 30 - then close at market. What does the P/L look like?

That isolates the ENTRY. Every strategy currently mixes two separate
claims: "this is a good moment to be long/short" and "these are the right
target and stop". Measuring them under one clock removes the second claim
entirely, so what is left is the first one.

## What is deliberately switched off

No profit target, no stop, no breakeven floor, no ratchet, no stagnation
bail, and for SPY_KEY_LEVELS no underlying stop or R-target either. The
ONLY things that can close a trade are the horizon and the 15:45 flatten
(`LAST_EXIT_MINUTE`), which is not optional - a 0DTE held past the bell is
not a trade anyone can make.

## Two things that will look like bugs and are not

1. **Trade counts differ across horizons.** One position at a time is a
   live rule, so a 5-minute clock frees the strategy to take the next
   signal while a 30-minute clock is still holding the first. Shorter
   horizons therefore take strictly more trades. Covered by
   `test_a_shorter_clock_frees_the_strategy_to_trade_again`.
2. **SPY_KEY_LEVELS is not comparable to its own baseline.** It exits on
   the UNDERLYING live (stop at the level, target at 2R), so it has no
   premium-percent exit to be measured against. It is scored on option
   premium here like the other 14, and flagged in the output rather than
   quietly ranked alongside them.

Entries come from `spy_live_new_strategies.NEW_STRATEGY_SPECS` - the same
callables the live scanner uses, at their live thresholds. That matters:
the older `spy_option_report.SHORTLIST` still names `1.0atr ext` and
`0.5atr drive` for two strategies that were recalibrated to 0.40 and 0.22,
so anything driven off SHORTLIST measures thresholds this system stopped
using.

One pass over the archive, all six horizons scored per signal, because
each horizon on its own walk would be six times ~40 minutes.

Run:  ./.venv-tradysquid/Scripts/python.exe spy_time_stop_study.py

Sessions scored: **988** (only sessions where a same-day expiry really existed). Run time 4 min.

## $/trade by horizon

| Strategy | 5m | 10m | 15m | 20m | 25m | 30m | best | its own exit (BASELINE) |
|---|---|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | +5.19 | +8.73 | +4.87 | -0.62 | -2.36 | +4.50 | **+8.73** @ 10m | +15.69 (+115/-75) |
| SPY_EXHAUSTION_1ATR | +1.04 | +2.95 | +4.72 | +5.92 | +7.65 | +8.59 | **+8.59** @ 30m | +4.06 (+115/-75) |
| SPY_FIRST_PULLBACK | -0.43 | +0.79 | +2.11 | +4.11 | +6.46 | +8.37 | **+8.37** @ 30m | +0.65 (+75/-58) |
| SPY_GAP_CONT_50 | +0.18 | +1.93 | +3.91 | +5.27 | +7.04 | +8.14 | **+8.14** @ 30m | +8.47 (+150/-75) |
| SPY_TOD_FINAL30 | +2.81 | +5.67 | +5.82 | +5.82 | +5.82 | +5.82 | **+5.82** @ 15m | +2.00 (+115/-75) |
| SPY_ORB_IMMEDIATE | +1.18 | -0.16 | +2.10 | +2.95 | +3.06 | +5.01 | **+5.01** @ 30m | +4.67 (+115/-75) |
| SPY_FAILED_BREAK | -0.88 | +1.11 | +1.94 | +3.89 | +4.82 | +4.91 | **+4.91** @ 30m | +2.85 (+115/-75) |
| SPY_SWEEP_10 | -0.94 | +1.27 | +2.44 | +2.36 | +3.39 | +4.00 | **+4.00** @ 30m | +3.20 (+150/-75) |
| SPY_COMPRESSION_3BAR | +0.01 | +0.74 | +0.59 | +3.57 | +3.08 | +1.92 | **+3.57** @ 20m | +6.62 (+115/-75) |
| SPY_VWAP_RECLAIM | -0.34 | -1.30 | +0.09 | +1.92 | +3.33 | +3.42 | **+3.42** @ 30m | +4.54 (+150/-75) |
| SPY_MOMENTUM_ADX25 | -1.23 | -0.50 | +0.63 | +0.86 | +1.99 | +2.96 | **+2.96** @ 30m | +2.85 (+115/-75) |
| SPY_MTF_4OF4 | -1.06 | -0.21 | +0.82 | +2.68 | +2.60 | +2.91 | **+2.91** @ 30m | +3.32 (+150/-75) |
| SPY_CONFLUENCE_4 | -0.93 | -0.16 | +0.86 | +0.88 | +2.05 | +2.40 | **+2.40** @ 30m | +3.43 (+115/-75) |
| SPY_KEY_LEVELS * | -1.15 | -0.48 | +0.16 | +1.19 | +1.88 | +2.26 | **+2.26** @ 30m | +26.86 (underlying stop/target) |
| SPY_TOD_MIDDAY | -1.42 | -0.73 | -0.41 | +0.30 | +1.06 | +1.43 | **+1.43** @ 30m | +4.66 (+150/-75) |

`*` SPY_KEY_LEVELS exits on the UNDERLYING live, so its BASELINE column is not a like-for-like comparison.

## Win rate by horizon

| Strategy | 5m | 10m | 15m | 20m | 25m | 30m |
|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | 53.8% | 61.5% | 38.5% | 53.8% | 46.2% | 38.5% |
| SPY_EXHAUSTION_1ATR | 42.4% | 42.6% | 44.8% | 44.1% | 46.1% | 46.9% |
| SPY_FIRST_PULLBACK | 36.7% | 40.8% | 44.7% | 43.5% | 43.2% | 46.7% |
| SPY_GAP_CONT_50 | 42.0% | 45.2% | 45.9% | 46.5% | 48.0% | 48.3% |
| SPY_TOD_FINAL30 | 45.6% | 48.0% | 47.3% | 47.3% | 47.3% | 47.3% |
| SPY_ORB_IMMEDIATE | 42.6% | 43.5% | 43.8% | 45.2% | 41.9% | 44.7% |
| SPY_FAILED_BREAK | 38.7% | 41.0% | 44.0% | 45.6% | 44.1% | 44.3% |
| SPY_SWEEP_10 | 37.0% | 42.7% | 44.8% | 45.0% | 42.1% | 42.1% |
| SPY_COMPRESSION_3BAR | 39.5% | 40.7% | 40.7% | 47.2% | 46.5% | 48.4% |
| SPY_VWAP_RECLAIM | 40.2% | 37.3% | 39.0% | 41.6% | 45.3% | 43.5% |
| SPY_MOMENTUM_ADX25 | 35.9% | 38.0% | 39.2% | 39.7% | 40.3% | 40.7% |
| SPY_MTF_4OF4 | 35.1% | 37.5% | 38.7% | 42.5% | 40.5% | 41.1% |
| SPY_CONFLUENCE_4 | 37.4% | 40.5% | 40.9% | 41.3% | 43.1% | 42.4% |
| SPY_KEY_LEVELS | 36.4% | 39.3% | 40.6% | 42.1% | 42.5% | 41.8% |
| SPY_TOD_MIDDAY | 35.2% | 38.0% | 38.4% | 40.1% | 41.8% | 42.1% |

## Trades and total P/L by horizon

| Strategy | 5m trades / total $ | 10m trades / total $ | 15m trades / total $ | 20m trades / total $ | 25m trades / total $ | 30m trades / total $ |
|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | 13 / +68 | 13 / +114 | 13 / +63 | 13 / -8 | 13 / -31 | 13 / +58 |
| SPY_EXHAUSTION_1ATR | 349 / +363 | 331 / +978 | 310 / +1,462 | 297 / +1,758 | 282 / +2,157 | 275 / +2,363 |
| SPY_FIRST_PULLBACK | 338 / -145 | 338 / +267 | 338 / +713 | 338 / +1,389 | 338 / +2,184 | 338 / +2,830 |
| SPY_GAP_CONT_50 | 5,217 / +921 | 3,686 / +7,126 | 2,927 / +11,440 | 2,421 / +12,758 | 2,073 / +14,589 | 1,846 / +15,028 |
| SPY_TOD_FINAL30 | 281 / +791 | 281 / +1,593 | 281 / +1,635 | 281 / +1,635 | 281 / +1,635 | 281 / +1,635 |
| SPY_ORB_IMMEDIATE | 418 / +492 | 418 / -68 | 418 / +877 | 418 / +1,233 | 418 / +1,279 | 418 / +2,093 |
| SPY_FAILED_BREAK | 1,376 / -1,213 | 1,219 / +1,351 | 1,113 / +2,158 | 1,039 / +4,038 | 979 / +4,722 | 938 / +4,602 |
| SPY_SWEEP_10 | 1,131 / -1,068 | 973 / +1,237 | 896 / +2,183 | 843 / +1,988 | 805 / +2,726 | 770 / +3,081 |
| SPY_COMPRESSION_3BAR | 162 / +1 | 162 / +120 | 162 / +96 | 161 / +575 | 159 / +490 | 159 / +305 |
| SPY_VWAP_RECLAIM | 624 / -212 | 590 / -769 | 566 / +50 | 560 / +1,075 | 554 / +1,847 | 550 / +1,881 |
| SPY_MOMENTUM_ADX25 | 12,170 / -14,952 | 8,991 / -4,511 | 7,378 / +4,621 | 6,374 / +5,485 | 5,712 / +11,340 | 5,202 / +15,405 |
| SPY_MTF_4OF4 | 3,286 / -3,482 | 2,559 / -538 | 2,133 / +1,755 | 1,888 / +5,055 | 1,724 / +4,487 | 1,584 / +4,613 |
| SPY_CONFLUENCE_4 | 8,128 / -7,553 | 5,710 / -936 | 4,533 / +3,878 | 3,801 / +3,350 | 3,311 / +6,797 | 2,949 / +7,070 |
| SPY_KEY_LEVELS | 24,855 / -28,700 | 16,469 / -7,897 | 12,681 / +2,054 | 10,366 / +12,298 | 8,814 / +16,547 | 7,755 / +17,550 |
| SPY_TOD_MIDDAY | 12,273 / -17,417 | 8,188 / -5,954 | 6,229 / -2,534 | 5,141 / +1,544 | 4,391 / +4,670 | 3,775 / +5,405 |

Trade counts rise as the horizon shortens because one position at a time is a live rule: a 5-minute clock is free to take the next signal while a 30-minute clock is still holding the first.

