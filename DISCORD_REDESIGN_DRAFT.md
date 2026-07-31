# Tradysquids Discord Redesign — Local Draft

This is a review draft only. It does not create, rename, delete, or change live
Discord channels.

## START HERE

- `welcome`: purpose, paper-trading status, and navigation.
- `rules-and-risk`: educational-only disclaimer, options risk, conduct, privacy,
  no performance promises, and no trade automation.
- `how-to-use-tradebot`: public information commands and examples.

## LIVE TRADING DESK

- `scanner-feed`: every ticker inspected, why it passed or failed, and data age.
- `new-positions`: newly opened paper positions that passed every active filter.
- `held-positions`: one updating card per open paper position.
- `wins`: closed profitable paper positions.
- `losses`: every other closed paper position. There is no scratch outcome.

There is no `qualified-trades` holding area. A unique contract that qualifies
becomes a new paper position. Existing positions continue to be tracked even if
their ticker later leaves the discovery universe.

## MARKET INTELLIGENCE

- `premarket`: universe, macro calendar, earnings, gaps, and scheduled events.
- `breaking-alerts`: deduplicated TradingView/provider events.
- `charts-and-levels`: requested and scheduled charts for any active symbol.
- `news-and-events`: cached company and market news with timestamps.
- `market-regime`: broad-market context and volatility conditions.
- `universe-watch`: active symbols, discovery source, rank, and exclusions.

## PERFORMANCE

- `performance-dashboard`: lifecycle totals and recorded paper P/L.
- `strategy-results`: calls, puts, spreads, DTE, delta, and regime breakdowns.
- `ticker-results`: outcomes by underlying without ticker-specific desks.
- `learning-results`: evidence summaries; filters never change automatically.

## LEARNING CENTER

- `learning-index`: the curriculum in `LEARNING_CENTER.md`.
- `ask-tradebot`: `/ask` and `/explain` only.
- `examples-and-reviews`: anonymized paper-trade walkthroughs.

## OWNER CONTROL

- `scanner-controls`: `/filters`, `/filter-set`, universe controls, and schedules.
- `system-health`: local services, queue depth, provider freshness, and restarts.
- `workflow-log`: releases and rare GitHub backup runs.
- `upgrade-review`: suggestions receive approve/decline controls; only approved
  work is eligible for implementation.
- `security-log`: rejected webhook signatures, unauthorized admin attempts, and
  configuration warnings without exposing secrets.

## Permission model

- Members can read the information areas and speak in `general-chat`.
- Slash commands may be used only in their designated command/information areas.
- Owner-only commands change filters, universe membership, schedules, or files.
- TradingView may submit signed data events. Robinhood MCP is read-only.
- No provider is permitted to place, alter, cancel, or route a trade.
