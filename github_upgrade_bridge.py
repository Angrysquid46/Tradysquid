"""Free Discord-to-GitHub upgrade batching for Tradysquid.

This module uses GitHub Issues directly. It never calls OpenAI, edits repository
contents, creates pull requests, merges code, or deploys anything. Owner requests
and persistent diagnostic repair requests share one auditable batch.
"""

from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any

import requests

DEFAULT_REPOSITORY = "Angrysquid46/Tradysquid"
API_ROOT = "https://api.github.com"
OPEN_TITLE = "[Tradysquids Upgrade Batch] OPEN"
READY_PREFIX = "[Tradysquids Upgrade Batch] READY"
BATCH_MARKER = "<!-- tradysquids-upgrade-batch -->"
REQUEST_MARKER = "<!-- tradysquids-upgrade-request -->"
DIAGNOSTIC_MARKER_PREFIX = "<!-- tradysquids-diagnostic:"
READY_MARKER = "<!-- tradysquids-upgrade-ready -->"
CANCEL_MARKER = "<!-- tradysquids-upgrade-cancelled -->"
REQUEST_TIMEOUT_SECONDS = 20
MAX_REQUESTS = 100


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
        "User-Agent": "Tradysquids-Discord-Upgrade-Bridge/2.0",
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
        pass

    if response.status_code == 401:
        detail = "GitHub rejected the token. Replace `GITHUB_UPGRADE_TOKEN` in `.env`."
    elif response.status_code == 403:
        detail = (
            "GitHub blocked this action. Confirm the token can access this repository "
            "and has Issues read/write permission."
        )
    elif response.status_code == 404:
        detail = (
            "GitHub could not find the configured repository or item. Check "
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
        params={
            "state": "open",
            "per_page": 100,
            "sort": "created",
            "direction": "desc",
        },
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
    return next(
        (
            issue
            for issue in _list_open_issues()
            if str(issue.get("title") or "") == OPEN_TITLE
        ),
        None,
    )


def _latest_ready_batch() -> dict[str, Any] | None:
    return next(
        (
            issue
            for issue in _list_open_issues()
            if str(issue.get("title") or "").startswith(READY_PREFIX)
        ),
        None,
    )


def _create_open_batch() -> dict[str, Any]:
    body = "\n".join(
        [
            BATCH_MARKER,
            "# Tradysquids Upgrade Batch",
            "",
            "**Status:** OPEN",
            "",
            "This issue is the shared review queue for owner requests and persistent",
            "diagnostic-generated repair requests. Every request is a separate comment.",
            "",
            "Use `/upgrade-ready` when the batch is complete. READY means reviewable,",
            "not implemented, merged, deployed, or verified.",
        ]
    )
    data = _request("POST", "/issues", payload={"title": OPEN_TITLE, "body": body})
    if not isinstance(data, dict) or not data.get("number"):
        raise GitHubUpgradeError("GitHub did not confirm the new upgrade batch.")
    return data


def _open_batch() -> dict[str, Any]:
    return _find_open_batch() or _create_open_batch()


def _request_comments(issue_number: int) -> list[dict[str, Any]]:
    return [
        comment
        for comment in _list_comments(issue_number)
        if REQUEST_MARKER in str(comment.get("body") or "")
    ]


def _request_count(issue_number: int) -> int:
    return len(_request_comments(issue_number))


def _issue_url(issue: dict[str, Any]) -> str:
    return str(issue.get("html_url") or "")


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _clean_text(value: Any, limit: int) -> str:
    return "\n".join(
        line.rstrip() for line in str(value or "").strip().splitlines()
    )[:limit]


def _field(body: str, label: str, default: str = "") -> str:
    match = re.search(
        rf"^\*\*{re.escape(label)}:\*\*\s*(.+)$",
        body,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    return match.group(1).strip() if match else default


def _request_number(body: str) -> int | None:
    match = re.search(r"^## Upgrade request\s+(\d+)", body, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _summary(body: str) -> str:
    lines = [line.strip() for line in body.splitlines()]
    for index, line in enumerate(lines):
        if line.startswith("## Upgrade request"):
            for candidate in lines[index + 1 :]:
                if candidate and not candidate.startswith("<!--") and not candidate.startswith("**"):
                    return candidate[:240]
    return "Upgrade request"


def _next_action(state: str) -> str:
    return (
        "Add remaining requests or use /upgrade-ready."
        if state == "OPEN"
        else "Maintainer review and implementation are required."
        if state == "READY"
        else "No open action."
    )


def list_batch_requests(issue_number: int | None = None) -> list[dict[str, Any]]:
    status = batch_status() if issue_number is None else None
    if issue_number is None:
        issue_number = status.get("issue_number") if status else None
    if not issue_number:
        return []
    state = str(status.get("state") if status else "OPEN")
    records: list[dict[str, Any]] = []
    for comment in _request_comments(int(issue_number)):
        body = str(comment.get("body") or "")
        records.append(
            {
                "request_number": _request_number(body),
                "source": _field(body, "Source", "OWNER REQUEST"),
                "status": _field(body, "Status", "PENDING BATCH REVIEW").strip("*"),
                "summary": _summary(body),
                "diagnostic_id": _field(body, "Diagnostic ID"),
                "comment_id": int(comment.get("id") or 0),
                "comment_url": str(comment.get("html_url") or ""),
                "updated_at": str(comment.get("updated_at") or comment.get("created_at") or ""),
                "next_action": _next_action(state),
            }
        )
    return records


def add_request(
    request_text: str,
    *,
    discord_user_id: str,
    source: str = "OWNER REQUEST",
) -> dict[str, Any]:
    cleaned = _clean_text(request_text, 1500)
    if len(cleaned) < 5:
        raise GitHubUpgradeError("Upgrade requests must contain at least 5 characters.")
    normalized_source = "AUTOMATIC DIAGNOSTIC" if source.upper() == "AUTOMATIC DIAGNOSTIC" else "OWNER REQUEST"

    issue = _open_batch()
    issue_number = int(issue["number"])
    existing_count = _request_count(issue_number)
    if existing_count >= MAX_REQUESTS:
        raise GitHubUpgradeError(
            f"The open upgrade batch already has {MAX_REQUESTS} requests. Mark it ready before adding more."
        )
    sequence = existing_count + 1
    body = "\n".join(
        [
            REQUEST_MARKER,
            f"## Upgrade request {sequence}",
            "",
            cleaned,
            "",
            f"**Source:** {normalized_source}",
            f"**Submitted by Discord owner ID:** `{discord_user_id or 'unknown'}`",
            f"**Submitted at:** {_timestamp()}",
            "**Status:** PENDING BATCH REVIEW",
            "**Next action:** Add remaining requests or mark the batch upgrade-ready.",
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
        "source": normalized_source,
        "comment_id": int(comment.get("id") or 0),
        "created": True,
    }


def _diagnostic_marker(signature: str) -> str:
    clean = re.sub(r"[^a-fA-F0-9_-]", "", str(signature or ""))[:96]
    if not clean:
        raise GitHubUpgradeError("A diagnostic signature is required.")
    return f"{DIAGNOSTIC_MARKER_PREFIX}{clean} -->"


def _diagnostic_body(report: dict[str, Any], sequence: int) -> str:
    marker = _diagnostic_marker(str(report.get("signature") or ""))
    evidence = _clean_text(report.get("evidence"), 3500) or "No additional evidence supplied."
    acceptance = _clean_text(report.get("acceptance_tests"), 1400) or "Reproduce the failure, deploy the repair, and require passing live verification."
    return "\n".join(
        [
            REQUEST_MARKER,
            marker,
            f"## Upgrade request {sequence}",
            "",
            f"### DIAGNOSTIC-GENERATED: {_clean_text(report.get('title'), 180) or 'Repair detected Tradysquid failure'}",
            "",
            f"**Source:** AUTOMATIC DIAGNOSTIC",
            f"**Diagnostic ID:** {_clean_text(report.get('diagnostic_id'), 120)}",
            f"**Severity:** {_clean_text(report.get('severity'), 40) or 'ERROR'}",
            f"**Component:** {_clean_text(report.get('component'), 160)}",
            f"**Operation:** {_clean_text(report.get('operation'), 200)}",
            f"**Affected channels:** {_clean_text(report.get('channels'), 300) or 'None identified'}",
            f"**Process / job / hook:** {_clean_text(report.get('runtime_target'), 300) or 'Not identified'}",
            f"**First occurrence:** {_clean_text(report.get('first_seen'), 80)}",
            f"**Latest occurrence:** {_clean_text(report.get('last_seen'), 80)}",
            f"**Consecutive failures:** {int(report.get('consecutive_failures') or 0)}",
            f"**Total failures:** {int(report.get('total_failures') or 0)}",
            f"**Deployed commit:** {_clean_text(report.get('deployed_commit'), 80) or 'unknown'}",
            f"**Last known working commit:** {_clean_text(report.get('last_working_commit'), 80) or 'unknown'}",
            f"**Automatic retry:** {_clean_text(report.get('automatic_retry'), 120) or 'unknown'}",
            f"**Healthy services remain online:** {_clean_text(report.get('healthy_services'), 120) or 'unknown'}",
            "",
            "### Sanitized evidence",
            "```text",
            evidence,
            "```",
            "",
            f"**Steps already attempted:** {_clean_text(report.get('steps_attempted'), 700) or 'Automatic retry only.'}",
            f"**Repair objective:** {_clean_text(report.get('repair_objective'), 900) or 'Identify and repair the repeatable defect without breaking healthy services.'}",
            "",
            "### Required acceptance",
            acceptance,
            "",
            "**Status:** PENDING BATCH REVIEW",
            "**Next action:** Owner marks the shared batch upgrade-ready; maintainer reviews and implements the repair.",
            "Uploading this request is not proof of repair. Merge, deployment, and live verification are separate states.",
        ]
    )[:65000]


def add_or_update_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
    """Create one shared-batch request per stable diagnostic signature."""
    issue = _open_batch()
    issue_number = int(issue["number"])
    comments = _request_comments(issue_number)
    marker = _diagnostic_marker(str(report.get("signature") or ""))
    existing = next(
        (comment for comment in comments if marker in str(comment.get("body") or "")),
        None,
    )
    if existing:
        sequence = _request_number(str(existing.get("body") or "")) or 1
        updated = _request(
            "PATCH",
            f"/issues/comments/{int(existing['id'])}",
            payload={"body": _diagnostic_body(report, sequence)},
        )
        return {
            "issue_number": issue_number,
            "issue_url": _issue_url(issue),
            "request_number": sequence,
            "comment_id": int((updated or existing).get("id") or existing["id"]),
            "source": "AUTOMATIC DIAGNOSTIC",
            "created": False,
        }

    if len(comments) >= MAX_REQUESTS:
        raise GitHubUpgradeError(
            f"The open upgrade batch already has {MAX_REQUESTS} requests."
        )
    sequence = len(comments) + 1
    created = _request(
        "POST",
        f"/issues/{issue_number}/comments",
        payload={"body": _diagnostic_body(report, sequence)},
    )
    if not isinstance(created, dict):
        raise GitHubUpgradeError("GitHub did not confirm the diagnostic request.")
    return {
        "issue_number": issue_number,
        "issue_url": _issue_url(issue),
        "request_number": sequence,
        "comment_id": int(created.get("id") or 0),
        "source": "AUTOMATIC DIAGNOSTIC",
        "created": True,
    }


def pull_request_queue() -> list[dict[str, Any]]:
    data = _request(
        "GET",
        "/pulls",
        params={"state": "open", "per_page": 100, "sort": "updated", "direction": "desc"},
    )
    if not isinstance(data, list):
        return []
    results: list[dict[str, Any]] = []
    for pull in data:
        if not isinstance(pull, dict):
            continue
        sha = str((pull.get("head") or {}).get("sha") or "")
        ci_state = "UNKNOWN"
        if sha:
            try:
                status = _request("GET", f"/commits/{sha}/status")
                ci_state = str((status or {}).get("state") or "UNKNOWN").upper()
            except GitHubUpgradeError:
                ci_state = "UNKNOWN"
        results.append(
            {
                "number": int(pull.get("number") or 0),
                "title": str(pull.get("title") or "Untitled pull request"),
                "url": str(pull.get("html_url") or ""),
                "updated_at": str(pull.get("updated_at") or ""),
                "draft": bool(pull.get("draft")),
                "mergeable_state": str(pull.get("mergeable_state") or "UNKNOWN").upper(),
                "ci_state": ci_state,
                "head_sha": sha,
                "next_action": (
                    "Wait for or repair CI."
                    if ci_state in {"FAILURE", "ERROR", "PENDING"}
                    else "Maintainer review and merge are required."
                ),
            }
        )
    return results


def batch_status() -> dict[str, Any]:
    issue = _find_open_batch()
    state = "OPEN"
    if issue is None:
        issue = _latest_ready_batch()
        state = "READY" if issue else "NONE"
    if issue is None:
        return {
            "state": "NONE",
            "request_count": 0,
            "issue_number": None,
            "issue_url": "",
            "requests": [],
            "next_action": "Use /upgrade-add or wait for a persistent diagnostic.",
        }
    issue_number = int(issue["number"])
    requests_list = list_batch_requests(issue_number)
    return {
        "state": state,
        "request_count": len(requests_list),
        "issue_number": issue_number,
        "issue_url": _issue_url(issue),
        "title": str(issue.get("title") or ""),
        "requests": requests_list,
        "next_action": _next_action(state),
        "updated_at": str(issue.get("updated_at") or ""),
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
    body = body.rstrip() + "\n\n" + (
        f"Ready for implementation review at {_timestamp()} with {count} request(s)."
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
            "READY means maintainer review may begin. It does not mean implemented,",
            "CI passed, merged, deployed, or live-verified.",
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
        payload={
            "state": "closed",
            "title": f"[Tradysquids Upgrade Batch] CANCELLED · #{issue_number}",
        },
    )
    return {
        "issue_number": issue_number,
        "issue_url": _issue_url(updated if isinstance(updated, dict) else issue),
    }
