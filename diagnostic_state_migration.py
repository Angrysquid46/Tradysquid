"""One-time cleanup of pre-stabilization transient diagnostic state.

The original runtime published first-occurrence observations and generated
hash-based log signatures. Those records are not actionable repair requests and
would otherwise remain open forever after the publication model is corrected.
This migration resolves only active records that never reached the shared GitHub
batch and have fewer than three consecutive failures. Escalated repair evidence
is never rewritten or deleted.
"""

from __future__ import annotations

import json
from typing import Any

import diagnostic_upgrade_system as diagnostics

VERSION = "diagnostic-state-migration-v1"
META_KEY = f"{VERSION}:completed"
_INSTALLED = False


def migrate() -> dict[str, Any]:
    connection = diagnostics.connect_store()
    try:
        if diagnostics._meta(connection, META_KEY, ""):
            return {"version": VERSION, "already_completed": True, "resolved": 0}
        rows = [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM diagnostics
                WHERE status IN ('DEGRADED','FAILED','RETRYING','FAILED AGAIN')
                """
            ).fetchall()
        ]
        candidates = [
            row
            for row in rows
            if not int(row.get("github_request_number") or 0)
            and int(row.get("consecutive_failures") or 0) < 3
        ]
        timestamp = diagnostics.iso_now()
        for row in candidates:
            connection.execute(
                """
                UPDATE diagnostics SET
                    status='RESOLVED',
                    consecutive_failures=0,
                    recovery_time=?,
                    resolution_commit=?,
                    verification_result=?,
                    automatic_retry='reclassified by diagnostic stabilization',
                    discord_message_id=''
                WHERE signature=?
                """,
                (
                    timestamp,
                    diagnostics._current_sha(),
                    "Pre-stabilization first-occurrence observation was consolidated into the actionable review model.",
                    row["signature"],
                ),
            )
        diagnostics._set_meta(
            connection,
            META_KEY,
            json.dumps(
                {
                    "resolved": len(candidates),
                    "preserved_escalated": len(rows) - len(candidates),
                    "at": timestamp,
                },
                separators=(",", ":"),
            ),
        )
        connection.commit()
        return {
            "version": VERSION,
            "already_completed": False,
            "resolved": len(candidates),
            "preserved_escalated": len(rows) - len(candidates),
        }
    finally:
        connection.close()


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    migrate()
    _INSTALLED = True
