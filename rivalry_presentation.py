"""Failure-isolated, privacy-preserving Discord competition presentation."""

from __future__ import annotations

from typing import Any

import discord_surface_manifest as surfaces
import discord_transport
import rivalry
import scoreboard

CHANNEL_NAME = "blacktide-vs-claude"


def render_scoreboard(connection: Any) -> str:
    rows = [scoreboard.scoreboard_snapshot(connection, bot) for bot in scoreboard.BOTS]
    lines = ["## BLACKTIDE vs AXIOM — Official Scoreboard"]
    for row in rows:
        lines.extend((
            f"### {row['bot']}",
            f"Generation {row['generation']} · Bankroll ${row['current_bankroll']:.2f} · "
            f"Lifetime P/L ${row['lifetime_pnl']:.2f}",
            f"Trades {row['trade_count_lifetime']} · Position {row['current_position_status']}",
        ))
    lines.append("Live positions are intentionally shown only as OPEN or FLAT.")
    return "\n".join(lines)


def render_rivalry(connection: Any) -> str:
    lines = ["## BLACKTIDE vs AXIOM — Rivalry"]
    for item in reversed(rivalry.public_rivalry_history(connection, limit=12)):
        lines.append(f"**{item['speaker']}** · {item['message']}")
    if len(lines) == 1:
        lines.append("No official rivalry events yet.")
    return "\n".join(lines)


def _channel_id(tracker: discord_transport.DiscordTracker) -> str:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    matches = [str(row.get("id") or "") for row in (channels or []) if row.get("name") == CHANNEL_NAME]
    if len(matches) != 1:
        raise discord_transport.DiscordError(
            f"expected exactly one #{CHANNEL_NAME} channel, found {len(matches)}"
        )
    return matches[0]


def publish_competition_surfaces(
    score_connection: Any,
    rivalry_connection: Any,
    surface_connection: Any,
    tracker: discord_transport.DiscordTracker,
) -> dict[str, Any]:
    """Publish both persistent cards; errors are recorded and returned.

    No exception crosses this presentation boundary, so Discord/rivalry can
    never alter or stop trading.  Callers can alert on the returned health.
    """
    surfaces.reconcile_canonical_competition_surfaces(surface_connection)
    result: dict[str, Any] = {"ok": False, "published": (), "error": None}
    published: list[str] = []
    try:
        channel_id = _channel_id(tracker)
        cards = (
            ("competition-scoreboard-card", render_scoreboard(score_connection), "TSQ-COMPETITION-SCOREBOARD"),
            ("competition-rivalry-card", render_rivalry(rivalry_connection), "TSQ-COMPETITION-RIVALRY"),
        )
        for surface_id, body, token in cards:
            message_id, _ = tracker.upsert_singleton_message(channel_id, body, token)
            surfaces.record_surface_event(
                surface_connection, surface_id=surface_id, event_type="PUBLISH",
                detail=f"message_id={message_id}",
            )
            published.append(surface_id)
        result.update(ok=True, published=tuple(published))
    except Exception as exc:  # presentation failure must remain isolated
        for surface_id in ("competition-scoreboard-card", "competition-rivalry-card"):
            try:
                surfaces.record_surface_event(
                    surface_connection, surface_id=surface_id, event_type="ERROR",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        result.update(published=tuple(published), error=f"{type(exc).__name__}: {exc}")
    return result
