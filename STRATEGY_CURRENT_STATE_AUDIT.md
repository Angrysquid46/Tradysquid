# Tradysquid Current Strategy Audit

This document records the paper-trading behavior that exists before the editable
strategy engine is introduced. It distinguishes implemented behavior from
planned behavior so later profile work cannot quietly rewrite history.

## Runtime boundary

The current scanner and position evaluator remain authoritative in PR 1. The new
strategy profiles are read-only descriptions of that behavior. No profile value
changes qualification, entry, management, or exit until the runtime-consumption
phase is separately implemented, tested, deployed, and acknowledged.

The automatic updater, supervisor, watchdog, rollback system, startup tasks,
ngrok supervision, runtime contract, and deployment workflows are outside the
strategy platform and remain frozen.

## Current lifecycle

```text
Dynamic universe
  -> market-regime gate
  -> option-chain retrieval
  -> liquidity / DTE / delta / risk filters
  -> candidate score and ranking
  -> duplicate / cooldown rejection
  -> every remaining eligible candidate becomes a paper trade
  -> canonical CSV row and Discord journal
  -> repeated option repricing
  -> MFE / MAE tracking
  -> static target, static stop, or expiration close
  -> result routing, exit snapshot, and post-trade review
```

## Shared qualification behavior

- Paper trading only. No brokerage orders are placed.
- The market regime uses daily SMA20/SMA50 and RSI14 plus intraday evidence.
- Regimes are `BULLISH / CONTROLLED`, `BEARISH / CONTROLLED`,
  `NEUTRAL / RANGE`, or `NO TRADE`.
- Missing required market history blocks qualification.
- Long calls are considered in bullish controlled conditions.
- Long puts are considered in bearish controlled conditions.
- Swing bull-put spreads are considered in bullish conditions.
- Swing bear-call spreads are considered in bearish conditions.
- Neutral/range swing conditions may consider call- or put-credit spreads.
- Candidate score is a ranking value, not a win probability.
- Every eligible non-duplicate candidate is currently opened as a paper trade;
  there is no profile-specific maximum selected-candidate count.

## Current profile matrix

| Profile | Identity | DTE | Direction / structure | Entry technical model | Current management | Current exit |
|---|---|---:|---|---|---|---|
| `regular-call` | REGULAR call | 7-20 | Long call | Shared bullish regime gate; liquidity, delta, price, and risk filters | Quote polling; MFE/MAE only | +20% target, -15% stop, expiration close |
| `regular-put` | REGULAR put | 7-20 | Long put | Shared bearish regime gate; liquidity, delta, price, and risk filters | Quote polling; MFE/MAE only | +20% target, -15% stop, expiration close |
| `swing-call` | SWING call | 21-45 | Long call | Same long-call qualification model with later expiration | Quote polling; MFE/MAE only | +20% target, -15% stop, expiration close |
| `swing-put` | SWING put | 21-45 | Long put | Same long-put qualification model with later expiration | Quote polling; MFE/MAE only | +20% target, -15% stop, expiration close |
| `bull-put-spread` | SPREAD put | 21-45 | Bull put credit spread | Bullish regime; short-delta, liquidity, credit, width, and modeled-risk filters | Cost-to-close polling; MFE/MAE only | 50% credit capture, 2x-credit stop, close by 5 DTE |
| `bear-call-spread` | SPREAD call | 21-45 | Bear call credit spread | Bearish regime; short-delta, liquidity, credit, width, and modeled-risk filters | Cost-to-close polling; MFE/MAE only | 50% credit capture, 2x-credit stop, close by 5 DTE |

## Current contract filters

Long options currently use:

- absolute delta: 0.20-0.80;
- minimum open interest: 100;
- minimum daily option volume: 1;
- maximum bid/ask width: 25% of midpoint;
- maximum contract ask: $1.00;
- maximum modeled paper risk: $100;
- strike band: within 12% of spot;
- duplicate / reentry cooldown: 24 hours.

Credit spreads currently use:

- short-leg absolute delta: 0.10-0.25;
- the same per-leg liquidity test;
- minimum credit: $0.05;
- adjacent long leg;
- modeled maximum risk no greater than $100.

## Current journal and evidence behavior

Each canonical trade row can store:

- trade ID;
- play type and direction;
- contract and quote evidence;
- Greeks and liquidity;
- setup score and reason;
- market regime;
- thesis;
- entry confirmation;
- invalidation;
- risk plan;
- Learning Center application;
- evidence limitations and confidence;
- current P&L, MFE, and MAE;
- lifecycle signal and closing result.

Discord journal validation requires visible entry-plan, risk, qualification,
Learning Center, evidence, and post-trade fields. Historical missing evidence is
reported as unavailable rather than invented.

Entry, material-HOLD, and exit snapshots use recorded source bars and display
5-minute, daily, weekly, and monthly views when data is available.

## Implemented versus merely described

### Implemented now

- Shared regime classification.
- DTE, delta, liquidity, contract-price, and risk filters.
- Candidate ranking.
- Duplicate and cooldown rejection.
- Paper entry creation and canonical trade IDs.
- Repricing of open positions.
- MFE and MAE recording.
- Static profit, stop, and expiration exits.
- Discord journals and source-bar snapshots.
- Global Discord settings for the current shared targets, stops, and risk limits.

### Stored in journals but not fully enforced as exit logic

- Thesis invalidation prose.
- Entry confirmation prose beyond the scanner qualification result.
- Regime no longer supporting the trade.
- Learning Center management concepts.

The current evaluator does not close a trade because a configurable moving
average crossed, RSI weakened, support failed, momentum decayed, or a thesis
state changed. Those are future strategy-engine rules, not current behavior.

### Not implemented yet

- Unique technical logic per profile.
- Editable SMA/EMA periods and timeframes.
- Configurable rule groups.
- Profile-specific break-even activation.
- Profit-zone and MFE-giveback protection.
- Momentum-loss exits.
- Technical-invalidation exits.
- Versioned runtime consumption and acknowledgements.
- Admin editing cards.
- Per-trade overrides.
- Assistant-to-bot strategy change queue.
- Strategy-version learning recommendations.
- Option-mark lifecycle charts with active stop and trailing levels.

## Known weakness motivating the roadmap

A long option may reach a useful profit below +20%, receive no protection, and
then decline to the -15% stop. The system records MFE after the fact but does not
currently use MFE to protect gains. Regular and swing trades also share the same
static exit percentages despite different holding horizons.

PR 1 records that weakness without changing it. Later chunks must introduce new
behavior through versioned profiles, focused tests, runtime acknowledgements,
and live proof, one controlled feature layer at a time.
