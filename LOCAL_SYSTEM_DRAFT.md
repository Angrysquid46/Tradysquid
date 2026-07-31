# Local System Draft

This replacement is assembled locally and is not live until it is reviewed,
published, and the launcher is restarted.

## One-click process

`START-TRADYSQUID.bat` starts the Discord/signal gateway, local scheduler, and
ngrok tunnel, then opens the working pages. The scheduler is the primary runtime;
GitHub Actions remains a manual backup.

## Runtime cadence

- Provider event queue: every 15 seconds.
- Open paper positions: every 30 seconds during market hours.
- Full options discovery: rotating batch every 15 minutes during market hours.
- Universe quote/liquidity refresh: hourly, or every two hours after market.
- Health: every 15 minutes.
- Outcome-learning archive: every six hours.
- Weekly evidence review: Friday after the market.

The Discord publisher should edit existing held-position cards on material
changes and heartbeat intervals, rather than post a new message every 30 seconds.

## TradingView webhook

Set a long random `TRADINGVIEW_WEBHOOK_SECRET` in the local `.env`. Configure a
TradingView alert to POST JSON to:

`https://YOUR-NGROK-DOMAIN/tradingview?secret=YOUR_SECRET`

Example body:

```json
{
  "id": "{{ticker}}-{{time}}-breakout",
  "ticker": "{{exchange}}:{{ticker}}",
  "event": "breakout",
  "price": "{{close}}",
  "interval": "{{interval}}"
}
```

The endpoint validates the secret, limits payload size, normalizes the symbol,
deduplicates the event, returns HTTP 202, and raises that symbol's local scan
priority. It never places a trade.

## Robinhood MCP boundary

Robinhood integration is intentionally an adapter boundary until its MCP server
is authenticated. Accepted capabilities are quotes, market data, option chains,
and watchlists. Orders, trades, write-position actions, transfers, buys, and
sells are blocked. Read-only discovery snapshots can be imported through
`dynamic_universe.import_robinhood_snapshot`.

## Provider and safety controls

- Tradier remains the authoritative live option-chain validator.
- The universe rotates in small batches to avoid provider bursts.
- Single-leg ask and total risk cannot exceed $1.00/$100.
- Defined-risk spread maximum loss cannot exceed $100.
- No brokerage order API exists in the runtime.
- Configuration changes are local and owner-only; they never auto-commit.
- Learning output can recommend a review but cannot change filters.
