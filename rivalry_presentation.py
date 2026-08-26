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


_BOT_CHANNEL_ID_CACHE: dict[str, str] = {}


def _resolve_channel_id(tracker: discord_transport.DiscordTracker, name: str) -> str:
    cached = _BOT_CHANNEL_ID_CACHE.get(name)
    if cached:
        return cached
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    matches = [str(row.get("id") or "") for row in (channels or []) if row.get("name") == name]
    if len(matches) != 1:
        raise discord_transport.DiscordError(f"expected exactly one #{name} channel, found {len(matches)}")
    _BOT_CHANNEL_ID_CACHE[name] = matches[0]
    return matches[0]


def render_bot_dashboard(connection: Any, bot: str) -> str:
    row = scoreboard.scoreboard_snapshot(connection, bot)
    lines = [
        f"## {bot} — Dashboard",
        f"Generation {row['generation']} · Bankroll ${row['current_bankroll']:.2f}",
        f"Lifetime P/L ${row['lifetime_pnl']:.2f} · This generation P/L ${row['generation_pnl']:.2f}",
        f"Trades: {row['trade_count_lifetime']} lifetime · {row['trade_count_generation']} this generation",
    ]
    win_rate = row.get("win_rate")
    profit_factor = row.get("profit_factor")
    lines.append(
        "Win rate " + (f"{win_rate:.1%}" if win_rate is not None else "n/a")
        + " · Profit factor " + (f"{profit_factor:.2f}" if profit_factor is not None else "n/a")
    )
    streak = row.get("current_streak") or {}
    if streak.get("count"):
        lines.append(f"Current streak: {streak['count']} {streak.get('kind', '')}".strip())
    drawdown = row.get("current_drawdown")
    if drawdown is not None:
        lines.append(f"Current drawdown: ${drawdown:.2f}")
    lines.append(f"Position: {row['current_position_status']} · Busts (lifetime): {row.get('bust_count', 0)}")
    return "\n".join(lines)


def render_bot_held_trade(connection: Any, bot: str) -> str:
    status = scoreboard.current_position_status(connection, bot)
    if not status:
        return f"## {bot} — Held Trade\nNo open position. Status: FLAT."
    return "\n".join((
        f"## {bot} — Held Trade",
        f"Status: OPEN · generation {status.get('generation')}",
        f"Opened: {status.get('opened_at')}",
        "Contract, side, and size stay private (Section 14) - only that a "
        "position is open is shown here.",
    ))


def render_bot_winners_losers(connection: Any, bot: str) -> str:
    trades = scoreboard.recent_closed_trades(connection, bot, limit=20)
    lines = [f"## {bot} — Winners & Losers"]
    if not trades:
        lines.append("No closed trades yet.")
        return "\n".join(lines)
    for trade in trades:
        marker = {"WIN": "🟩", "LOSS": "🟥"}.get(trade["outcome"], "⬜")
        lines.append(
            f"{marker} **{trade['outcome']}** · ${trade['pnl_usd']:+.2f} · "
            f"gen {trade['generation']} · {trade['closed_at']}"
        )
    return "\n".join(lines)


def publish_bot_surfaces(
    score_connection: Any,
    surface_connection: Any,
    tracker: discord_transport.DiscordTracker,
    bot: str,
) -> dict[str, Any]:
    """Per-bot dashboard/held-trade/winners-losers cards, same
    failure-isolated shape as publish_competition_surfaces above. The
    winners/losers channel is one upserted "last 20 trades" card (matching
    render_rivalry()'s already-working "last N events" pattern) rather than
    one Discord message per trade - no new cursor/state bookkeeping needed."""
    prefix = bot.lower()
    result: dict[str, Any] = {"ok": False, "published": (), "error": None}
    published: list[str] = []
    surface_ids = (f"{prefix}-dashboard-card", f"{prefix}-held-trade-card", f"{prefix}-winners-losers-card")
    try:
        cards = (
            (surface_ids[0], render_bot_dashboard(score_connection, bot), f"{prefix}-dashboard", f"{prefix}-dashboard"),
            (surface_ids[1], render_bot_held_trade(score_connection, bot), f"{prefix}-held-trade", f"{prefix}-held-trades"),
            (surface_ids[2], render_bot_winners_losers(score_connection, bot), f"{prefix}-winners-losers", f"{prefix}-winners-losers"),
        )
        for surface_id, body, token, channel_name in cards:
            channel_id = _resolve_channel_id(tracker, channel_name)
            message_id, _ = tracker.upsert_singleton_message(channel_id, body, token)
            surfaces.record_surface_event(
                surface_connection, surface_id=surface_id, event_type="PUBLISH",
                detail=f"message_id={message_id}",
            )
            published.append(surface_id)
        result.update(ok=True, published=tuple(published))
    except Exception as exc:  # presentation failure must remain isolated
        for surface_id in surface_ids:
            try:
                surfaces.record_surface_event(
                    surface_connection, surface_id=surface_id, event_type="ERROR",
                    detail=f"{type(exc).__name__}: {exc}",
                )
            except Exception:
                pass
        result.update(published=tuple(published), error=f"{type(exc).__name__}: {exc}")
    return result


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
