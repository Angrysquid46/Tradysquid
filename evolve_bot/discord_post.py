"""Posts the evolve bot's own dashboard, trade alerts, and weekly
reviews to its own Discord category - the one item from the original
outline that was deliberately deferred through every earlier phase
("attach it to Discord last, not immediately... until there's something
real to show"). The trading loop is now actually running
(run_evolve_bot.ps1), so there's real content worth posting.

Reuses the SAME Discord bot application/token as the rest of Tradysquid
- one bot serves the whole guild across every strategy's own category,
the existing established pattern (CLAUDE.md: "own Discord category,
config flag" per strategy), not a new bot identity. But this module
implements its OWN minimal, independent REST client rather than reusing
spy_scanner.DiscordTracker - that class's discover() is tightly coupled
to the main system's specific forum/tag/CHANNEL_NAMES taxonomy (requires
a "trade-journal" forum channel with OPEN/HOLDING/WIN/LOSS/SCRATCH tags)
and touching it would mean extending shared machinery the evolve bot is
deliberately isolated from (never merged into the main system's
reconciliation/reporting). This manages its own category/channels from
scratch, mirroring DiscordTracker's proven retry/auth/multipart request
patterns without inheriting its main-system coupling.

Reads credentials from the process environment only (os.environ.get,
same convention market_features.py already uses for FRED_API_KEY/
FINNHUB_API_KEY) - deliberately does NOT auto-load .env at import time.
An earlier draft did that (mirroring _smoke_test.py's inline loader) and
it was a real mistake, caught before it shipped: every test that imports
this module transitively (engine.py does, unconditionally) would have
silently loaded the REAL Discord bot token from .env into the test
process and made genuine network calls during `pytest`, since
_load_env_if_needed() ran unconditionally at import time with no way for
a test to opt out short of mocking every credential-bearing test. Call
load_env() explicitly (see below) when you actually want .env's values -
the two scheduled-task PowerShell scripts (run_evolve_bot.ps1,
run_weekly_review.ps1) load .env at the PowerShell level before invoking
python instead, so their python subprocess already has real credentials
without this module ever touching disk on its own.

Every posting function here fails soft: enabled() is False (missing
credentials) -> returns None, does nothing. A caller like engine.py's
live trading cycle must never fail or block a real trade because Discord
is unreachable or unconfigured - posting is a side effect of trading,
never a precondition for it.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
API_BASE = "https://discord.com/api/v10"


def load_env() -> None:
    """Explicit, opt-in .env loader for interactive/manual use (e.g. a
    one-off verification script run directly, not through either
    scheduled task's PowerShell wrapper). Never called automatically by
    this module - see the module docstring for why that was a real bug
    the first time it was tried."""
    env_path = ROOT.parent / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())

    # BOT_TOKEN/GUILD_ID are captured once at import time (before .env is
    # ever read - see the module docstring for why). Refresh them here so
    # a caller who explicitly opts into load_env() actually sees the
    # loaded values, not the empty defaults captured at import.
    global BOT_TOKEN, GUILD_ID
    BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()


BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

CATEGORY_NAME = "SPY_EVOLVE"
GUILD_CATEGORY_CHANNEL_TYPE = 4
GUILD_TEXT_CHANNEL_TYPE = 0

# key -> (channel name, topic). Three channels, not the older strategies'
# two ("<slug>-performance"/"<slug>-results") - the evolve bot has two
# extra real content types (weekly reviews, Phase 12 logic proposals)
# that don't fit that naming, so a third channel is clearer than
# stretching "results" to cover all of it.
CHANNEL_SPECS: dict[str, tuple[str, str]] = {
    "dashboard": (
        "evolve-dashboard",
        "Equity curve, stats card, milestones - the evolve bot's real-numbers dashboard.",
    ),
    "trades": (
        "evolve-trades",
        "Real entry/exit alerts for the evolve bot's own live paper trades.",
    ),
    "reviews": (
        "evolve-reviews",
        "Weekly Claude reviews and pending Phase 12 logic proposals awaiting owner sign-off.",
    ),
}


class DiscordPostError(Exception):
    pass


def enabled() -> bool:
    return bool(BOT_TOKEN and GUILD_ID)


def _headers(content_type: str | None = "application/json") -> dict[str, str]:
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "User-Agent": "DiscordBot (Tradysquid Evolve Bot, 1.0)",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def _request(method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
    if not enabled():
        raise DiscordPostError("DISCORD_BOT_TOKEN or DISCORD_GUILD_ID is missing")
    url = f"{API_BASE}{path}"
    for attempt in range(4):
        response = requests.request(method, url, headers=_headers(), json=payload, timeout=20)
        if response.status_code == 429:
            retry_after = float(response.json().get("retry_after", 1.0)) if response.content else 1.0
            time.sleep(min(retry_after + 0.25, 65))
            continue
        if response.status_code >= 500 and attempt < 3:
            time.sleep(2**attempt)
            continue
        if not response.ok:
            body = response.text[:700].replace(BOT_TOKEN, "[REDACTED]")
            raise DiscordPostError(f"Discord HTTP {response.status_code} for {path}: {body}")
        if response.status_code == 204 or not response.content:
            return None
        return response.json()
    raise DiscordPostError(f"Discord rate limit retries exhausted for {path}")


_channel_cache: dict[str, str] = {}


def ensure_channels() -> dict[str, str]:
    """Idempotent find-or-create for the SPY_EVOLVE category and its 3
    channels. Real Discord state is the source of truth - re-running this
    never creates duplicates, it just discovers what already exists and
    only creates what's actually missing."""
    global _channel_cache
    if _channel_cache:
        return _channel_cache

    existing = _request("GET", f"/guilds/{GUILD_ID}/channels") or []
    by_name = {c["name"].lower(): c for c in existing}

    category = by_name.get(CATEGORY_NAME.lower())
    if not category or category.get("type") != GUILD_CATEGORY_CHANNEL_TYPE:
        category = _request(
            "POST", f"/guilds/{GUILD_ID}/channels", {"name": CATEGORY_NAME, "type": GUILD_CATEGORY_CHANNEL_TYPE}
        )
        by_name[category["name"].lower()] = category
    category_id = category["id"]

    channels: dict[str, str] = {}
    for key, (channel_name, topic) in CHANNEL_SPECS.items():
        channel = by_name.get(channel_name.lower())
        if (
            not channel
            or channel.get("type") != GUILD_TEXT_CHANNEL_TYPE
            or str(channel.get("parent_id")) != str(category_id)
        ):
            channel = _request(
                "POST",
                f"/guilds/{GUILD_ID}/channels",
                {"name": channel_name, "type": GUILD_TEXT_CHANNEL_TYPE, "parent_id": category_id, "topic": topic[:1024]},
            )
        channels[key] = channel["id"]

    _channel_cache = channels
    return channels


def post_message(channel_key: str, content: str) -> dict[str, Any] | None:
    if not enabled():
        return None
    channel_id = ensure_channels()[channel_key]
    return _request(
        "POST",
        f"/channels/{channel_id}/messages",
        {"content": content[:2000], "allowed_mentions": {"parse": []}},
    )


def post_file(
    channel_key: str, file_path: Path, content: str = "", mime_type: str = "image/png"
) -> dict[str, Any] | None:
    if not enabled() or not file_path.exists():
        return None
    channel_id = ensure_channels()[channel_key]
    url = f"{API_BASE}/channels/{channel_id}/messages"
    payload = {"content": content[:2000], "allowed_mentions": {"parse": []}}
    for attempt in range(4):
        with file_path.open("rb") as handle:
            response = requests.post(
                url,
                headers=_headers(content_type=None),
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (file_path.name, handle, mime_type)},
                timeout=30,
            )
        if response.status_code == 429:
            retry_after = float(response.json().get("retry_after", 1.0)) if response.content else 1.0
            time.sleep(min(retry_after + 0.25, 65))
            continue
        if response.status_code >= 500 and attempt < 3:
            time.sleep(2**attempt)
            continue
        if not response.ok:
            body = response.text[:700].replace(BOT_TOKEN, "[REDACTED]")
            raise DiscordPostError(f"Discord file upload HTTP {response.status_code}: {body}")
        return response.json()
    raise DiscordPostError("Discord file upload retries exhausted")


# Tracks one Discord message id per (channel_key, card_key) so
# upsert_message/upsert_file can keep exactly ONE card per real "thing"
# (the dashboard's stats card, a specific open position's live P/L card)
# instead of the channel accumulating a new message every single refresh.
# Deliberately a plain local JSON file, not a Discord-side search (unlike
# the main system's DiscordTracker.upsert_channel_message, which re-scans
# the channel's own message history) - this module has no per-channel
# message-history search machinery, and a local file is simpler and
# sufficient since this process is the only writer.
MESSAGE_STATE_PATH = ROOT / "state" / "discord_message_state.json"


def _load_message_state() -> dict[str, str]:
    try:
        return json.loads(MESSAGE_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_message_state(state: dict[str, str]) -> None:
    MESSAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    MESSAGE_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _delete_tracked_message(channel_key: str, card_key: str, state: dict[str, str]) -> None:
    tracked_id = state.get(f"{channel_key}:{card_key}")
    if not tracked_id:
        return
    channel_id = ensure_channels()[channel_key]
    try:
        _request("DELETE", f"/channels/{channel_id}/messages/{tracked_id}")
    except DiscordPostError as exc:
        if "HTTP 404" not in str(exc):
            raise


def _patch_message(channel_id: str, message_id: str, content: str) -> dict[str, Any] | None:
    return _request(
        "PATCH",
        f"/channels/{channel_id}/messages/{message_id}",
        {"content": content[:2000], "allowed_mentions": {"parse": []}},
    )


def _patch_message_with_file(
    channel_id: str, message_id: str, file_path: Path, content: str = "", mime_type: str = "image/png"
) -> dict[str, Any] | None:
    url = f"{API_BASE}/channels/{channel_id}/messages/{message_id}"
    # attachments: [] clears the message's existing attachment in the
    # same request - without it Discord keeps the old file alongside the
    # new one instead of replacing it.
    payload = {"content": content[:2000], "allowed_mentions": {"parse": []}, "attachments": []}
    for attempt in range(4):
        with file_path.open("rb") as handle:
            response = requests.request(
                "PATCH",
                url,
                headers=_headers(content_type=None),
                data={"payload_json": json.dumps(payload)},
                files={"files[0]": (file_path.name, handle, mime_type)},
                timeout=30,
            )
        if response.status_code == 429:
            retry_after = float(response.json().get("retry_after", 1.0)) if response.content else 1.0
            time.sleep(min(retry_after + 0.25, 65))
            continue
        if response.status_code >= 500 and attempt < 3:
            time.sleep(2**attempt)
            continue
        if not response.ok:
            body = response.text[:700].replace(BOT_TOKEN, "[REDACTED]")
            raise DiscordPostError(f"Discord file edit HTTP {response.status_code}: {body}")
        return response.json()
    raise DiscordPostError("Discord file edit retries exhausted")


def delete_card(channel_key: str, card_key: str) -> None:
    """Removes a previously upserted card with no replacement - for a
    card whose "thing" is genuinely done (a position's held-P/L card once
    it closes; the close alert is its own separate message and already
    covers that event), not for a card that'll be refreshed again later
    (use upsert_message/upsert_file for that)."""
    if not enabled():
        return
    state = _load_message_state()
    key = f"{channel_key}:{card_key}"
    if key not in state:
        return
    _delete_tracked_message(channel_key, card_key, state)
    del state[key]
    _save_message_state(state)


def upsert_message(channel_key: str, card_key: str, content: str) -> dict[str, Any] | None:
    """Like post_message, but keeps exactly one message per card_key in
    the channel - edits the existing tracked message in place (a true
    PATCH) when one already exists, rather than deleting and posting a
    fresh one. That distinction matters beyond appearances: Discord
    sends a push notification for a new message but not for an edit, so
    a delete+repost cycle notified on every single refresh regardless of
    whether anything real changed. Owner: "it's spamming the fuck out of
    me even without trades." Falls back to creating a fresh message only
    the first time, or if the tracked message was deleted out from under
    this process (a real 404, not the expected path)."""
    if not enabled():
        return None
    state = _load_message_state()
    key = f"{channel_key}:{card_key}"
    tracked_id = state.get(key)
    if tracked_id:
        channel_id = ensure_channels()[channel_key]
        try:
            return _patch_message(channel_id, tracked_id, content)
        except DiscordPostError as exc:
            if "HTTP 404" not in str(exc):
                raise
            del state[key]
    result = post_message(channel_key, content)
    if result and result.get("id"):
        state[key] = result["id"]
        _save_message_state(state)
    return result


def upsert_file(
    channel_key: str, card_key: str, file_path: Path, content: str = "", mime_type: str = "image/png"
) -> dict[str, Any] | None:
    """File-attachment version of upsert_message - same true-edit-in-
    place behavior (Discord's message-edit endpoint supports replacing
    an attachment via attachments: [] in the same PATCH, see
    _patch_message_with_file), same reason: a delete+repost cycle
    notified on every refresh even when nothing real had changed."""
    if not enabled() or not file_path.exists():
        return None
    state = _load_message_state()
    key = f"{channel_key}:{card_key}"
    tracked_id = state.get(key)
    if tracked_id:
        channel_id = ensure_channels()[channel_key]
        try:
            return _patch_message_with_file(channel_id, tracked_id, file_path, content=content, mime_type=mime_type)
        except DiscordPostError as exc:
            if "HTTP 404" not in str(exc):
                raise
            del state[key]
    result = post_file(channel_key, file_path, content=content, mime_type=mime_type)
    if result and result.get("id"):
        state[key] = result["id"]
        _save_message_state(state)
    return result
