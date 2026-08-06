from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


RETIRED_STABLE_IDS = ("shadow-candidates",)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _resolve_channel(guild: Any, channel_id: str) -> Any | None:
    try:
        numeric_id = int(channel_id)
    except (TypeError, ValueError):
        return None

    getter = getattr(guild, "get_channel", None)
    if getter is not None:
        channel = getter(numeric_id)
        if channel is not None:
            return channel

    fetcher = getattr(guild, "fetch_channel", None)
    if fetcher is not None:
        try:
            return await fetcher(numeric_id)
        except Exception:
            return None
    return None


def _is_not_found(exc: Exception) -> bool:
    if type(exc).__name__ == "NotFound":
        return True
    return int(getattr(exc, "status", 0) or 0) == 404


async def retire_stable_messages(
    database: Any,
    guild: Any,
    *,
    bot_user_id: str,
) -> dict[str, Any]:
    """Delete bot-authored messages for features removed from the real dashboard.

    The state row is removed only after the message is deleted or confirmed absent.
    Human-authored messages are never touched.
    """

    placeholders = ",".join("?" for _ in RETIRED_STABLE_IDS)
    rows = database.query(
        "SELECT stable_id,channel_name,message_id FROM discord_message_state "
        f"WHERE stable_id IN ({placeholders})",
        RETIRED_STABLE_IDS,
    )
    result: dict[str, Any] = {
        "status": "PASS",
        "retired_ids": list(RETIRED_STABLE_IDS),
        "deleted": [],
        "already_absent": [],
        "blocked": [],
        "observed_at": _utc_now(),
    }

    for row in rows:
        stable_id = str(row["stable_id"])
        channel_id = str(row.get("channel_name") or "")
        message_id = str(row.get("message_id") or "")
        channel = await _resolve_channel(guild, channel_id)

        if channel is None or not message_id:
            database.execute(
                "DELETE FROM discord_message_state WHERE stable_id=?",
                (stable_id,),
            )
            result["already_absent"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id or None,
                    "message_id": message_id or None,
                }
            )
            continue

        fetch_message = getattr(channel, "fetch_message", None)
        if fetch_message is None:
            result["blocked"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reason": "channel-does-not-support-message-fetch",
                }
            )
            continue

        try:
            message = await fetch_message(int(message_id))
        except Exception as exc:
            if _is_not_found(exc):
                database.execute(
                    "DELETE FROM discord_message_state WHERE stable_id=?",
                    (stable_id,),
                )
                result["already_absent"].append(
                    {
                        "stable_id": stable_id,
                        "channel_id": channel_id,
                        "message_id": message_id,
                    }
                )
                continue
            result["blocked"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            continue

        author = getattr(message, "author", None)
        author_id = str(getattr(author, "id", ""))
        if author_id != str(bot_user_id):
            result["blocked"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reason": "message-is-not-authored-by-this-bot",
                }
            )
            continue

        delete = getattr(message, "delete", None)
        if delete is None:
            result["blocked"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reason": "message-delete-is-not-supported",
                }
            )
            continue

        try:
            await delete()
            database.execute(
                "DELETE FROM discord_message_state WHERE stable_id=?",
                (stable_id,),
            )
            result["deleted"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                }
            )
        except Exception as exc:
            result["blocked"].append(
                {
                    "stable_id": stable_id,
                    "channel_id": channel_id,
                    "message_id": message_id,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )

    if result["blocked"]:
        result["status"] = "DEGRADED"
    return result
