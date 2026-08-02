"""Read-only verification of the live Discord guild command registry.

The diagnostic compares Discord's registered guild commands with the expected
public registry. It never PUTs, POSTs, deletes, or re-registers commands. A
persistent mismatch follows the normal diagnostic-generated upgrade path.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

import requests

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics
import register_discord_commands_public as public_registry

_INSTALLED = False
_ORIGINAL_COLLECT = startup.collect_health_checks


def expected_command_names() -> list[str]:
    return sorted(
        {
            str(command.get("name") or "").strip()
            for command in public_registry.registry.COMMANDS
            if str(command.get("name") or "").strip()
        }
    )


def registered_command_names() -> list[str]:
    application_id = os.environ.get("DISCORD_APPLICATION_ID", "").strip()
    guild_id = os.environ.get("DISCORD_GUILD_ID", "").strip()
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    missing = [
        name
        for name, value in (
            ("DISCORD_APPLICATION_ID", application_id),
            ("DISCORD_GUILD_ID", guild_id),
            ("DISCORD_BOT_TOKEN", token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError("Missing Discord command verification configuration: " + ", ".join(missing))
    response = requests.get(
        f"https://discord.com/api/v10/applications/{application_id}/guilds/{guild_id}/commands",
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (Tradysquid Command Diagnostics, 1.0)",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload: Any = response.json()
    if not isinstance(payload, list):
        raise RuntimeError("Discord returned an unexpected guild command payload")
    return [
        str(command.get("name") or "").strip()
        for command in payload
        if isinstance(command, dict) and str(command.get("name") or "").strip()
    ]


def command_registration_check() -> diagnostics.HealthCheck:
    expected = expected_command_names()
    try:
        registered = registered_command_names()
    except Exception as exc:
        return diagnostics.HealthCheck(
            "discord-command-registry-connectivity",
            False,
            "Discord commands",
            "read-only guild command verification",
            f"{type(exc).__name__}: {exc}",
            severity="WARNING",
            channels="#upgrade-review",
            runtime_target="GET /applications/{application}/guilds/{guild}/commands",
            automatic_retry="next five-minute diagnostic cycle",
            healthy_services="unchanged",
            repair_objective="Restore read-only command verification without blocking the command bot or updater.",
            acceptance_tests="The read-only Discord command GET succeeds and returns the expected unique command set.",
        )

    counts = Counter(registered)
    duplicates = sorted(name for name, count in counts.items() if count > 1)
    registered_set = set(registered)
    expected_set = set(expected)
    missing = sorted(expected_set - registered_set)
    extra = sorted(registered_set - expected_set)
    passed = not missing and not extra and not duplicates
    detail = (
        f"expected={len(expected)}; registered={len(registered)}; "
        f"missing={missing or 'none'}; extra={extra or 'none'}; duplicates={duplicates or 'none'}"
    )
    return diagnostics.HealthCheck(
        "discord-command-registry-match",
        passed,
        "Discord commands",
        "live guild command set",
        detail,
        severity="ERROR" if not passed else "INFO",
        channels="#upgrade-review and Discord slash-command menu",
        runtime_target="register_discord_commands_public.COMMANDS versus live guild commands",
        automatic_retry="read-only verification repeats every five minutes; registration remains an explicit maintenance action",
        healthy_services="command bot remains independent",
        repair_objective="Make the live Discord guild commands exactly match the expected unique public registry.",
        acceptance_tests="The four owner upgrade commands and all public commands appear exactly once, with no missing or extra names.",
    )


def collect_health_checks(engine_connection: Any):
    checks, channels = _ORIGINAL_COLLECT(engine_connection)
    checks.append(command_registration_check())
    return checks, channels


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    startup.collect_health_checks = collect_health_checks
    diagnostics.collect_health_checks = collect_health_checks
    _INSTALLED = True
