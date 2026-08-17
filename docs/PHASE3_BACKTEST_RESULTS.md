# Phase 3 - Underlying Backtest Results

Generated from `minute_features` over **3,347 sessions** (2008-01-22 - 2021-05-06). Every number below is the **SPY underlying**, measured in ATR multiples. There is no option P/L here - that is Phase 5, and mixing the two would misreport what was actually tested.

**Nothing is eliminated.** Every variant tested is listed, including the losing ones. Where a strategy does not work, that is the finding.

## The comparison that matters

Random entries on the same bars, under the same exit policy search, return **-0.0002 ATR/trade** (48.8% win rate over 6,133 trades).

That is the bar. A strategy beating zero but not beating this has shown nothing - it is being carried by the same drift and exit geometry the random control gets for free.


## Best exit policy per variant

Exit labels read `t<target>/s<stop>/m<time-stop>`, all in ATR multiples. `t` is the t-statistic of the expectancy against zero; **|t| >= 1.96 is the 95% threshold**. Per-trade P/L scatters about +-1 ATR, so a few hundred trades cannot resolve an edge of a few hundredths - most rows below are statistically indistinguishable from a coin flip, and the column says so.

| Strategy | Variant | Best exit | Trades | Win% | Expectancy (ATR) | t | Sig? | PF | MaxDD | vs random |
|---|---|---|---|---|---|---|---|---|---|---|
| S10 VWAP reversion | 0.5atr | `t1.0/s0.75/m-` | 420 | 52.1% | +0.0284 | +1.37 | no | 1.19 | -10.7 | +0.0286 |
| S2 ORB immediate | or5 | `t1.0/s0.75/m-` | 1,565 | 50.5% | +0.0251 | +1.75 | no | 1.11 | -11.9 | +0.0254 |
| S4 VWAP reclaim | chop<=2 | `t2.0/s1.0/m-` | 2,164 | 49.8% | +0.0217 | +1.78 | no | 1.11 | -17.1 | +0.0219 |
| S1 ORB retest | or5 | `t2.0/s1.0/m-` | 3,198 | 50.0% | +0.0172 | +1.74 | no | 1.08 | -25.5 | +0.0175 |
| S3 VWAP pullback | zoneC 0.50atr | `t2.0/s1.0/m-` | 3,489 | 51.0% | +0.0143 | +1.53 | no | 1.07 | -28.0 | +0.0146 |
| S3 VWAP pullback | zoneB 0.25atr | `t2.0/s1.0/m-` | 3,392 | 51.1% | +0.0142 | +1.49 | no | 1.07 | -21.8 | +0.0144 |
| S4 VWAP reclaim | chop<=5 | `t1.0/s0.75/m-` | 3,249 | 48.9% | +0.0087 | +0.96 | no | 1.04 | -28.7 | +0.0089 |
| S4 VWAP reclaim | chop<=3 | `t1.0/s0.75/m-` | 2,761 | 48.5% | +0.0084 | +0.85 | no | 1.04 | -20.2 | +0.0086 |
| S4 VWAP reclaim | chop<=4 | `t1.0/s0.75/m-` | 3,105 | 48.7% | +0.0072 | +0.78 | no | 1.04 | -28.6 | +0.0074 |
| S3 VWAP pullback | zoneA vwap | `t1.0/s0.75/m-` | 2,374 | 51.4% | +0.0066 | +0.70 | no | 1.04 | -23.9 | +0.0068 |
| S2 ORB immediate | or30 | `t2.0/s1.0/m-` | 1,472 | 48.0% | +0.0027 | +0.17 | no | 1.01 | -19.8 | +0.0029 |
| S2 ORB immediate | or15 | `t0.5/s0.5/m-` | 1,506 | 50.7% | +0.0011 | +0.10 | no | 1.01 | -10.1 | +0.0013 |
| S1 ORB retest | or15 | `t1.0/s0.75/m-` | 3,324 | 48.5% | +0.0001 | +0.01 | no | 1.00 | -34.2 | +0.0003 |
| S1 ORB retest | or30 | `t2.0/s1.0/m-` | 3,267 | 48.3% | -0.0001 | -0.01 | no | 1.00 | -34.3 | +0.0002 |
| BASELINE random | 2/session | `t0.5/s0.5/m30` | 6,133 | 48.8% | -0.0002 | -0.12 | no | 1.00 | -13.1 |  |
| S10 VWAP reversion | 0.75atr | `t1.0/s0.75/m15` | 88 | 50.0% | -0.0245 | -1.44 | no | 0.67 | -3.2 | -0.0242 |

## Verdict

- **0 of 15 variants** clear statistical significance at 95% AND beat the random baseline.
- **0 of 15 variants** are profitable in every one of the four eras.


No variant in this tranche produced an edge that is distinguishable from noise on this data. The best expectancies are a few hundredths of an ATR per trade with t-statistics well under 2 - which is what a coin flip looks like when you measure it a few thousand times.

That is a real result, not a failure of the test. It says the ORB and VWAP families **as literally specified** do not, on their own, predict the SPY underlying over 2008-2021. The spec's own instinct was right: it repeatedly insists the filters matter as much as the pattern. This tranche deliberately ran them with light filtering to establish that baseline first, so later phases can show whether a filter adds anything real rather than merely appearing to.


The t-statistics above are also **optimistic by construction**: each row is the best of 12 exit policies for that variant, so the selection has already had 12 chances to find a favourable draw. Correcting for that search would push every one of them further toward zero, not away from it. Treat the column as an upper bound.


One pattern is consistent enough to call out: **every leading variant loses money in the 2020-2021 era**, the most recent one available. Whether that is COVID-era distortion or genuine edge decay cannot be settled here - and the 2021-2026 gap in the intraday data means it cannot be settled at all until that gap is filled.


## Walk-forward: does it hold across eras?

A strategy that only works in one era is an artefact of that era. These are the same trades split by period, never refitted.


### BASELINE random | 2/session

| Era | Trades | Win% | Expectancy (ATR) | PF | MaxDD |
|---|---|---|---|---|---|
| 2008-2011 crisis+recovery | 1,841 | 47.3% | -0.0048 | 0.92 | -10.6 |
| 2012-2015 low-vol bull | 1,844 | 48.6% | +0.0038 | 1.07 | -4.3 |
| 2016-2019 late bull | 1,837 | 50.6% | +0.0025 | 1.04 | -7.5 |
| 2020-2021 covid era | 611 | 48.6% | -0.0068 | 0.89 | -8.3 |

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

## Every combination tested

216 (variant x exit-policy) pairs. Listed in full so the size of the search is visible - a best result picked from a large grid deserves more scepticism than one picked from a small grid.

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

## Method and its limits

- Signals evaluate on a closed bar; fills happen at the **next** bar's open.
- When a bar contains both the stop and the target, the **stop** is taken - 1-minute OHLC cannot resolve the order, and assuming otherwise inflates results.
- One position at a time, forced flat at 15:59.
- No commission or slippage is modelled yet. Real fills are worse than these.
- Expectancy is in ATR, not dollars, so 2008 and 2021 are comparable.
- **This measures the underlying entry only.** A positive underlying edge is a necessary but not sufficient condition for a profitable 0DTE option trade; theta and spread can erase a real move. Phase 5 models that separately.

