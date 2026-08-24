"""Generic Discord REST transport - the working plumbing survivor category
Master Spec Section 2 names explicitly ("working GitHub/Discord/market-data/
broker/env/credential plumbing"), extracted out of spy_scanner.py before its
Phase 3 purge.

This is deliberately the NARROW surface: auth, retry/rate-limit handling,
and a generic "keep exactly one bot-authored card for a stable title"
upsert. It does not include spy_scanner's discover()/forum/tag-routing
logic - that machinery hard-requires the old trade-journal forum and its
five status tags to exist (raises DiscordError if they don't), which makes
it structurally trade-journal-specific, not generic transport. Any feature
that depended on that (member upgrade-request reaction moderation, a
general-chat history-clear command) was dropped in the purge rather than
force-fit to survive without it - see governance/PHASES.json's Phase 3
discovered_subphases for the follow-up note.
"""

from __future__ import annotations

import os
import threading
import time
from typing import Any

import requests

DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

DISCORD_FORMAT_VERSION = "13"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Tradysquids-TradeBot/1.0"})

CARD_COLORS = {
    "entry": 0x3498DB,
    "qualified": 0x9B59B6,
    "hold": 0xF1C40F,
    "win": 0x2ECC71,
    "loss": 0xE74C3C,
    "scratch": 0x95A5A6,
    "scanner": 0x00A8E8,
    "performance": 0x5865F2,
    "error": 0xE74C3C,
    "status": 0x607D8B,
}


def card_color_for_text(content: str) -> int:
    title = next((line for line in content.splitlines() if line.strip()), content).upper()
    if "ERROR" in title or "FAILED" in title or "🚨" in title:
        return CARD_COLORS["error"]
    if "QUALIFIED" in title:
        return CARD_COLORS["qualified"]
    if "ENTRY" in title:
        return CARD_COLORS["entry"]
    if "· WIN" in title or "WINS SUMMARY" in title or "🏆" in title or "🟩" in title:
        return CARD_COLORS["win"]
    if "· LOSS" in title or "LOSSES SUMMARY" in title or "🟥" in title:
        return CARD_COLORS["loss"]
    if "SCRATCH" in title:
        return CARD_COLORS["scratch"]
    if "HOLD" in title or "POSITION" in title:
        return CARD_COLORS["hold"]
    if "SCAN" in title:
        return CARD_COLORS["scanner"]
    if "PERFORMANCE" in title or "STRATEGY" in title or "REPORT" in title or "RECAP" in title:
        return CARD_COLORS["performance"]
    return CARD_COLORS["status"]


def discord_card(content: str, *, footer_suffix: str = "") -> dict[str, Any]:
    """Convert markdown into a native Discord embed card.

    footer_suffix appends a searchable identifier to the footer text, which
    is real embed text Discord renders (small, at the bottom) so it is
    genuinely searchable by message_search_text, not a comment that gets
    thrown away."""
    raw_lines = [line.rstrip() for line in content.strip().splitlines()]
    title = "Tradysquids TradeBot"
    description_lines: list[str] = []
    fields: list[dict[str, Any]] = []
    current_name = ""
    current_value: list[str] = []

    def flush_field() -> None:
        nonlocal current_name, current_value
        if not current_name:
            return
        value = "\n".join(current_value).strip() or "—"
        fields.append({
            "name": current_name[:256],
            "value": value[:1024],
            "inline": False,
        })
        current_name = ""
        current_value = []

    for line in raw_lines:
        if line.startswith("## ") and title == "Tradysquids TradeBot":
            title = line[3:].strip()
            continue
        if line.startswith("# ") and title == "Tradysquids TradeBot":
            title = line[2:].strip()
            continue
        if line.startswith("### "):
            flush_field()
            current_name = line[4:].strip()
            continue
        if current_name:
            current_value.append(line)
        else:
            description_lines.append(line)
    flush_field()

    description = "\n".join(description_lines).strip()
    footer_text = f"Tradysquids TradeBot · Card format {DISCORD_FORMAT_VERSION}"
    if footer_suffix:
        footer_text = f"{footer_text} · {footer_suffix}"
    embed: dict[str, Any] = {
        "title": title[:256],
        "color": card_color_for_text(content),
        "footer": {"text": footer_text[:2048]},
    }
    if description:
        embed["description"] = description[:4096]
    if fields:
        embed["fields"] = fields[:25]
    return embed


def message_search_text(message: dict[str, Any]) -> str:
    parts = [str(message.get("content") or "")]
    for embed in message.get("embeds") or []:
        parts.append(str(embed.get("title") or ""))
        parts.append(str(embed.get("description") or ""))
        for field in embed.get("fields") or []:
            parts.append(str(field.get("name") or ""))
            parts.append(str(field.get("value") or ""))
        parts.append(str((embed.get("footer") or {}).get("text") or ""))
    return "\n".join(parts)


class DiscordError(RuntimeError):
    pass


def discord_route_is_missing(exc: Exception) -> bool:
    message = str(exc)
    return "HTTP 403" in message or "HTTP 404" in message or "Missing Access" in message


class DiscordTracker:
    """Auth + retry/rate-limit-aware Discord REST client, plus one generic
    singleton-card upsert. Does not implement channel/forum/tag discovery -
    callers that need a channel ID already have one (or resolve it
    themselves); see this module's docstring for why."""

    API_BASE = "https://discord.com/api/v10"
    _discovery_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _discovery_lock = threading.Lock()
    _discovery_ttl_seconds = 300.0

    def __init__(self, token: str, guild_id: str):
        self.token = token
        self.guild_id = guild_id
        self.ready = False
        self.channels: dict[str, str] = {}
        self.tag_ids: dict[str, str] = {}
        self.forum_id = ""
        self.missing_channels: list[str] = []
        self.private_system_channels: set[str] = set()
        self._channel_message_cache: dict[str, list[dict[str, Any]]] = {}
        self._dedupe_swept_at: dict[str, float] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.guild_id)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.enabled:
            raise DiscordError("Discord bot token or guild ID is missing")
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
        }
        url = f"{self.API_BASE}{path}"
        for attempt in range(4):
            try:
                response = SESSION.request(method, url, headers=headers, json=payload, timeout=20)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise DiscordError(f"Discord request failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429:
                try:
                    retry_after = float(response.json().get("retry_after", 1.0))
                except (ValueError, TypeError):
                    retry_after = 1.0
                # Discord can impose a guild-wide cooldown longer than ten
                # seconds during chart/card bursts. Sleeping for less than
                # the advertised window only burns every retry immediately.
                time.sleep(min(max(retry_after, 0.0) + 0.25, 65))
                continue
            if response.status_code >= 500 and attempt < 3:
                time.sleep(2**attempt)
                continue
            if not response.ok:
                body = response.text[:700].replace(self.token, "[REDACTED]")
                raise DiscordError(f"Discord HTTP {response.status_code} for {path}: {body}")
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise DiscordError(f"Discord rate limit retries exhausted for {path}")

    def upsert_singleton_message(
        self,
        channel_id: str,
        content: str,
        search_token: str,
        components: list[dict[str, Any]] | None = None,
    ) -> tuple[str, int]:
        """Keep exactly one bot-authored card for a stable title in a channel."""
        if not channel_id or not search_token:
            return "", 0
        payload = {
            "content": "",
            "embeds": [discord_card(content[:6000])],
            "allowed_mentions": {"parse": []},
        }
        if components:
            payload["components"] = components
        recent = self._request("GET", f"/channels/{channel_id}/messages?limit=100")
        if not isinstance(recent, list):
            recent = []
        matches = [
            message
            for message in recent
            if ((message.get("author") or {}).get("bot") or message.get("webhook_id"))
            and search_token in message_search_text(message)
        ]
        if matches:
            message_id = str(matches[0].get("id") or "")
            self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
            removed = 0
            for duplicate in matches[1:]:
                duplicate_id = str(duplicate.get("id") or "")
                if duplicate_id:
                    self._request("DELETE", f"/channels/{channel_id}/messages/{duplicate_id}")
                    removed += 1
            return message_id, removed
        created = self._request("POST", f"/channels/{channel_id}/messages", payload)
        return str((created or {}).get("id") or ""), 0
