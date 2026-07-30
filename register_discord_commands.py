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
    for command in COMMANDS:
        response = requests.post(url, headers=headers, json=command, timeout=20)
        if not response.ok:
            print(
                f"Failed to register /{command['name']}: "
                f"HTTP {response.status_code} {response.text[:500]}",
                file=sys.stderr,
            )
            return 1
        print(f"Registered /{command['name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

