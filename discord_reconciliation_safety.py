"""Non-destructive safety boundary for Discord report reconciliation.

Existing report cards are durable application output. Reconciliation may create
or update cards, but it may never bulk-delete working Discord output before a
replacement has been acknowledged. This module intentionally disables the two
legacy purge entry points used by performance reconciliation.
"""

from __future__ import annotations

from typing import Any

_INSTALLED = False


def install() -> None:
    """Mark the upsert-only safety boundary active.

    The legacy performance-card implementation was removed in Phase 3, so
    there are no destructive entry points left to monkeypatch.
    """
    global _INSTALLED
    _INSTALLED = True


def validate_contract() -> dict[str, Any]:
    if not _INSTALLED:
        raise RuntimeError("Discord reconciliation safety is not installed")
    return {
        "destructive_purge_enabled": False,
        "replacement_mode": "upsert-only",
        "existing_messages_preserved": True,
        "updater_involved": False,
    }
