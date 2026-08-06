"""Read-only check: asks Discord directly which commands are currently
registered for this guild, right now. Makes no changes - a GET request,
not the PUT that register_discord_commands.py uses. Exists purely to cut
through any uncertainty about whether a specific command actually made it
through, instead of guessing from local files."""

from __future__ import annotations

import os
import sys

import requests

from run_with_env import load_env


def main() -> int:
    load_env()
    application_id = os.environ.get("DISCORD_APPLICATION_ID", "").strip()
    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    missing = [
        name for name, value in (
            ("DISCORD_APPLICATION_ID", application_id),
            ("DISCORD_BOT_TOKEN", bot_token),
            ("DISCORD_GUILD_ID", guild_id),
        )
        if not value
    ]
    if missing:
        print("Missing environment values: " + ", ".join(missing), file=sys.stderr)
        return 1

    url = f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands"
    headers = {"Authorization": f"Bot {bot_token}"}
    response = requests.get(url, headers=headers, timeout=30)
    if not response.ok:
        print(f"HTTP {response.status_code}: {response.text[:500]}", file=sys.stderr)
        return 1

    commands = response.json()
    if not isinstance(commands, list):
        print("Unexpected response shape from Discord.", file=sys.stderr)
        return 1

    names = sorted(str(c.get("name") or "") for c in commands)
    print(f"Discord currently has {len(names)} command(s) registered for this guild:")
    for name in names:
        print(f"  {name}")
    print()
    if "reset-trading-data" in names:
        print("reset-trading-data IS in the list Discord actually has.")
    else:
        print("reset-trading-data is NOT in the list Discord actually has.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
