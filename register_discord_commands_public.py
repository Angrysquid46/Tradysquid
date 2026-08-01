"""Register TradeBot commands with public capped ticker add/remove access."""

from __future__ import annotations

import register_discord_commands as registry


registry.OWNER_ONLY_COMMANDS.discard("ticker-remove")

for command in registry.COMMANDS:
    name = str(command.get("name") or "")
    if name == "ticker-add":
        command["description"] = (
            "Anyone: add a verified optionable ticker, up to the 25-ticker cap"
        )
    elif name == "ticker-remove":
        command.pop("default_member_permissions", None)
        command["description"] = (
            "Anyone: remove a ticker from new scans while preserving history"
        )


if __name__ == "__main__":
    raise SystemExit(registry.main())
