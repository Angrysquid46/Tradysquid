# Live Strategy Rules

**Generated from the code by `strategy_rules_doc.py` - do not edit by hand.** `test_strategy_rules_doc.py` fails if this drifts from the registry, so a strategy cannot change its rules without this changing too.

Why it exists: these rules were repeatedly re-derived from scratch, and several measurements were taken against settings that were no longer live - a shared exit none of the strategies use, and ATR thresholds two of them had been recalibrated away from. Read this first.

## The roster

| # | Strategy | Signal | Exit (option premium) | Max signal age | Channel | Live |
|---|---|---|---|---|---|---|
| 1 | **SPY_GAP_CONT_50** | `gap_continuation` | +150% / -75% | 2 bar(s) | `s01-gap-cont-50` | yes |
| 2 | **SPY_FAILED_BREAK** | `failed_breakout_reversal` | +115% / -75% | 2 bar(s) | `s02-failed-break` | yes |
| 3 | **SPY_ORB_IMMEDIATE** | `orb_immediate` | +115% / -75% | 2 bar(s) | `s03-orb-immediate` | yes |
| 4 | **SPY_SWEEP_10** | `liquidity_sweep` | +150% / -75% | 2 bar(s) | `s04-sweep-10` | yes |
| 5 | **SPY_VWAP_RECLAIM** | `vwap_reclaim` | +150% / -75% | 2 bar(s) | `s05-vwap-reclaim` | yes |
| 6 | **SPY_MOMENTUM_ADX25** | `momentum_continuation` | +115% / -75% | 2 bar(s) | `s06-momentum-adx25` | yes |
| 7 | **SPY_TOD_MIDDAY** | `time_of_day_momentum` | +150% / -75% | 2 bar(s) | `s07-tod-midday` | yes |
| 8 | **SPY_CONFLUENCE_4** | `multi_level_confluence` | +115% / -75% | 2 bar(s) | `s08-confluence-4` | yes |
| 9 | **SPY_TOD_FINAL30** | `time_of_day_momentum` | +115% / -75%, 30min | 2 bar(s) | `s09-tod-final30` | yes |
| 10 | **SPY_MTF_4OF4** | `multi_timeframe_breakout` | +150% / -75% | 2 bar(s) | `s10-mtf-4of4` | yes |
| 11 | **SPY_EXHAUSTION_1ATR** | `momentum_exhaustion` | +40% / -40%, 30min | 2 bar(s) | `s11-exhaustion-1atr` | yes |
| 12 | **SPY_FIRST_PULLBACK** | `first_pullback_after_drive` | +75% / -58% | 1 bar(s) | `s12-first-pullback` | yes |
| 13 | **SPY_OPENING_GAP_FADE** | `playbook_opening_gap_fade` | +40% / -40%, 15min | 1 bar(s) | `s13-opening-gap-fade` | yes |
| 14 | **SPY_KEY_LEVELS** | live level/VWAP/ORB read in `spy_scanner` | **underlying** stop 0.45% / target 2.0R | n/a (state, not a bar event) | `s14-key-levels` | yes |
| 15 | **SPY_COMPRESSION_3BAR** | `compression_breakout` | +115% / -75% | 2 bar(s) | `s15-compression-3bar` | yes |

## Measured performance

Each strategy under **its own** exit rules, one contract, $0.04/contract commission. Break-even win rate is set by the exit's payoff ratio - a strategy is profitable exactly when its win rate clears it.

| Strategy | Trades | Win% | Break-even | $/trade |
|---|---|---|---|---|
| SPY_GAP_CONT_50 | 1,743 | 42.5% | 31.3% | +8.47 |
| SPY_FAILED_BREAK | 906 | 42.6% | 37.8% | +2.85 |
| SPY_ORB_IMMEDIATE | 383 | 44.6% | 37.9% | +4.86 |
| SPY_SWEEP_10 | 704 | 38.4% | 33.2% | +3.20 |
| SPY_VWAP_RECLAIM | 557 | 37.5% | 32.1% | +4.54 |
| SPY_MOMENTUM_ADX25 | 5,803 | 41.2% | 36.2% | +2.85 |
| SPY_TOD_MIDDAY | 2,809 | 38.2% | 31.3% | +4.66 |
| SPY_CONFLUENCE_4 | 2,507 | 41.8% | 35.6% | +3.43 |
| SPY_TOD_FINAL30 | 281 | 44.8% | 39.8% | +2.00 |
| SPY_MTF_4OF4 | 1,457 | 38.0% | 32.4% | +3.32 |
| SPY_EXHAUSTION_1ATR | 335 | 43.0% | 44.5% | -0.50 |
| SPY_FIRST_PULLBACK | 338 | 40.5% | 39.3% | +0.65 |
| SPY_OPENING_GAP_FADE | 13 | 61.5% | 29.4% | +10.62 |
| SPY_KEY_LEVELS | 1,591 | 42.4% | 21.8% | +26.86 |
| SPY_COMPRESSION_3BAR | 155 | 50.3% | 37.2% | +6.62 |

## Rules that apply to every strategy

- **One position at a time.** A strategy holding a trade is skipped entirely by the entry scan until it closes.
- **One contract per trade**, so risk is `ask x 100` - between about $1 and $500, never more. The backtest sizes the same way.
- **Scanned every minute** during market hours, with a per-strategy lookback so a signal is still caught when a cycle runs late. Capture is 100%.
- **`POSITION_FILE_LOCK` is never held across network I/O**, so entry scanning cannot delay an exit.
- **Each strategy has its own channel, its own ledger and its own backtest card.** Nothing shares an exit or a signal.

## Things that are NOT live (do not resurrect)

- The 10 ratchet variants - retired; ten channels off one signal.
- `SPY_0DTE_1M` / `SPY_0DTE_5M`, `SPY_GAP_CONT_25`, `SPY_GAP_CONT_100`, `SPY_SWEEP_5` - retired play types. Closed rows survive in the trade log and are filtered out of all reporting.
- `SPY_EXPANSION_LEVEL` - disabled.
- **Premarket-based strategies cannot work**: `premarket_high/low/range` are 0% populated on recent sessions and the live feature builder never constructs them. S5 Premarket Breakout scored well and was rejected for this reason.

