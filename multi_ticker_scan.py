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
    results: dict[str, int] = {}
    try:
        for index, ticker in enumerate(tickers):
            ford_scan.TICKER = ticker
            # Every ticker publishes its own scan, chart, and new positions.
            # Only the final pass performs shared lifecycle/performance work so
            # open positions are repriced once and consolidated cards do not spam.
            results[ticker] = ford_scan.main(
                publish_shared=index == len(tickers) - 1
            )
    finally:
        ford_scan.TICKER = original_ticker
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
