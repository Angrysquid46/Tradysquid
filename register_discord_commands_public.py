"""Register TradeBot commands with public capped ticker access and free-form learning."""

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
    elif name == "explain":
        command["description"] = "Explain any options, chart, risk, or trading topic"
        options = command.get("options") or []
        if options:
            options[0].pop("choices", None)
            options[0]["description"] = (
                "Example: gamma, IV crush, credit spreads, pin risk, or expectancy"
            )
            options[0]["max_length"] = 100


if __name__ == "__main__":
    raise SystemExit(registry.main())
