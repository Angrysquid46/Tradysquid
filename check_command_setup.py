"""Validate the private local configuration used by the one-click launcher."""

from __future__ import annotations

import os

from run_with_env import load_env

REQUIRED = {
    "DISCORD_PUBLIC_KEY": "Discord Developer Portal > General Information > Public Key",
    "DISCORD_GUILD_ID": "Discord server ID",
    "TRADIER_TOKEN": "Tradier market-data token",
    "NGROK_AUTHTOKEN": "ngrok dashboard > Your Authtoken",
}


def main() -> int:
    load_env()
    missing = [
        f"  - {name}: {location}"
        for name, location in REQUIRED.items()
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        print("The one-click server is not configured yet:")
        print("\n".join(missing))
        print("\nComplete the local .env file, then double-click the launcher again.")
        return 1
    print("Private configuration check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
