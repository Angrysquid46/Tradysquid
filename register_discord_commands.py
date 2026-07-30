"""Register private guild-scoped slash commands for TradeBot."""

from __future__ import annotations

import os
import sys

import requests

APPLICATION_ID = os.environ.get("DISCORD_APPLICATION_ID", "").strip()
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

COMMANDS = [
    {
        "name": "help",
        "type": 1,
        "description": "Show every Tradysquids Ford command and how to use it",
    },
    {
        "name": "quote",
        "type": 1,
        "description": "Show the current Ford quote, volume, spread, and timestamp",
    },
    {
        "name": "trend",
        "type": 1,
        "description": "Show the full Ford technical dashboard",
    },
    {
        "name": "chart",
        "type": 1,
        "description": "Generate a current Ford price chart",
        "options": [{
            "name": "days",
            "description": "Number of trading days",
            "type": 4,
            "required": False,
            "choices": [
                {"name": "30 days", "value": 30},
                {"name": "60 days", "value": 60},
                {"name": "90 days", "value": 90},
                {"name": "120 days", "value": 120},
            ],
        }],
    },
    {
        "name": "levels",
        "type": 1,
        "description": "Show Ford trend, RSI, support, and resistance",
    },
    {
        "name": "events",
        "type": 1,
        "description": "Show official Ford events, news, and recent SEC filings",
    },
    {
        "name": "why",
        "type": 1,
        "description": "Explain the recorded rationale for a tracked Ford trade",
        "options": [{
            "name": "trade_id",
            "description": "Example: F-20260729-005",
            "type": 3,
            "required": True,
            "min_length": 10,
            "max_length": 40,
        }],
    },
    {
        "name": "chain",
        "type": 1,
        "description": "Rank liquid Ford option contracts",
        "options": [{
            "name": "side",
            "description": "Calls or puts",
            "type": 3,
            "required": False,
            "choices": [
                {"name": "Calls", "value": "call"},
                {"name": "Puts", "value": "put"},
            ],
        }],
    },
    {
        "name": "setup",
        "type": 1,
        "description": "Check the qualified Ford direction and research shortlist",
    },
    {
        "name": "watchlist",
        "type": 1,
        "description": "Show reactive Ford levels and monitored conditions",
    },
    {
        "name": "option",
        "type": 1,
        "description": "Inspect one Ford option contract",
        "options": [{
            "name": "symbol",
            "description": "Tradier OCC option symbol",
            "type": 3,
            "required": True,
            "min_length": 8,
            "max_length": 32,
        }],
    },
    {
        "name": "risk",
        "type": 1,
        "description": "Calculate long-option premium risk and management levels",
        "options": [
            {
                "name": "premium",
                "description": "Option price per share, such as 0.42",
                "type": 10,
                "required": True,
                "min_value": 0.01,
                "max_value": 100,
            },
            {
                "name": "contracts",
                "description": "Number of contracts",
                "type": 4,
                "required": False,
                "min_value": 1,
                "max_value": 100,
            },
            {
                "name": "side",
                "description": "Call or put",
                "type": 3,
                "required": False,
                "choices": [
                    {"name": "Call", "value": "call"},
                    {"name": "Put", "value": "put"},
                ],
            },
        ],
    },
    {
        "name": "performance",
        "type": 1,
        "description": "Summarize recorded Ford trade performance",
    },
    {
        "name": "status",
        "type": 1,
        "description": "Check bot, Tradier, scheduler, Discord, and SEC status",
    },
    {
        "name": "schedule",
        "type": 1,
        "description": "Show the local no-GitHub monitoring schedule",
    },
    {
        "name": "dataage",
        "type": 1,
        "description": "Show the age of locally cached Ford information",
    },
    {
        "name": "lastscan",
        "type": 1,
        "description": "Show recent local monitoring job results",
    },
    {
        "name": "filings",
        "type": 1,
        "description": "Show recent official Ford SEC filings",
    },
    {
        "name": "calendar",
        "type": 1,
        "description": "Show Ford event links and recent material filings",
    },
    {
        "name": "explain",
        "type": 1,
        "description": "Explain an options or technical-analysis term",
        "options": [{
            "name": "topic",
            "description": "Delta, theta, IV, spread, open interest, DTE, RSI, or ATR",
            "type": 3,
            "required": True,
            "choices": [
                {"name": "Delta", "value": "delta"},
                {"name": "Theta", "value": "theta"},
                {"name": "Implied volatility", "value": "iv"},
                {"name": "Bid/ask spread", "value": "spread"},
                {"name": "Open interest", "value": "open-interest"},
                {"name": "Days to expiration", "value": "dte"},
                {"name": "RSI", "value": "rsi"},
                {"name": "ATR", "value": "atr"},
            ],
        }],
    },
]


def main() -> int:
    missing = [
        name for name, value in (
            ("DISCORD_APPLICATION_ID", APPLICATION_ID),
            ("DISCORD_BOT_TOKEN", BOT_TOKEN),
            ("DISCORD_GUILD_ID", GUILD_ID),
        )
        if not value
    ]
    if missing:
        print("Missing environment values: " + ", ".join(missing), file=sys.stderr)
        return 1
    url = (
        f"https://discord.com/api/v10/applications/{APPLICATION_ID}"
        f"/guilds/{GUILD_ID}/commands"
    )
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
    }
    # Discord's bulk-overwrite endpoint registers the complete guild command
    # set in one request. This avoids a burst of POST requests and removes
    # commands that no longer exist in COMMANDS.
    response = requests.put(url, headers=headers, json=COMMANDS, timeout=30)
    if not response.ok:
        print(
            f"Failed to register command set: "
            f"HTTP {response.status_code} {response.text[:500]}",
            file=sys.stderr,
        )
        return 1
    registered = response.json()
    if not isinstance(registered, list):
        print("Discord returned an unexpected command response.", file=sys.stderr)
        return 1
    names = {str(command.get("name") or "") for command in registered}
    expected = {str(command["name"]) for command in COMMANDS}
    if names != expected:
        print(
            "Discord command verification mismatch: "
            f"expected {sorted(expected)}, received {sorted(names)}",
            file=sys.stderr,
        )
        return 1
    print(f"Registered and verified {len(registered)} guild commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
