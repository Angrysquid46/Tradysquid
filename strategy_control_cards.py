"""Read-only Discord card rendering for strategy profile PR 1.

The cards show stored settings and runtime acknowledgement separately. They do
not edit profiles and never claim ACTIVE without matching scanner and position-
manager acknowledgements.
"""

from __future__ import annotations

from typing import Any

import strategy_profiles

CARD_COLOR_ACTIVE = 0x57F287
CARD_COLOR_PENDING = 0xFEE75C
CARD_COLOR_MISMATCH = 0xED4245


def _field(name: str, value: str, *, inline: bool = False) -> dict[str, Any]:
    return {
        "name": name[:256],
        "value": (value or "—")[:1024],
        "inline": inline,
    }


def _fmt(value: Any) -> str:
    if value is None:
        return "Disabled"
    if isinstance(value, bool):
        return "YES" if value else "NO"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) or "None"
    return str(value)


def card_token(profile_name: str) -> str:
    return f"STRATEGY-CARD::{profile_name}"


def _color(status: str) -> int:
    if status == "ACTIVE":
        return CARD_COLOR_ACTIVE
    if status == "RUNTIME MISMATCH":
        return CARD_COLOR_MISMATCH
    return CARD_COLOR_PENDING


def profile_card(
    snapshot: dict[str, Any], page: str = "overview"
) -> dict[str, Any]:
    profile = snapshot["profile"]
    page_key = page.strip().casefold().replace("_", "-")
    fields = [
        _field("Profile version", snapshot["version"], inline=True),
        _field(
            "Stored configuration hash",
            snapshot["configuration_hash"],
            inline=True,
        ),
        _field("Runtime status", snapshot["runtime_status"], inline=True),
    ]

    if page_key == "overview":
        fields.extend(
            [
                _field(
                    "Play style",
                    f"{snapshot['play_type']} {snapshot['direction'].upper()} · "
                    f"{snapshot['structure']}",
                ),
                _field(
                    "Scanner acknowledgement",
                    f"Version: {_fmt(snapshot['scanner_loaded_version'])}\n"
                    f"Hash: {_fmt(snapshot['scanner_loaded_hash'])}\n"
                    f"At: {_fmt(snapshot['scanner_acknowledged_at'])}",
                    inline=True,
                ),
                _field(
                    "Position-manager acknowledgement",
                    f"Version: {_fmt(snapshot['position_manager_loaded_version'])}\n"
                    f"Hash: {_fmt(snapshot['position_manager_loaded_hash'])}\n"
                    f"At: {_fmt(snapshot['position_manager_acknowledged_at'])}",
                    inline=True,
                ),
                _field(
                    "Activation proof",
                    "ACTIVE is shown only when stored version/hash, scanner "
                    "version/hash, and position-manager version/hash all match. "
                    "PR 1 is read-only and does not change trade behavior.",
                ),
            ]
        )
    elif page_key == "contract-filters":
        filters = profile["contract_filters"]
        rows = [f"`{key}`: {_fmt(filters[key])}" for key in sorted(filters)]
        fields.append(_field("Contract filters", "\n".join(rows)))
    elif page_key == "entry-rules":
        entry = profile["entry"]
        fields.extend(
            [
                _field(
                    "Timeframes",
                    f"Entry: {_fmt(entry['timeframe'])}\n"
                    f"Context: {_fmt(entry['higher_timeframes'])}",
                ),
                _field(
                    "Rules",
                    "\n".join(
                        f"{'✓' if rule['enabled'] else '○'} `{rule['id']}` · "
                        f"{rule['type']} · {rule['action']}"
                        for rule in entry["rules"]
                    ),
                ),
                _field(
                    "Rule groups",
                    "\n".join(
                        f"`{group['id']}` · {group['operator']} · "
                        f"{', '.join(group['rule_ids'])}"
                        for group in entry["rule_groups"]
                    ),
                ),
            ]
        )
    elif page_key == "management-rules":
        rows = [
            f"`{key}`: {_fmt(profile['management'][key])}"
            for key in sorted(profile["management"])
        ]
        fields.append(_field("Management rules", "\n".join(rows)))
    elif page_key == "exit-rules":
        exit_config = profile["exit"]
        fields.extend(
            [
                _field(
                    "Hard stop",
                    "\n".join(
                        f"`{key}`: {_fmt(value)}"
                        for key, value in exit_config["hard_stop"].items()
                    ),
                ),
                _field(
                    "Profit target",
                    "\n".join(
                        f"`{key}`: {_fmt(value)}"
                        for key, value in exit_config["profit_target"].items()
                    ),
                ),
                _field(
                    "Profit protection",
                    "\n".join(
                        f"`{section}`: {_fmt(exit_config[section])}"
                        for section in (
                            "preferred_profit_zone",
                            "break_even",
                            "trailing",
                        )
                    ),
                ),
                _field(
                    "Expiration",
                    "\n".join(
                        f"`{key}`: {_fmt(value)}"
                        for key, value in exit_config["expiration"].items()
                    ),
                ),
            ]
        )
    else:
        raise strategy_profiles.StrategyProfileError(
            f"unsupported strategy card page: {page}"
        )

    return {
        "title": f"{snapshot['name'].replace('-', ' ').upper()} STRATEGY",
        "description": (
            f"Read-only canonical profile · `{card_token(snapshot['name'])}`\n"
            "Stored settings are not reported as live until both runtime "
            "consumers acknowledge them."
        ),
        "color": _color(snapshot["runtime_status"]),
        "fields": fields[:25],
        "footer": {
            "text": "Paper trading only · updater infrastructure is not involved"
        },
    }


def all_profile_cards(
    document: dict[str, Any] | None = None,
    runtime_state: dict[str, Any] | None = None,
    page: str = "overview",
) -> list[dict[str, Any]]:
    snapshot = strategy_profiles.registry_snapshot(document, runtime_state)
    return [profile_card(item, page) for item in snapshot["profiles"]]
