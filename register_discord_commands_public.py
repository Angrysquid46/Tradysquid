"""Register TradeBot commands with public ticker access and owner upgrade batching."""

from __future__ import annotations

import register_discord_commands as registry


registry.OWNER_ONLY_COMMANDS.discard("ticker-remove")
registry.OWNER_ONLY_COMMANDS.update(
    {"upgrade-add", "upgrade-list", "upgrade-ready", "upgrade-cancel"}
)

UPGRADE_COMMANDS = [
    {
        "name": "upgrade-add",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: add one request to the free GitHub upgrade batch",
        "options": [
            {
                "name": "request",
                "description": "Describe the change, bug fix, or feature to batch",
                "type": 3,
                "required": True,
                "min_length": 5,
                "max_length": 1500,
            }
        ],
    },
    {
        "name": "upgrade-list",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: show the current GitHub upgrade batch and request count",
    },
    {
        "name": "upgrade-ready",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: lock the current upgrade batch for implementation review",
        "options": [
            {
                "name": "summary",
                "description": "Optional note about how the requests should be handled together",
                "type": 3,
                "required": False,
                "max_length": 500,
            }
        ],
    },
    {
        "name": "upgrade-cancel",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: close the open upgrade batch without changing code",
        "options": [
            {
                "name": "reason",
                "description": "Optional reason for cancelling this batch",
                "type": 3,
                "required": False,
                "max_length": 500,
            }
        ],
    },
]

existing_names = {str(command.get("name") or "") for command in registry.COMMANDS}
registry.COMMANDS.extend(
    command for command in UPGRADE_COMMANDS if command["name"] not in existing_names
)

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
    elif name == "ask":
        command["description"] = (
            "Ask AI-enhanced TradeBot an educational trading or options question"
        )
        options = command.get("options") or []
        if options:
            options[0]["description"] = (
                "Ask about options, charts, risk, scanner logic, or trade mechanics"
            )
            options[0]["max_length"] = 600


if __name__ == "__main__":
    raise SystemExit(registry.main())
