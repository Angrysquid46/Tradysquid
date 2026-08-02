"""Free Discord-to-GitHub upgrade batching for Tradysquids.

This module uses the GitHub Issues REST API directly. It never calls OpenAI and
never edits repository contents. Approved batches become ordinary GitHub issues
that a maintainer can inspect and implement later.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

DEFAULT_REPOSITORY = "Angrysquid46/Tradysquid"
API_ROOT = "https://api.github.com"
OPEN_TITLE = "[Tradysquids Upgrade Batch] OPEN"
READY_PREFIX = "[Tradysquids Upgrade Batch] READY"
BATCH_MARKER = "<!-- tradysquids-upgrade-batch -->"
REQUEST_MARKER = "<!-- tradysquids-upgrade-request -->"
READY_MARKER = "<!-- tradysquids-upgrade-ready -->"
CANCEL_MARKER = "<!-- tradysquids-upgrade-cancelled -->"
REQUEST_TIMEOUT_SECONDS = 20


class GitHubUpgradeError(RuntimeError):
    """Raised when the configured GitHub issue bridge cannot complete a request."""


def _token() -> str:
    return os.environ.get("GITHUB_UPGRADE_TOKEN", "").strip()


def repository_name() -> str:
    return (
        os.environ.get("GITHUB_REPOSITORY", DEFAULT_REPOSITORY).strip()
        or DEFAULT_REPOSITORY
    )


def _validate_repository(repository: str) -> str:
    parts = repository.split("/")
    if len(parts) != 2 or not all(part.strip() for part in parts):
        raise GitHubUpgradeError(
            "GITHUB_REPOSITORY must use the form owner/repository."
        )
    return f"{parts[0].strip()}/{parts[1].strip()}"


def configured() -> bool:
    try:
        _validate_repository(repository_name())
    except GitHubUpgradeError:
        return False
    return bool(_token())


def configuration_message() -> str:
    if not _token():
        return (
            "GitHub upgrade batching is not configured. Add "
            "`GITHUB_UPGRADE_TOKEN` to the private local `.env`."
        )
    try:
        repository = _validate_repository(repository_name())
    except GitHubUpgradeError as exc:
        return str(exc)
    return f"GitHub upgrade batching is configured for `{repository}`."


def _headers() -> dict[str, str]:
    token = _token()
    if not token:
        raise GitHubUpgradeError(configuration_message())
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Tradysquids-Discord-Upgrade-Bridge/1.0",
    }


def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    repository = _validate_repository(repository_name())
    url = f"{API_ROOT}/repos/{repository}{path}"
    try:
        response = requests.request(
            method,
            url,
            headers=_headers(),
            params=params,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise GitHubUpgradeError(
            "GitHub could not be reached. The upgrade request was not uploaded."
        ) from exc

    if response.ok:
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise GitHubUpgradeError(
                "GitHub returned an unreadable response. The request was not confirmed."
            ) from exc

    message = ""
    try:
        data = response.json()
        if isinstance(data, dict):
            message = str(data.get("message") or "")
    except ValueError:
        message = ""

    if response.status_code == 401:
        detail = "GitHub rejected the token. Replace `GITHUB_UPGRADE_TOKEN` in `.env`."
    elif response.status_code == 403:
        detail = (
            "GitHub blocked this action. Confirm the token can access this repository "
            "and has Issues read/write permission."
        )
    elif response.status_code == 404:
        detail = (
            "GitHub could not find the configured repository. Check "
            "`GITHUB_REPOSITORY` and the token's selected-repository access."
        )
    elif response.status_code == 422:
        detail = "GitHub rejected the issue data as invalid."
    else:
        detail = f"GitHub returned HTTP {response.status_code}."
    if message:
        detail = f"{detail} GitHub message: {message[:240]}"
    raise GitHubUpgradeError(detail)


def _list_open_issues() -> list[dict[str, Any]]:
    data = _request(
        "GET",
        "/issues",
        params={"state": "open", "per_page": 100, "sort": "created", "direction": "desc"},
    )
    if not isinstance(data, list):
        raise GitHubUpgradeError("GitHub returned an unexpected issue list.")
    return [item for item in data if isinstance(item, dict) and "pull_request" not in item]


def _list_comments(issue_number: int) -> list[dict[str, Any]]:
    data = _request(
        "GET",
        f"/issues/{issue_number}/comments",
        params={"per_page": 100},
    )
    if not isinstance(data, list):
        raise GitHubUpgradeError("GitHub returned an unexpected issue-comment list.")
    return [item for item in data if isinstance(item, dict)]


def _find_open_batch() -> dict[str, Any] | None:
    for issue in _list_open_issues():
        if str(issue.get("title") or "") == OPEN_TITLE:
            return issue
    return None


def _latest_ready_batch() -> dict[str, Any] | None:
    for issue in _list_open_issues():
        if str(issue.get("title") or "").startswith(READY_PREFIX):
            return issue
    return None


def _create_open_batch() -> dict[str, Any]:
    body = "\n".join(
        [
            BATCH_MARKER,
            "# Tradysquids Upgrade Batch",
            "",
            "**Status:** OPEN",
            "",
            "This issue was created by the owner-only Discord upgrade bridge.",
            "Each `/upgrade-add` request is stored as a separate comment so the",
            "complete batch can be reviewed without using paid AI API calls.",
            "",
            "Use `/upgrade-ready` when the batch is complete. A ready batch is",
            "review material only; it does not edit code, merge a pull request, or",
            "deploy anything by itself.",
        ]
    )
    data = _request("POST", "/issues", payload={"title": OPEN_TITLE, "body": body})
    if not isinstance(data, dict) or not data.get("number"):
        raise GitHubUpgradeError("GitHub did not confirm the new upgrade batch.")
    return data


def _open_batch() -> dict[str, Any]:
    return _find_open_batch() or _create_open_batch()


def _request_count(issue_number: int) -> int:
    return sum(
        1
        for comment in _list_comments(issue_number)
        if REQUEST_MARKER in str(comment.get("body") or "")
    )


def _issue_url(issue: dict[str, Any]) -> str:
    return str(issue.get("html_url") or "")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def add_request(request_text: str, *, discord_user_id: str) -> dict[str, Any]:
    cleaned = "\n".join(line.rstrip() for line in str(request_text or "").strip().splitlines())
    if len(cleaned) < 5:
        raise GitHubUpgradeError("Upgrade requests must contain at least 5 characters.")
    if len(cleaned) > 1500:
        raise GitHubUpgradeError("Upgrade requests are limited to 1,500 characters.")

    issue = _open_batch()
    issue_number = int(issue["number"])
    sequence = _request_count(issue_number) + 1
    body = "\n".join(
        [
            REQUEST_MARKER,
            f"## Upgrade request {sequence}",
            "",
            cleaned,
            "",
            f"Submitted from Discord by owner ID `{discord_user_id or 'unknown'}` at {_timestamp()}.",
            "Status: **PENDING BATCH REVIEW**",
        ]
    )
    comment = _request(
        "POST", f"/issues/{issue_number}/comments", payload={"body": body}
    )
    if not isinstance(comment, dict):
        raise GitHubUpgradeError("GitHub did not confirm the uploaded request.")
    return {
        "issue_number": issue_number,
        "issue_url": _issue_url(issue),
        "request_number": sequence,
        "request_text": cleaned,
    }


def batch_status() -> dict[str, Any]:
    issue = _find_open_batch()
    state = "OPEN"
    if issue is None:
        issue = _latest_ready_batch()
        state = "READY" if issue else "NONE"
    if issue is None:
        return {"state": "NONE", "request_count": 0, "issue_number": None, "issue_url": ""}
    issue_number = int(issue["number"])
    return {
        "state": state,
        "request_count": _request_count(issue_number),
        "issue_number": issue_number,
        "issue_url": _issue_url(issue),
        "title": str(issue.get("title") or ""),
    }


def ready_batch(summary: str, *, discord_user_id: str) -> dict[str, Any]:
    issue = _find_open_batch()
    if issue is None:
        raise GitHubUpgradeError("There is no open upgrade batch to mark ready.")
    issue_number = int(issue["number"])
    count = _request_count(issue_number)
    if count < 1:
        raise GitHubUpgradeError("The open upgrade batch has no requests yet.")

    cleaned_summary = " ".join(str(summary or "").split())[:500]
    ready_title = f"{READY_PREFIX} {_timestamp()} · #{issue_number}"
    body = str(issue.get("body") or "")
    if "**Status:** OPEN" in body:
        body = body.replace("**Status:** OPEN", "**Status:** READY", 1)
    body = (
        body.rstrip()
        + "\n\n"
        + f"Ready for implementation review at {_timestamp()} with {count} request(s)."
    )
    ready_comment = "\n".join(
        [
            READY_MARKER,
            "## Batch marked ready",
            "",
            f"Requests: **{count}**",
            f"Owner ID: `{discord_user_id or 'unknown'}`",
            f"Summary: {cleaned_summary or 'No additional summary supplied.'}",
            "",
            "This approval makes the issue ready for maintainer review. It does not",
            "automatically edit, merge, or deploy repository code.",
        ]
    )
    _request("POST", f"/issues/{issue_number}/comments", payload={"body": ready_comment})
    updated = _request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"title": ready_title, "body": body},
    )
    if not isinstance(updated, dict):
        raise GitHubUpgradeError("GitHub did not confirm the ready batch.")
    return {
        "issue_number": issue_number,
        "issue_url": _issue_url(updated) or _issue_url(issue),
        "request_count": count,
        "title": ready_title,
    }


def cancel_batch(reason: str, *, discord_user_id: str) -> dict[str, Any]:
    issue = _find_open_batch()
    if issue is None:
        raise GitHubUpgradeError("There is no open upgrade batch to cancel.")
    issue_number = int(issue["number"])
    cleaned_reason = " ".join(str(reason or "").split())[:500]
    comment = "\n".join(
        [
            CANCEL_MARKER,
            "## Batch cancelled",
            "",
            f"Owner ID: `{discord_user_id or 'unknown'}`",
            f"Reason: {cleaned_reason or 'No reason supplied.'}",
            f"Cancelled at {_timestamp()}.",
        ]
    )
    _request("POST", f"/issues/{issue_number}/comments", payload={"body": comment})
    updated = _request(
        "PATCH",
        f"/issues/{issue_number}",
        payload={"state": "closed", "title": f"[Tradysquids Upgrade Batch] CANCELLED · #{issue_number}"},
    )
    return {
        "issue_number": issue_number,
        "issue_url": _issue_url(updated if isinstance(updated, dict) else issue),
    }
