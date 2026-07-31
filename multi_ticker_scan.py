"""Run the options scanner for every active ticker in tracked configuration."""

from __future__ import annotations

import dynamic_universe
import ford_scan

def configured_active_tickers() -> list[str]:
    dynamic_universe.initialize()
    return dynamic_universe.next_scan_batch()


def main(tickers: list[str] | None = None) -> int:
    tickers = tickers or configured_active_tickers()
    if not tickers:
        print("No active tickers are configured.")
        return 0
    original_ticker = ford_scan.TICKER
    original_bot_token = ford_scan.DISCORD_BOT_TOKEN
    original_webhook = ford_scan.DISCORD_WEBHOOK_URL
    results: dict[str, int] = {}
    try:
        for index, ticker in enumerate(tickers):
            ford_scan.TICKER = ticker
            # Only the final pass publishes the consolidated lifecycle boards;
            # every pass still records its qualifying contracts in the shared log.
            publish = index == len(tickers) - 1
            ford_scan.DISCORD_BOT_TOKEN = original_bot_token if publish else ""
            ford_scan.DISCORD_WEBHOOK_URL = original_webhook if publish else ""
            results[ticker] = ford_scan.main()
    finally:
        ford_scan.TICKER = original_ticker
        ford_scan.DISCORD_BOT_TOKEN = original_bot_token
        ford_scan.DISCORD_WEBHOOK_URL = original_webhook
    print(
        "Multi-ticker scan results: "
        + ", ".join(
            f"{ticker}={'OK' if not result else 'FAILED'}"
            for ticker, result in results.items()
        )
    )
    return 1 if any(results.values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
