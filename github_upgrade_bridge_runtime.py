"""Runtime hardening for the shared GitHub upgrade bridge.

All open issue pages and issue-comment pages are read, so a diagnostic signature
cannot be missed after the first 100 comments. Pull-request CI uses GitHub check
runs first and combined commit status as a fallback. This module remains read
only except for the bridge's existing request/comment update operations.
"""

from __future__ import annotations

from typing import Any

import github_upgrade_bridge as bridge

_INSTALLED = False


def _paged(path: str, *, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    base = dict(params or {})
    per_page = int(base.pop("per_page", 100) or 100)
    values: list[dict[str, Any]] = []
    for page in range(1, 51):
        payload = bridge._request(
            "GET",
            path,
            params={**base, "per_page": per_page, "page": page},
        )
        if not isinstance(payload, list):
            raise bridge.GitHubUpgradeError(
                f"GitHub returned an unexpected paginated response for {path}."
            )
        items = [item for item in payload if isinstance(item, dict)]
        values.extend(items)
        if len(payload) < per_page:
            return values
    raise bridge.GitHubUpgradeError(
        f"GitHub pagination exceeded 50 pages for {path}; review the repository queue."
    )


def list_open_issues() -> list[dict[str, Any]]:
    return [
        item
        for item in _paged(
            "/issues",
            params={
                "state": "open",
                "per_page": 100,
                "sort": "created",
                "direction": "desc",
            },
        )
        if "pull_request" not in item
    ]


def list_comments(issue_number: int) -> list[dict[str, Any]]:
    return _paged(
        f"/issues/{int(issue_number)}/comments",
        params={"per_page": 100},
    )


def _check_run_state(sha: str) -> str:
    try:
        payload = bridge._request(
            "GET",
            f"/commits/{sha}/check-runs",
            params={"per_page": 100},
        )
    except bridge.GitHubUpgradeError:
        return "UNKNOWN"
    runs = (
        payload.get("check_runs")
        if isinstance(payload, dict) and isinstance(payload.get("check_runs"), list)
        else []
    )
    runs = [item for item in runs if isinstance(item, dict)]
    if not runs:
        return "UNKNOWN"
    failure_conclusions = {
        "failure",
        "cancelled",
        "timed_out",
        "action_required",
        "startup_failure",
        "stale",
    }
    if any(
        str(item.get("conclusion") or "").casefold() in failure_conclusions
        for item in runs
    ):
        return "FAILURE"
    if any(str(item.get("status") or "").casefold() != "completed" for item in runs):
        return "PENDING"
    successful = {"success", "neutral", "skipped"}
    if all(
        str(item.get("conclusion") or "").casefold() in successful
        for item in runs
    ):
        return "SUCCESS"
    return "UNKNOWN"


def pull_ci_state(sha: str) -> str:
    checks = _check_run_state(sha)
    if checks != "UNKNOWN":
        return checks
    try:
        status = bridge._request("GET", f"/commits/{sha}/status")
    except bridge.GitHubUpgradeError:
        return "UNKNOWN"
    state = str((status or {}).get("state") or "UNKNOWN").upper()
    return {
        "EXPECTED": "PENDING",
        "PENDING": "PENDING",
        "ERROR": "FAILURE",
        "FAILURE": "FAILURE",
        "SUCCESS": "SUCCESS",
    }.get(state, "UNKNOWN")


def pull_request_queue() -> list[dict[str, Any]]:
    pulls = _paged(
        "/pulls",
        params={
            "state": "open",
            "per_page": 100,
            "sort": "updated",
            "direction": "desc",
        },
    )
    results: list[dict[str, Any]] = []
    for pull in pulls:
        sha = str((pull.get("head") or {}).get("sha") or "")
        ci_state = pull_ci_state(sha) if sha else "UNKNOWN"
        mergeable = str(pull.get("mergeable_state") or "UNKNOWN").upper()
        if ci_state == "FAILURE":
            next_action = "Repair the failing CI checks."
        elif ci_state == "PENDING":
            next_action = "Wait for CI to finish, then complete maintainer review."
        elif bool(pull.get("draft")):
            next_action = "Finish the draft implementation and request maintainer review."
        elif ci_state == "SUCCESS":
            next_action = "Maintainer reviews and merges the approved implementation."
        else:
            next_action = "Inspect the pull-request checks, then complete maintainer review."
        results.append(
            {
                "number": int(pull.get("number") or 0),
                "title": str(pull.get("title") or "Untitled pull request"),
                "url": str(pull.get("html_url") or ""),
                "updated_at": str(pull.get("updated_at") or ""),
                "draft": bool(pull.get("draft")),
                "mergeable_state": mergeable,
                "ci_state": ci_state,
                "head_sha": sha,
                "next_action": next_action,
            }
        )
    return results


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    bridge._list_open_issues = list_open_issues
    bridge._list_comments = list_comments
    bridge.pull_request_queue = pull_request_queue
    _INSTALLED = True
