"""Preserve one diagnostic repair request across OPEN and READY batches.

The normal bridge creates new requests only in an OPEN batch. This runtime patch
first searches every open Tradysquid batch, including READY batches, and updates
the existing diagnostic comment in place. It never edits code or changes batch
approval state.
"""

from __future__ import annotations

from typing import Any

import github_upgrade_bridge as bridge

_INSTALLED = False
_ORIGINAL_ADD_OR_UPDATE = bridge.add_or_update_diagnostic


def add_or_update_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
    marker = bridge._diagnostic_marker(str(report.get("signature") or ""))
    for issue in bridge._list_open_issues():
        title = str(issue.get("title") or "")
        if title != bridge.OPEN_TITLE and not title.startswith(bridge.READY_PREFIX):
            continue
        issue_number = int(issue.get("number") or 0)
        if not issue_number:
            continue
        comments = bridge._request_comments(issue_number)
        existing = next(
            (
                comment
                for comment in comments
                if marker in str(comment.get("body") or "")
            ),
            None,
        )
        if not existing:
            continue
        sequence = bridge._request_number(str(existing.get("body") or "")) or 1
        updated = bridge._request(
            "PATCH",
            f"/issues/comments/{int(existing['id'])}",
            payload={"body": bridge._diagnostic_body(report, sequence)},
        )
        return {
            "issue_number": issue_number,
            "issue_url": bridge._issue_url(issue),
            "request_number": sequence,
            "comment_id": int((updated or existing).get("id") or existing["id"]),
            "source": "AUTOMATIC DIAGNOSTIC",
            "batch_state": "READY" if title.startswith(bridge.READY_PREFIX) else "OPEN",
            "created": False,
        }
    return _ORIGINAL_ADD_OR_UPDATE(report)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    bridge.add_or_update_diagnostic = add_or_update_diagnostic
    _INSTALLED = True
