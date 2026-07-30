"""Run the options scanner for every active ticker in tracked configuration."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import ford_scan

ROOT = Path(__file__).resolve().parent
TICKER_CONFIG_PATH = ROOT / "config" / "tickers.json"


def configured_active_tickers() -> list[str]:
    payload = json.loads(TICKER_CONFIG_PATH.read_text(encoding="utf-8"))
    active: list[str] = []
    for item in payload.get("tickers") or []:
        ticker = str(item.get("ticker") or "").strip().upper()
        status = str(item.get("status") or "").upper()
        resume_on = str(item.get("resume_on") or "")
        resumed = status == "PAUSED" and resume_on and resume_on <= date.today().isoformat()
        if ticker and (status == "ACTIVE" or resumed):
            active.append(ticker)
    if "F" in active:
        active = [ticker for ticker in active if ticker != "F"] + ["F"]
    return list(dict.fromkeys(active))


def main() -> int:
    tickers = configured_active_tickers()
    if not tickers:
        print("No active tickers are configured.")
        return 0
    original_ticker = ford_scan.TICKER
    original_bot_token = ford_scan.DISCORD_BOT_TOKEN
    original_webhook = ford_scan.DISCORD_WEBHOOK_URL
    results: dict[str, int] = {}
    try:
        for ticker in tickers:
            ford_scan.TICKER = ticker
            ford_scan.DISCORD_BOT_TOKEN = (
                original_bot_token if ticker == "F" else ""
            )
            ford_scan.DISCORD_WEBHOOK_URL = (
                original_webhook if ticker == "F" else ""
            )
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
