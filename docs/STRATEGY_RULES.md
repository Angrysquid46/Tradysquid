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
| 11 | **SPY_EXHAUSTION_1ATR** | `momentum_exhaustion` | +115% / -75%, 30min | 2 bar(s) | `s11-exhaustion-1atr` | yes |
| 12 | **SPY_FIRST_PULLBACK** | `first_pullback_after_drive` | +75% / -58% | 1 bar(s) | `s12-first-pullback` | yes |
| 13 | **SPY_OPENING_GAP_FADE** | `playbook_opening_gap_fade` | +115% / -75%, 15min | 1 bar(s) | `s13-opening-gap-fade` | yes |
| 14 | **SPY_KEY_LEVELS** | live level/VWAP/ORB read in `spy_scanner` | **underlying** stop 0.45% / target 2.0R | n/a (state, not a bar event) | `s14-key-levels` | yes |
| 15 | **SPY_COMPRESSION_3BAR** | `compression_breakout` | +115% / -75% | 2 bar(s) | `s15-compression-3bar` | yes |

## What each strategy trades

**SPY_GAP_CONT_50** - Gap continuation. SPY gaps at least 0.5% at the open; trade in the direction of the gap, betting the move keeps going rather than fills.

**SPY_FAILED_BREAK** - Failed breakout reversal. Price breaks a prior-day level, fails to hold it, and reverses back through - trade the reversal, not the break.

**SPY_ORB_IMMEDIATE** - Opening-range breakout taken on the breakout bar ITSELF, not on a retest. Fires once per session per direction. Needs relative volume at or above 1.0, so it will not chase a quiet break.

**SPY_SWEEP_10** - Liquidity sweep. A stricter failed breakout: price must poke through the level and reclaim it QUICKLY - within 10 bars. A slow grind back is acceptance, not a sweep, and that distinction is the whole idea.

**SPY_VWAP_RECLAIM** - Lose VWAP, reclaim it, hold the retest, then break the pullback high. A chop filter rejects the setup once SPY has crossed VWAP too many times that session, since repeated crosses mean no one is in control.

**SPY_MOMENTUM_ADX25** - Momentum, small consolidation, then the continuation break - deliberately NOT the largest candle. Requires ADX at or above 25 so it only trades when a trend is actually established.

**SPY_TOD_MIDDAY** - The same momentum rule as ADX25, restricted to the midday session. SPY does not behave identically all day; this holds the rule fixed and varies only the clock.

**SPY_CONFLUENCE_4** - Four or more independent references stacked at one price, THEN confirmation. Touching four levels is explicitly not itself a trade - the confirming break is required.

**SPY_TOD_FINAL30** - The momentum rule restricted to the final 30 minutes. Its 30-minute time stop is redundant in practice: the closing bell always arrives first.

**SPY_MTF_4OF4** - Breakout requiring all four tracked timeframes to agree. The strictest of the multi-timeframe variants - 2-of-4 and 3-of-4 also exist and were not promoted.

**SPY_EXHAUSTION_1ATR** - Momentum exhaustion. Price stretches far from VWAP, market structure turns against it, and the bar closes through the prior bar's extreme - fade the overextension. A reversal snap: if it has not snapped back within 30 minutes the thesis was wrong, which is what the time stop enforces.

**SPY_FIRST_PULLBACK** - Strong drive off the open, then the FIRST controlled pullback - explicitly not chasing the drive itself. Takes one trade per session.

**SPY_OPENING_GAP_FADE** - Fade the opening gap, strictly between 09:45 and 10:00. Needs a gap of 0.4% or more, a volume z-score above 1.5, momentum already flipped against the gap, and the bar closing at the extreme of its own range. Rare by construction.

**SPY_KEY_LEVELS** - Price trading at a key level - prior-day, premarket, opening-range or VWAP - with 1/3/5-minute direction agreeing, plus its own economic catalyst check. The only strategy that exits on the UNDERLYING (stop at the level, target at 2R) rather than on option premium.

**SPY_COMPRESSION_3BAR** - Quiet range, then a bar that expands out of it. Three bars of compression is the trigger; the 5- and 10-bar variants exist and were not promoted because their samples are 21 and 1 trade.

## Measured performance

Each strategy under **its own** exit rules, one contract, $0.04/contract commission. Break-even win rate is set by the exit's payoff ratio - a strategy is profitable exactly when its win rate clears it.

| Strategy | Trades | Win% | Break-even | $/trade |
|---|---|---|---|---|
| SPY_GAP_CONT_50 | 406 | 26.6% | 41.8% | -29.90 |
| SPY_FAILED_BREAK | 653 | 21.1% | 46.4% | -34.18 |
| SPY_ORB_IMMEDIATE | 511 | 24.5% | 40.3% | -30.34 |
| SPY_SWEEP_10 | 568 | 18.5% | 43.7% | -34.81 |
| SPY_VWAP_RECLAIM | 637 | 21.0% | 43.3% | -41.19 |
| SPY_MOMENTUM_ADX25 | 1,715 | 22.3% | 42.5% | -29.05 |
| SPY_TOD_MIDDAY | 1,078 | 17.3% | 45.3% | -39.34 |
| SPY_CONFLUENCE_4 | 825 | 19.9% | 45.0% | -39.55 |
| SPY_TOD_FINAL30 | 482 | 26.1% | 42.8% | -6.33 |
| SPY_MTF_4OF4 | 766 | 17.0% | 45.2% | -32.91 |
| SPY_EXHAUSTION_1ATR | 351 | 31.9% | 43.5% | -5.74 |
| SPY_FIRST_PULLBACK | 429 | 27.7% | 42.2% | -20.14 |
| SPY_OPENING_GAP_FADE | 14 | 42.9% | 48.7% | -3.09 |
| SPY_KEY_LEVELS | 4,755 | 29.6% | 47.9% | -12.36 |
| SPY_COMPRESSION_3BAR | 192 | 17.2% | 46.0% | -27.15 |

## Rules that apply to every strategy

- **One position at a time.** A strategy holding a trade is skipped entirely by the entry scan until it closes.
- **One contract per trade**, so risk is `ask x 100` - between about $1 and $500, never more. The backtest sizes the same way.
- **Scanned every minute** during market hours, with a per-strategy lookback so a signal is still caught when a cycle runs late. Capture is 100%.
- **`POSITION_FILE_LOCK` is never held across network I/O**, so entry scanning cannot delay an exit.
- **Each strategy has its own channel, its own ledger and its own backtest card.** Nothing shares an exit or a signal.
## Known limits

- **Premarket-based strategies cannot work**: `premarket_high/low/range` are 0% populated on recent sessions and the live feature builder never constructs them. S5 Premarket Breakout scored well and was rejected for this reason.

