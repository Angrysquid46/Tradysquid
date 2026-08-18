# Each Strategy With Its Own Exit Rules

Each strategy through the option layer using ITS OWN exit rules.

Every option run before this one imposed a single +50/-50 exit on all 13
strategies. They do not use that shape - NEW_STRATEGY_EXITS gives six
distinct configurations, targets from +40% to +150% and stops from -40%
to -75%. Testing them all under one exit produced a "discovery" that
every strategy shares a payoff ratio of 1.32, which was not a finding at
all: it was the imposed exit showing up in the output.

It also understated them. On one entry, sweeping the exit moved results
from +$15.90/trade at +50/-50 to +$57.81 at +150/-50 - and +150/-75 is
what most of these strategies actually run.

Owner, repeatedly: every strategy gets its own rules. This measures them
that way.



| Strategy | Exit | Trades | Win% | Payoff | BE win% | $/trade | Total |
|---|---|---|---|---|---|---|---|
| SPY_OPENING_GAP_FADE | +40/-40 | 13 | 61.5 | 2.40 | 29.4 | +10.62 | +138 |
| SPY_GAP_CONT_50 | +150/-75 | 1,743 | 42.5 | 2.19 | 31.3 | +8.47 | +14,761 |
| SPY_EXHAUSTION_1ATR | +40/-40 | 11 | 63.6 | 1.33 | 43.0 | +6.69 | +74 |
| SPY_ORB_IMMEDIATE | +115/-75 | 383 | 44.6 | 1.64 | 37.9 | +4.86 | +1,862 |
| SPY_TOD_MIDDAY | +150/-75 | 2,809 | 38.2 | 2.19 | 31.3 | +4.66 | +13,098 |
| SPY_VWAP_RECLAIM | +150/-75 | 557 | 37.5 | 2.12 | 32.1 | +4.54 | +2,530 |
| SPY_CONFLUENCE_4 | +115/-75 | 2,507 | 41.8 | 1.81 | 35.6 | +3.43 | +8,587 |
| SPY_MTF_4OF4 | +150/-75 | 1,457 | 38.0 | 2.08 | 32.4 | +3.32 | +4,833 |
| SPY_SWEEP_10 | +150/-75 | 704 | 38.4 | 2.01 | 33.2 | +3.20 | +2,250 |
| SPY_FAILED_BREAK | +115/-75 | 906 | 42.6 | 1.64 | 37.8 | +2.85 | +2,579 |
| SPY_MOMENTUM_ADX25 | +115/-75 | 5,803 | 41.2 | 1.76 | 36.2 | +2.85 | +16,513 |
| SPY_TOD_FINAL30 | +115/-75 | 281 | 44.8 | 1.51 | 39.8 | +2.00 | +562 |
| LIVE SPY_KEY_LEVELS | deployed rules | +50/-50 | 14,987 | 41.4 | 1.37 | 42.2 | -0.27 | -4,007 |
| SPY_FIRST_PULLBACK | +75/-58 | 56 | 42.9 | 1.16 | 46.4 | -2.23 | -125 |
