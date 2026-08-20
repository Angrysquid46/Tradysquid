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

Sessions scored: **1,006** (only sessions where a same-day expiry really existed). Run time 5 min.

## $/trade by horizon

| Strategy | 5m | 10m | 15m | 20m | 25m | 30m | best | its own exit (BASELINE) |
|---|---|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | +0.37 | +5.29 | -3.09 | -2.87 | -4.00 | +5.89 | **+5.89** @ 30m | +15.69 (+115/-75) |
| SPY_EXHAUSTION_1ATR | -2.41 | -3.21 | -2.82 | -2.89 | -3.78 | -4.47 | **-2.41** @ 5m | +4.06 (+115/-75) |
| SPY_COMPRESSION_3BAR | -2.45 | -3.30 | -4.01 | -3.39 | -4.46 | -6.22 | **-2.45** @ 5m | +6.62 (+115/-75) |
| SPY_ORB_IMMEDIATE | -2.54 | -5.55 | -5.32 | -6.71 | -7.90 | -7.97 | **-2.54** @ 5m | +4.67 (+115/-75) |
| SPY_FIRST_PULLBACK | -2.61 | -3.63 | -3.98 | -3.88 | -3.59 | -3.39 | **-2.61** @ 5m | +0.65 (+75/-58) |
| SPY_TOD_FINAL30 | -2.98 | -4.23 | -6.99 | -6.99 | -6.99 | -6.99 | **-2.98** @ 5m | +2.00 (+115/-75) |
| SPY_SWEEP_10 | -3.34 | -3.02 | -3.54 | -4.84 | -5.58 | -6.08 | **-3.02** @ 10m | +3.20 (+150/-75) |
| SPY_KEY_LEVELS * | -3.39 | -4.29 | -5.16 | -5.90 | -6.67 | -7.71 | **-3.39** @ 5m | +26.86 (underlying stop/target) |
| SPY_TOD_MIDDAY | -3.45 | -4.29 | -5.37 | -6.20 | -6.98 | -7.82 | **-3.45** @ 5m | +4.66 (+150/-75) |
| SPY_MTF_4OF4 | -3.48 | -4.63 | -5.60 | -5.90 | -7.37 | -8.40 | **-3.48** @ 5m | +3.32 (+150/-75) |
| SPY_FAILED_BREAK | -3.62 | -3.66 | -4.34 | -4.60 | -5.35 | -6.30 | **-3.62** @ 5m | +2.85 (+115/-75) |
| SPY_VWAP_RECLAIM | -3.64 | -5.94 | -6.37 | -6.36 | -6.77 | -8.28 | **-3.64** @ 5m | +4.54 (+150/-75) |
| SPY_CONFLUENCE_4 | -3.66 | -4.70 | -5.17 | -6.87 | -7.54 | -8.19 | **-3.66** @ 5m | +3.43 (+115/-75) |
| SPY_MOMENTUM_ADX25 | -3.69 | -4.75 | -5.29 | -6.64 | -7.10 | -7.71 | **-3.69** @ 5m | +2.85 (+115/-75) |
| SPY_GAP_CONT_50 | -3.72 | -4.56 | -5.31 | -6.12 | -6.60 | -7.51 | **-3.72** @ 5m | +8.47 (+150/-75) |

`*` SPY_KEY_LEVELS exits on the UNDERLYING live, so its BASELINE column is not a like-for-like comparison.

## Win rate by horizon

| Strategy | 5m | 10m | 15m | 20m | 25m | 30m |
|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | 50.0% | 50.0% | 42.9% | 50.0% | 28.6% | 28.6% |
| SPY_EXHAUSTION_1ATR | 34.6% | 33.5% | 33.8% | 32.0% | 30.3% | 32.5% |
| SPY_COMPRESSION_3BAR | 27.8% | 25.6% | 26.4% | 28.4% | 28.7% | 27.0% |
| SPY_ORB_IMMEDIATE | 38.9% | 39.7% | 36.4% | 38.6% | 35.4% | 35.8% |
| SPY_FIRST_PULLBACK | 33.4% | 34.3% | 40.4% | 36.7% | 37.1% | 36.7% |
| SPY_TOD_FINAL30 | 29.9% | 30.1% | 25.7% | 25.7% | 25.7% | 25.7% |
| SPY_SWEEP_10 | 30.6% | 34.1% | 34.2% | 32.4% | 31.2% | 30.8% |
| SPY_KEY_LEVELS | 27.9% | 29.2% | 29.4% | 29.3% | 28.6% | 27.6% |
| SPY_TOD_MIDDAY | 27.4% | 28.9% | 27.4% | 27.3% | 27.7% | 27.4% |
| SPY_MTF_4OF4 | 27.1% | 27.7% | 26.3% | 26.9% | 26.4% | 25.7% |
| SPY_FAILED_BREAK | 31.7% | 34.2% | 32.9% | 33.6% | 32.9% | 31.5% |
| SPY_VWAP_RECLAIM | 35.7% | 34.2% | 33.7% | 36.1% | 37.7% | 34.4% |
| SPY_CONFLUENCE_4 | 29.1% | 29.8% | 29.9% | 28.9% | 29.1% | 28.7% |
| SPY_MOMENTUM_ADX25 | 28.7% | 28.9% | 29.7% | 28.3% | 27.8% | 27.7% |
| SPY_GAP_CONT_50 | 34.1% | 35.2% | 35.5% | 35.6% | 34.6% | 35.6% |

## Trades and total P/L by horizon

| Strategy | 5m trades / total $ | 10m trades / total $ | 15m trades / total $ | 20m trades / total $ | 25m trades / total $ | 30m trades / total $ |
|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | 14 / +5 | 14 / +74 | 14 / -43 | 14 / -40 | 14 / -56 | 14 / +83 |
| SPY_EXHAUSTION_1ATR | 457 / -1,101 | 430 / -1,381 | 402 / -1,135 | 378 / -1,093 | 360 / -1,362 | 348 / -1,556 |
| SPY_COMPRESSION_3BAR | 227 / -557 | 227 / -749 | 227 / -910 | 225 / -762 | 223 / -994 | 222 / -1,382 |
| SPY_ORB_IMMEDIATE | 511 / -1,298 | 511 / -2,838 | 511 / -2,719 | 511 / -3,431 | 511 / -4,039 | 511 / -4,070 |
| SPY_FIRST_PULLBACK | 428 / -1,115 | 428 / -1,552 | 428 / -1,703 | 428 / -1,662 | 428 / -1,536 | 428 / -1,449 |
| SPY_TOD_FINAL30 | 482 / -1,437 | 482 / -2,039 | 482 / -3,370 | 482 / -3,370 | 482 / -3,370 | 482 / -3,370 |
| SPY_SWEEP_10 | 1,590 / -5,319 | 1,363 / -4,121 | 1,246 / -4,406 | 1,165 / -5,636 | 1,109 / -6,191 | 1,055 / -6,412 |
| SPY_KEY_LEVELS | 31,423 / -106,508 | 19,967 / -85,670 | 14,873 / -76,752 | 11,909 / -70,242 | 10,021 / -66,878 | 8,689 / -66,970 |
| SPY_TOD_MIDDAY | 14,570 / -50,338 | 9,307 / -39,915 | 6,928 / -37,185 | 5,649 / -35,000 | 4,863 / -33,928 | 4,005 / -31,339 |
| SPY_MTF_4OF4 | 4,472 / -15,556 | 3,417 / -15,805 | 2,842 / -15,902 | 2,482 / -14,641 | 2,265 / -16,696 | 2,064 / -17,334 |
| SPY_FAILED_BREAK | 1,863 / -6,750 | 1,647 / -6,021 | 1,506 / -6,539 | 1,402 / -6,443 | 1,323 / -7,075 | 1,262 / -7,956 |
| SPY_VWAP_RECLAIM | 770 / -2,800 | 728 / -4,321 | 698 / -4,447 | 685 / -4,358 | 676 / -4,577 | 672 / -5,561 |
| SPY_CONFLUENCE_4 | 9,613 / -35,222 | 6,560 / -30,835 | 5,126 / -26,502 | 4,249 / -29,206 | 3,675 / -27,721 | 3,265 / -26,747 |
| SPY_MOMENTUM_ADX25 | 15,676 / -57,883 | 11,169 / -53,026 | 8,895 / -47,056 | 7,606 / -50,527 | 6,673 / -47,370 | 6,037 / -46,523 |
| SPY_GAP_CONT_50 | 6,275 / -23,359 | 4,370 / -19,923 | 3,413 / -18,115 | 2,787 / -17,053 | 2,389 / -15,776 | 2,104 / -15,805 |

Trade counts rise as the horizon shortens because one position at a time is a live rule: a 5-minute clock is free to take the next signal while a 30-minute clock is still holding the first.

