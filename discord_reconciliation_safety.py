"""Non-destructive safety boundary for Discord report reconciliation.

Existing report cards are durable application output. Reconciliation may create
or update cards, but it may never bulk-delete working Discord output before a
replacement has been acknowledged. This module intentionally disables the two
legacy purge entry points used by performance reconciliation.
"""

from __future__ import annotations

from typing import Any

import performance_scorecards

_INSTALLED = False


def no_destructive_purge(*_args: Any, **_kwargs: Any) -> int:
    """Preserve every existing card; current cards are repaired with upserts."""
    return 0


def install() -> None:
    """Disable legacy bulk deletion without changing report generation."""
    global _INSTALLED
    performance_scorecards._purge_old_report_cards = no_destructive_purge
    performance_scorecards.base._purge_report_channel = no_destructive_purge
    _INSTALLED = True


def validate_contract() -> dict[str, Any]:
    if not _INSTALLED:
        raise RuntimeError("Discord reconciliation safety is not installed")
    if performance_scorecards._purge_old_report_cards is not no_destructive_purge:
        raise RuntimeError("Performance scorecards may still bulk-delete reports")
    if performance_scorecards.base._purge_report_channel is not no_destructive_purge:
        raise RuntimeError("Legacy report reconciliation may still delete reports")
    return {
        "destructive_purge_enabled": False,
        "replacement_mode": "upsert-only",
        "existing_messages_preserved": True,
        "updater_involved": False,
    }
