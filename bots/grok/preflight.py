"""GROK preflight — fail closed if any required condition is missing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PreflightResult:
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def run_preflight(
    *,
    scoreboard_available: bool,
    market_data_available: bool,
    today_0dte_available: bool,
    provider_reachable: bool,
    no_open_position: bool,
    session_open: bool,
    config_present: bool = True,
    governance_clear: bool = True,
) -> PreflightResult:
    failures: list[str] = []
    warnings: list[str] = []

    if not scoreboard_available:
        failures.append("neutral scoreboard unavailable")
    if not market_data_available:
        failures.append("factual market data unavailable")
    if not today_0dte_available:
        failures.append("current day SPY 0DTE expiration not available")
    if not provider_reachable:
        failures.append("provider connectivity failed")
    if not no_open_position:
        failures.append("overlapping official GROK position already exists")
    if not session_open:
        failures.append("market/session conditions not valid for trading")
    if not config_present:
        failures.append("required configuration missing")
    if not governance_clear:
        warnings.append("governance lock may still be active — proceed only with owner authorization")

    return PreflightResult(ok=len(failures) == 0, failures=failures, warnings=warnings)
