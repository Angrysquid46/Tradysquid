# Every Variant Through the Option Layer

Every strategy variant through the option layer, with corrected costs.

Two corrections since the last run:

* Commission was $0.65/contract each way - roughly 16x what this account
  pays. On a $115 contract that is 1.13% of position per round trip
  instead of 0.07%, charged against strategies whose entire edge is a few
  percent. It flipped Gap continuation >=1.0% from -$23,091 to +$24,595.
* The spread figure I had been quoting (4.6% of mid) was measured across
  every 0DTE contract in the chain, including expiring OTM ones with 58%
  spreads that the delta 0.40-0.60 filter would never select. On
  contracts actually tradeable it is 2.5%.

Ranked by DOLLARS PER TRADE, not by total. Total P/L mostly measures how
often a strategy trades: -$31/trade over 16,065 trades is -$497k, while
+$16/trade over 1,547 trades is +$25k, and the second is the better
strategy despite the smaller headline. Sample size is shown next to every
row because several apparent winners rest on ~12 trades.



| Strategy | Trades | $/trade | Total $ | Win% | PF |
|---|---|---|---|---|---|
| S11 Compression break | 10bars quiet | 1 | +238.81 | +239 | 100.0 | inf |
| S15 Momentum exhaustion | 1.0atr ext | 11 | +151.51 | +1,667 | 63.6 | 2.72 |
| PB1 Opening gap fade | spec thresholds | 13 | +98.95 | +1,286 | 53.8 | 1.84 |
| S2 ORB immediate | or30 | 383 | +18.69 | +7,157 | 43.3 | 1.13 |
| S21 Gap continuation | gap>=1.0% | 1,547 | +15.90 | +24,595 | 45.4 | 1.11 |
| S5 Premarket breakout | retest | 313 | +14.31 | +4,480 | 45.7 | 1.10 |
| S11 Compression break | 5bars quiet | 21 | +10.10 | +212 | 47.6 | 1.07 |
| S18 Time-of-day | FINAL_30 | 281 | +9.33 | +2,623 | 44.8 | 1.06 |
| S5 Premarket breakout | immediate | 142 | +5.02 | +713 | 41.5 | 1.03 |
| S11 Compression break | 3bars quiet | 158 | +0.68 | +107 | 46.8 | 1.00 |
| S22 Gap fade | gap>=1.0% | 1,575 | -0.76 | -1,201 | 41.7 | 1.00 |
| S21 Gap continuation | gap>=0.5% | 4,042 | -1.81 | -7,308 | 42.9 | 0.99 |
| PB2 Momentum squeeze | eff>=0.75 | 2 | -3.23 | -6 | 50.0 | 0.98 |
| S8 Liquidity sweep | reclaim<=5bars | 793 | -3.45 | -2,733 | 43.0 | 0.98 |
| S12 First pullback | 0.5atr drive | 56 | -3.67 | -206 | 44.6 | 0.98 |
| S2 ORB immediate | or15 | 392 | -5.22 | -2,046 | 40.6 | 0.96 |
| S7 Failed breakout | prev-day levels | 1,229 | -5.90 | -7,249 | 42.2 | 0.96 |
| S18 Time-of-day | MORNING | 2,755 | -9.34 | -25,719 | 42.0 | 0.94 |
| S8 Liquidity sweep | reclaim<=3bars | 649 | -10.09 | -6,551 | 43.1 | 0.93 |
| S10 VWAP reversion | 0.5atr | 253 | -10.35 | -2,618 | 41.5 | 0.94 |
| S8 Liquidity sweep | reclaim<=10bars | 972 | -10.70 | -10,397 | 41.8 | 0.93 |
| S18 Time-of-day | OPEN | 2,620 | -11.06 | -28,969 | 41.9 | 0.93 |
| S22 Gap fade | gap>=0.5% | 3,740 | -11.78 | -44,047 | 40.5 | 0.93 |
| S3 VWAP pullback | zoneA vwap | 939 | -12.07 | -11,330 | 41.2 | 0.92 |
| S21 Gap continuation | gap>=0.25% | 6,763 | -12.27 | -82,997 | 41.4 | 0.92 |
| S6 Prev-day breakout | immediate | 725 | -12.38 | -8,977 | 41.8 | 0.92 |
| S1 ORB retest | or5 | 1,731 | -12.48 | -21,604 | 41.0 | 0.92 |
| S2 ORB immediate | or5 | 418 | -15.52 | -6,486 | 40.7 | 0.90 |
| LIVE SPY_0DTE (ORB) | 5-min bars (5M) | 11,767 | -16.39 | -192,828 | 40.4 | 0.90 |
| S18 Time-of-day | MIDMORNING | 4,409 | -17.01 | -75,006 | 41.0 | 0.89 |
| S22 Gap fade | gap>=0.25% | 6,712 | -18.01 | -120,901 | 39.8 | 0.89 |
| S13 Structure reversal | vwap confirmed | 5,226 | -20.73 | -108,311 | 40.2 | 0.87 |
| S16 Confluence | 4+ levels | 5,229 | -21.11 | -110,368 | 39.7 | 0.87 |
| S6 Prev-day breakout | retest | 1,155 | -21.30 | -24,603 | 39.4 | 0.87 |
| S4 VWAP reclaim | chop<=2 | 618 | -21.64 | -13,373 | 39.8 | 0.86 |
| S13 Structure reversal | no vwap filter | 8,180 | -22.06 | -180,440 | 40.0 | 0.86 |
| LIVE SPY_0DTE (ORB) | 1-min bars (1M + 10 ratchets) | 16,538 | -22.46 | -371,379 | 39.5 | 0.87 |
| BASELINE random | 2/session | 1,388 | -22.71 | -31,521 | 39.5 | 0.85 |
| S16 Confluence | 3+ levels | 10,593 | -23.44 | -248,260 | 39.5 | 0.86 |
| S9 Range reversal | unfiltered | 8,497 | -24.30 | -206,455 | 39.6 | 0.85 |
| S4 VWAP reclaim | chop<=5 | 1,520 | -24.42 | -37,120 | 39.5 | 0.84 |
| S16 Confluence | 2+ levels | 16,089 | -24.51 | -394,405 | 39.3 | 0.85 |
| S3 VWAP pullback | zoneC 0.50atr | 11,565 | -24.85 | -287,365 | 39.1 | 0.85 |
| S3 VWAP pullback | zoneB 0.25atr | 9,221 | -24.91 | -229,659 | 39.1 | 0.85 |
| S17 Expected-move | <50% used | 8,585 | -25.27 | -216,965 | 39.1 | 0.84 |
| S19 MTF breakout | 3/4 agree | 10,415 | -25.34 | -263,942 | 39.0 | 0.85 |
| S19 MTF breakout | 2/4 agree | 18,873 | -25.64 | -483,887 | 39.1 | 0.85 |
| S18 Time-of-day | MIDDAY | 7,008 | -25.92 | -181,630 | 39.3 | 0.84 |
| S14 Momentum continuation | adx25 aligned | 5,969 | -26.09 | -155,759 | 38.4 | 0.84 |
| S9 Range reversal | range-filtered | 5,652 | -26.34 | -148,848 | 39.5 | 0.84 |
| S4 VWAP reclaim | chop<=3 | 953 | -26.38 | -25,137 | 39.0 | 0.83 |
| S17 Expected-move | <125% used | 18,094 | -27.17 | -491,596 | 38.8 | 0.84 |
| S14 Momentum continuation | adx20 aligned | 8,146 | -27.88 | -227,124 | 38.4 | 0.83 |
| S17 Expected-move | <75% used | 13,692 | -28.81 | -394,456 | 38.6 | 0.83 |
| S17 Expected-move | <100% used | 16,669 | -29.01 | -483,591 | 38.6 | 0.83 |
| S4 VWAP reclaim | chop<=4 | 1,234 | -29.18 | -36,005 | 38.7 | 0.82 |
| S14 Momentum continuation | adx25 unaligned | 10,083 | -29.39 | -296,333 | 38.1 | 0.82 |
| S12 First pullback | 0.75atr drive | 12 | -30.12 | -361 | 41.7 | 0.79 |
| S14 Momentum continuation | adx30 aligned | 4,160 | -30.64 | -127,445 | 37.5 | 0.82 |
| LIVE SPY_KEY_LEVELS | deployed rules | 16,065 | -30.95 | -497,258 | 38.2 | 0.82 |
| S1 ORB retest | or30 | 2,033 | -32.45 | -65,970 | 38.5 | 0.80 |
| S19 MTF breakout | 4/4 agree | 2,601 | -32.78 | -85,260 | 37.9 | 0.81 |
| LIVE SPY_EXPANSION_LEVEL | deployed rules | 605 | -33.05 | -19,996 | 39.2 | 0.80 |
| S18 Time-of-day | AFTERNOON | 8,976 | -33.22 | -298,159 | 38.1 | 0.81 |
| S1 ORB retest | or15 | 1,904 | -35.93 | -68,410 | 37.9 | 0.78 |
| S10 VWAP reversion | 0.75atr | 18 | -36.65 | -660 | 38.9 | 0.78 |
| S10 VWAP reversion | 1.0atr | 2 | -48.31 | -97 | 50.0 | 0.72 |
| PB2 Momentum squeeze | eff>=0.65 | 21 | -72.54 | -1,523 | 33.3 | 0.60 |
| S12 First pullback | 1.0atr drive | 5 | -265.29 | -1,326 | 0.0 | 0.00 |
| PB2 Momentum squeeze | eff>=0.85 | 1 | -266.06 | -266 | 0.0 | 0.00 |
