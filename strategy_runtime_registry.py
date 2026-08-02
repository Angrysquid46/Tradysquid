"""Publish an always-current, read-only strategy runtime registry to GitHub.

The private repository issue is a visibility surface, not an updater or change
queue.  One bot-managed comment is updated per profile.  It includes the stored
configuration and the scanner/position-manager acknowledgements needed to prove
what the running process loaded.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any

import github_upgrade_bridge as github
import strategy_profiles
import strategy_runtime_consumption as runtime

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "strategy-runtime-registry.json"
ISSUE_TITLE = "[Tradysquid Strategy Runtime Registry]"
ISSUE_MARKER = "<!-- tradysquid-strategy-runtime-registry -->"
PROFILE_MARKER_PREFIX = "<!-- tradysquid-strategy-profile:"
PUBLISH_INTERVAL_SECONDS = max(
    60,
    min(3600, int(os.environ.get("STRATEGY_REGISTRY_SYNC_SECONDS", "300"))),
)

_LOCK = threading.Lock()
_WORKER_LOCK = threading.Lock()
_WORKER_STARTED = False


def now_iso() -> str:
    return runtime.now_iso()


def _atomic_state(payload: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, STATE_PATH)


def profile_marker(name: str) -> str:
    clean = "".join(
        character
        for character in str(name or "").lower()
        if character.isalnum() or character == "-"
    )
    return f"{PROFILE_MARKER_PREFIX}{clean} -->"


def issue_body(snapshot: dict[str, Any]) -> str:
    statuses = {
        str(item["name"]): str(item["runtime_status"])
        for item in snapshot["profiles"]
    }
    active = sum(status == "ACTIVE" for status in statuses.values())
    return "\n".join(
        [
            ISSUE_MARKER,
            "# Tradysquid Strategy Runtime Registry",
            "",
            "This private issue is maintained by the running information engine.",
            "It is read-only runtime evidence and does not deploy code or change a strategy.",
            "",
            f"**Last published:** {now_iso()}",
            f"**Profiles with matching runtime proof:** {active}/{len(statuses)}",
            "**Required consumers:** scanner and position manager",
            "**Paper trading only:** YES",
            "**Updater involved:** NO",
            "",
            "Each profile is stored in one persistent comment containing both a readable",
            "summary and machine-readable JSON. `ACTIVE` means stored version/hash, scanner",
            "acknowledgement, and position-manager acknowledgement all match.",
        ]
    )


def profile_comment(item: dict[str, Any], load_meta: dict[str, Any]) -> str:
    profile = item["profile"]
    payload = {
        "profile": item["name"],
        "stored_version": item["version"],
        "stored_configuration_hash": item["configuration_hash"],
        "enabled": item["enabled"],
        "runtime_status": item["runtime_status"],
        "runtime_match": item["runtime_match"],
        "scanner": {
            "version": item["scanner_loaded_version"],
            "configuration_hash": item["scanner_loaded_hash"],
            "acknowledged_at": item["scanner_acknowledged_at"],
        },
        "position_manager": {
            "version": item["position_manager_loaded_version"],
            "configuration_hash": item["position_manager_loaded_hash"],
            "acknowledged_at": item["position_manager_acknowledged_at"],
        },
        "configuration_load": load_meta,
        "effective_profile": profile,
        "paper_trading_only": True,
        "updater_involved": False,
        "published_at": now_iso(),
    }
    machine = json.dumps(payload, indent=2, sort_keys=True)
    return "\n".join(
        [
            profile_marker(str(item["name"])),
            f"## {str(item['name']).replace('-', ' ').title()}",
            "",
            f"**Status:** {item['runtime_status']}",
            f"**Stored version:** `{item['version']}`",
            f"**Stored hash:** `{item['configuration_hash']}`",
            f"**Scanner loaded:** `{item['scanner_loaded_version'] or 'missing'}` / "
            f"`{item['scanner_loaded_hash'] or 'missing'}`",
            f"**Position manager loaded:** `{item['position_manager_loaded_version'] or 'missing'}` / "
            f"`{item['position_manager_loaded_hash'] or 'missing'}`",
            f"**Runtime hash match:** {'YES' if item['runtime_match'] else 'NO'}",
            f"**Configuration source:** `{load_meta.get('source') or 'unknown'}`",
            f"**Fallback used:** {'YES' if load_meta.get('fallback_used') else 'NO'}",
            "**Strategy writes enabled here:** NO",
            "**Updater involved:** NO",
            "",
            "### Machine-readable runtime record",
            "```json",
            machine,
            "```",
        ]
    )


def _find_or_create_issue(snapshot: dict[str, Any]) -> dict[str, Any]:
    issue = next(
        (
            item
            for item in github._list_open_issues()
            if str(item.get("title") or "") == ISSUE_TITLE
            and ISSUE_MARKER in str(item.get("body") or "")
        ),
        None,
    )
    body = issue_body(snapshot)
    if issue is None:
        created = github._request(
            "POST", "/issues", payload={"title": ISSUE_TITLE, "body": body}
        )
        if not isinstance(created, dict) or not created.get("number"):
            raise github.GitHubUpgradeError(
                "GitHub did not confirm the strategy runtime registry issue."
            )
        return created
    github._request(
        "PATCH", f"/issues/{int(issue['number'])}", payload={"body": body}
    )
    return issue


def publish_once() -> dict[str, Any]:
    """Update the registry issue and exactly one persistent comment per profile."""
    with _LOCK:
        if not github.configured():
            payload = {
                "status": "NOT_CONFIGURED",
                "published_at": now_iso(),
                "reason": github.configuration_message(),
                "updater_involved": False,
            }
            _atomic_state(payload)
            return payload

        document = runtime.load_active_document()
        runtime_state = strategy_profiles.load_runtime_state(runtime.RUNTIME_STATE_PATH)
        snapshot = strategy_profiles.registry_snapshot(document, runtime_state)
        load_meta = runtime.last_load_metadata()
        issue = _find_or_create_issue(snapshot)
        issue_number = int(issue["number"])
        comments = github._list_comments(issue_number)
        comments_by_marker: dict[str, dict[str, Any]] = {}
        for comment in comments:
            body = str(comment.get("body") or "")
            for name in strategy_profiles.PROFILE_IDENTITIES:
                marker = profile_marker(name)
                if marker in body:
                    comments_by_marker[marker] = comment
                    break

        comment_ids: dict[str, int] = {}
        for item in snapshot["profiles"]:
            name = str(item["name"])
            marker = profile_marker(name)
            body = profile_comment(item, load_meta)
            existing = comments_by_marker.get(marker)
            if existing:
                comment = github._request(
                    "PATCH",
                    f"/issues/comments/{int(existing['id'])}",
                    payload={"body": body},
                )
            else:
                comment = github._request(
                    "POST",
                    f"/issues/{issue_number}/comments",
                    payload={"body": body},
                )
            if not isinstance(comment, dict) or not comment.get("id"):
                raise github.GitHubUpgradeError(
                    f"GitHub did not confirm the runtime comment for {name}."
                )
            comment_ids[name] = int(comment["id"])

        statuses = {
            str(item["name"]): str(item["runtime_status"])
            for item in snapshot["profiles"]
        }
        payload = {
            "status": "OK",
            "published_at": now_iso(),
            "issue_number": issue_number,
            "issue_url": str(issue.get("html_url") or ""),
            "comments": comment_ids,
            "profile_statuses": statuses,
            "all_profiles_active": all(
                status == "ACTIVE" for status in statuses.values()
            ),
            "updater_involved": False,
        }
        _atomic_state(payload)
        return payload


def worker() -> None:
    while True:
        try:
            publish_once()
        except Exception as exc:
            _atomic_state(
                {
                    "status": "ERROR",
                    "published_at": now_iso(),
                    "error": f"{type(exc).__name__}: {exc}",
                    "updater_involved": False,
                }
            )
        time.sleep(PUBLISH_INTERVAL_SECONDS)


def start_worker() -> threading.Thread | None:
    global _WORKER_STARTED
    with _WORKER_LOCK:
        if _WORKER_STARTED:
            return None
        thread = threading.Thread(
            target=worker,
            name="strategy-runtime-registry",
            daemon=True,
        )
        thread.start()
        _WORKER_STARTED = True
        return thread


def validate_contract() -> dict[str, Any]:
    document = strategy_profiles.load_document()
    runtime_state = {"schema_version": 2, "profiles": {}}
    snapshot = strategy_profiles.registry_snapshot(document, runtime_state)
    bodies = [
        profile_comment(item, {"source": "validation", "fallback_used": False})
        for item in snapshot["profiles"]
    ]
    if len(bodies) != len(strategy_profiles.PROFILE_IDENTITIES):
        raise RuntimeError("registry did not render one comment per profile")
    if any("Strategy writes enabled here:** NO" not in body for body in bodies):
        raise RuntimeError("registry comments must remain read-only")
    if any("Updater involved:** NO" not in body for body in bodies):
        raise RuntimeError("registry comments must exclude updater involvement")
    return {
        "issue_title": ISSUE_TITLE,
        "profiles": len(bodies),
        "read_only": True,
        "publish_seconds": PUBLISH_INTERVAL_SECONDS,
    }
