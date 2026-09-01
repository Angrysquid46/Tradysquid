"""Failure-isolated, privacy-preserving Discord competition presentation."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import discord_surface_manifest as surfaces
import discord_transport
import rivalry
import scoreboard

CHANNEL_NAME = "blacktide-vs-claude"
CHART_DIR = Path(__file__).resolve().parent / "docs" / "tickers"
LEGACY_RIVALRY_TOKEN = "TSQ-COMPETITION-RIVALRY"
# Bump when a persisted per-bot Discord surface changes shape. The scheduler
# fingerprints this so a presentation release refreshes old cards even when
# the underlying trade facts have not changed.
BOT_SURFACE_FORMAT_VERSION = "generation-scoped-bankroll-v2"
# AXIOM permanently removed 2026-08-27 (owner directive) - no longer in
# scoreboard.BOTS/rivalry.BOTS either, not just this presentation list.
# GROK added 2026-08-30 as independent Grok/xAI competitor.
PUBLIC_BOTS = ("BLACKTIDE", "RIPTIDE", "SURGE", "GROK")


def render_scoreboard(connection: Any) -> str:
    rows = [scoreboard.scoreboard_snapshot(connection, bot) for bot in PUBLIC_BOTS]
    lines = ["## Official Scoreboard"]
    for row in rows:
        lines.extend((
            f"### {row['bot']}",
            f"Generation {row['generation']} · Bankroll ${row['current_bankroll']:.2f} · "
            f"Lifetime P/L ${row['lifetime_pnl']:.2f}",
            f"Trades {row['trade_count_lifetime']} · Position {row['current_position_status']}",
        ))
    lines.append("Live positions are intentionally shown only as OPEN or FLAT.")
    return "\n".join(lines)


def _verified_rivalry_events(score_connection: Any, rivalry_connection: Any) -> list[dict[str, Any]]:
    """Return public events whose trade claims have referee proof.

    Presentation must never revive an old test/demo message as if it were a
    live result. Any event with a trade reference is shown only when that
    exact immutable, closed trade exists for the named speaker.
    """
    verified: list[dict[str, Any]] = []
    for item in rivalry.public_rivalry_history(rivalry_connection, limit=50):
        reference = str(item.get("trade_reference") or "").strip()
        if reference:
            row = score_connection.execute(
                "SELECT 1 FROM official_trades WHERE trade_id=? AND bot=? AND closed_at IS NOT NULL",
                (reference, item["speaker"]),
            ).fetchone()
            if row is None:
                continue
        verified.append(item)
    return verified


def render_rivalry(score_connection: Any, rivalry_connection: Any) -> str:
    """Render a compact status, never a historical receipt wall.

    Each verified rivalry event has its own Discord card.  This compact value
    remains useful to the scheduler fingerprint without cramming history into
    one edited message.
    """
    verified = _verified_rivalry_events(score_connection, rivalry_connection)
    awaiting = sum(not str(item.get("discord_message_id") or "").strip() for item in verified)
    if not verified:
        return "## Rivalry\nNo official rivalry events yet."
    return (
        "## Rivalry\n"
        f"{len(verified)} verified event cards · {awaiting} awaiting publication."
    )


def render_rivalry_event(item: dict[str, Any]) -> str:
    """Render one verifiable rivalry event as one readable Discord card."""
    timestamp = datetime.fromisoformat(str(item["timestamp"])).strftime("%b %d, %Y %I:%M %p")
    outcome = "Verified win" if item["trigger"] == "TRADE_CLOSED_WIN" else "Verified loss"
    return "\n".join((
        "## Rivalry",
        f"### {item['speaker']} — {outcome}",
        item["message"],
        "### Referee receipt",
        f"Official paper close verified · {timestamp}",
    ))


def _channel_id(tracker: discord_transport.DiscordTracker) -> str:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    matches = [str(row.get("id") or "") for row in (channels or []) if row.get("name") == CHANNEL_NAME]
    if len(matches) != 1:
        raise discord_transport.DiscordError(
            f"expected exactly one #{CHANNEL_NAME} channel, found {len(matches)}"
        )
    return matches[0]


def _remove_legacy_rivalry_wall(tracker: discord_transport.DiscordTracker, channel_id: str) -> int:
    """Delete the retired history-wall card; individual event cards replace it."""
    messages = tracker._request("GET", f"/channels/{channel_id}/messages?limit=100")
    removed = 0
    for message in messages if isinstance(messages, list) else []:
        if LEGACY_RIVALRY_TOKEN not in discord_transport.message_search_text(message):
            continue
        message_id = str(message.get("id") or "")
        if message_id:
            tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            removed += 1
    return removed


def _remove_legacy_singleton_card(
    tracker: discord_transport.DiscordTracker, channel_id: str, legacy_token: str
) -> int:
    """Remove a retired aggregate card before immutable event cards replace it."""
    messages = tracker._request("GET", f"/channels/{channel_id}/messages?limit=100")
    removed = 0
    for message in messages if isinstance(messages, list) else []:
        if legacy_token not in discord_transport.message_search_text(message):
            continue
        message_id = str(message.get("id") or "")
        if message_id:
            tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            removed += 1
    return removed


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
    """### -prefixed sections so discord_card() renders each stat as its
    own boxed embed field (owner request: "stat cards on the dashboards"),
    not one run-together paragraph."""
    row = scoreboard.scoreboard_snapshot(connection, bot)
    win_rate = row.get("win_rate")
    profit_factor = row.get("profit_factor")
    streak = row.get("current_streak") or {}
    streak_text = f"{streak['count']} {streak.get('kind', '')}".strip() if streak.get("count") else "None"
    drawdown = row.get("current_drawdown")
    return "\n".join((
        f"## {bot} — Dashboard",
        "### Balance", f"${row['current_bankroll']:.2f}",
        "### Generation", f"{row['generation']} · Busts (lifetime): {row.get('bust_count', 0)}",
        "### Lifetime P/L", f"${row['lifetime_pnl']:+.2f}",
        "### This Generation P/L", f"${row['generation_pnl']:+.2f}",
        "### Trades", f"{row['trade_count_lifetime']} lifetime · {row['trade_count_generation']} this generation",
        "### Win Rate", (f"{win_rate:.1%}" if win_rate is not None else "n/a"),
        "### Profit Factor", (f"{profit_factor:.2f}" if profit_factor is not None else "n/a"),
        "### Current Streak", streak_text,
        "### Current Drawdown", (f"${drawdown:.2f}" if drawdown is not None else "$0.00"),
        "### Position", row["current_position_status"],
    ))


def render_bankroll_chart(bot: str, points: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    """Render only one generation's equity curve.

    Be defensive when called with legacy all-generation points: a reset is a
    new trial, never a bankroll gain, so no line may connect generations.
    """
    from PIL import Image, ImageDraw, ImageFont

    generation = int(points[-1].get("generation", 1)) if points else 1
    generation_points = [point for point in points if int(point.get("generation", generation)) == generation]
    actual_values = [float(point["bankroll"]) for point in generation_points]
    has_closed_trades = len(actual_values) > 1
    values = actual_values or [scoreboard.STARTING_BANKROLL_USD]
    scale_values = values if len(values) > 1 else values * 2

    width, height = 1200, 600
    left, right, top, bottom = 90, 40, 80, 60
    plot_width = width - left - right
    plot_height = height - top - bottom
    low = max(0.0, min(scale_values) - 25.0)
    high = max(scale_values + [scoreboard.STARTING_BANKROLL_USD]) * 1.1

    image = Image.new("RGB", (width, height), "#0b1420")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=15)
    title_font = ImageFont.load_default(size=26)

    def xy(index: int, value: float) -> tuple[int, int]:
        x = left + int(index / max(len(scale_values) - 1, 1) * plot_width)
        y = top + int((high - value) / max(high - low, 0.01) * plot_height)
        return x, y

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#26364a", width=1)
        draw.text((12, y - 8), f"${value:.0f}", fill="#9fb0c3", font=small)

    starting_y = xy(0, scoreboard.STARTING_BANKROLL_USD)[1]
    draw.line((left, starting_y, width - right, starting_y), fill="#3b4a5e", width=1)
    draw.text((width - 230, starting_y - 20), "start $1,000", fill="#6b7f97", font=small)

    if has_closed_trades:
        line_points = [xy(index, value) for index, value in enumerate(values)]
        draw.line(line_points, fill="#7dd3fc", width=3)

    current, peak = values[-1], max(values)
    draw.text((left, 20), f"{bot} · GENERATION {generation} BANKROLL", fill="#f8fafc", font=title_font)
    summary = (
        f"Current ${current:.2f} · Generation peak ${peak:.2f} · resets excluded"
        if has_closed_trades else
        f"No closed trades yet · Generation {generation} reset baseline $1,000"
    )
    draw.text(
        (left, 52),
        summary,
        fill="#b8c7d9", font=small,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return {"current": current, "peak": peak, "generation": generation, "has_closed_trades": has_closed_trades}


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


_OCC_SYMBOL = re.compile(
    r"^(?P<ticker>[A-Z]+)(?P<date>\d{6})(?P<right>[CP])(?P<strike>\d{8})$"
)


def _format_contract(trade: dict[str, Any]) -> str:
    """Turn an OCC option symbol into a compact, human-auditable contract.

    Fall back to the recorded symbol rather than guessing if a provider ever
    supplies a non-OCC identifier.
    """
    symbol = str(trade.get("contract_symbol") or "").strip().upper()
    match = _OCC_SYMBOL.fullmatch(symbol)
    if not match:
        return symbol or "Recorded contract unavailable"
    expiry_date = datetime.strptime(match.group("date"), "%y%m%d")
    expiration = f"{expiry_date.strftime('%b')} {expiry_date.day}, {expiry_date.year}"
    strike = int(match.group("strike")) / 1000
    right = "Call" if match.group("right") == "C" else "Put"
    return f"{match.group('ticker')} ${strike:,.3f} {right} · expires {expiration}"


def _format_timestamp(value: object) -> str:
    try:
        timestamp = datetime.fromisoformat(str(value))
        return (
            f"{timestamp.strftime('%b')} {timestamp.day}, {timestamp.year} "
            f"{timestamp.hour % 12 or 12}:{timestamp:%M} {timestamp:%p}"
        )
    except (TypeError, ValueError):
        return str(value or "not recorded")


def _closed_session_label(value: object) -> str:
    """Return a visible calendar-day divider for a closed trade."""
    try:
        timestamp = datetime.fromisoformat(str(value))
        return f"Closed {timestamp.strftime('%b')} {timestamp.day}, {timestamp.year}"
    except (TypeError, ValueError):
        return "Closed date unavailable"


def _render_trade_feed(bot: str, label: str, marker: str, trades: list[dict[str, Any]]) -> str:
    lines = [f"## {bot} — {label}"]
    if not trades:
        lines.append(f"No {label.lower()} yet.")
        return "\n".join(lines)
    previous_session: str | None = None
    for trade in trades:
        session = _closed_session_label(trade.get("closed_at"))
        if session != previous_session:
            lines.extend((f"### {session}", ""))
            previous_session = session
        entry = float(trade["entry_price"])
        exit_price = float(trade["exit_price"])
        percent = ((exit_price - entry) / entry) * 100 if entry else 0.0
        contracts = int(trade["contracts"])
        pnl = float(trade["pnl_usd"])
        pnl_text = f"{'+' if pnl >= 0 else '-'}${abs(pnl):.2f}"
        lines.extend((
            f"{marker} **{pnl_text} ({percent:+.1f}%)** · generation {trade['generation']}",
            _format_contract(trade),
            f"{contracts} contract{'s' if contracts != 1 else ''} · bought ${entry:.2f} → sold ${exit_price:.2f}",
            f"Opened {_format_timestamp(trade.get('opened_at'))} · closed {_format_timestamp(trade.get('closed_at'))}",
            f"Trade ID: `{trade['trade_id']}`",
            "",
        ))
    return "\n".join(lines)


def render_closed_trade_card(bot: str, label: str, marker: str, trade: dict[str, Any]) -> str:
    """Render one immutable, fully auditable closed trade as one card."""
    return _render_trade_feed(bot, f"{label} · Official Close", marker, [trade])


def render_bot_winners(connection: Any, bot: str) -> str:
    trades = scoreboard.recent_closed_trades(connection, bot, limit=20, outcome="WIN")
    return _render_trade_feed(bot, "Winners", "🟩", trades)


def render_bot_losers(connection: Any, bot: str) -> str:
    trades = scoreboard.recent_closed_trades(connection, bot, limit=20, outcome="LOSS")
    return _render_trade_feed(bot, "Losers", "🟥", trades)


def _replace_bot_chart(
    tracker: discord_transport.DiscordTracker,
    channel_id: str,
    path: Path,
    caption: str,
    search_token: str,
) -> str:
    """Discord can't edit an attachment in place, so an "updating chart" is
    really post-new-then-delete-old."""
    recent = tracker._request("GET", f"/channels/{channel_id}/messages?limit=50")
    old_ids = [
        str(message.get("id") or "")
        for message in (recent if isinstance(recent, list) else [])
        if ((message.get("author") or {}).get("bot") or message.get("webhook_id"))
        and search_token in discord_transport.message_search_text(message)
    ]
    stamped_caption = f"{caption[:1850]}\n-# {search_token}"
    response = tracker.send_channel_file(channel_id, path, content=stamped_caption)
    new_id = str((response or {}).get("id") or "")
    for old_id in old_ids:
        if old_id and old_id != new_id:
            try:
                tracker._request("DELETE", f"/channels/{channel_id}/messages/{old_id}")
            except discord_transport.DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
    return new_id


def publish_bot_surfaces(
    score_connection: Any,
    surface_connection: Any,
    tracker: discord_transport.DiscordTracker,
    bot: str,
) -> dict[str, Any]:
    """Per-bot dashboard (stat card + bankroll chart), held-trade,
    winners, and losers surfaces."""
    prefix = bot.lower()
    result: dict[str, Any] = {"ok": False, "published": (), "error": None}
    published: list[str] = []
    surface_ids = (
        f"{prefix}-dashboard-card", f"{prefix}-dashboard-chart", f"{prefix}-held-trade-card",
        f"{prefix}-winners-card", f"{prefix}-losers-card",
    )
    try:
        surfaces.reconcile_canonical_bot_surfaces(surface_connection)
        dashboard_channel_id = _resolve_channel_id(tracker, f"{prefix}-dashboard")
        message_id, _ = tracker.upsert_singleton_message(
            dashboard_channel_id, render_bot_dashboard(score_connection, bot), f"{prefix}-dashboard"
        )
        surfaces.record_surface_event(
            surface_connection, surface_id=surface_ids[0], event_type="PUBLISH", detail=f"message_id={message_id}",
        )
        published.append(surface_ids[0])

        generation = scoreboard.current_generation(score_connection, bot)
        points = scoreboard.bankroll_history(score_connection, bot, generation)
        output = CHART_DIR / f"{prefix}-bankroll.png"
        metrics = render_bankroll_chart(bot, points, output)
        caption = (
            f"📈 **{bot} generation {metrics['generation']} bankroll** · "
            f"current ${metrics['current']:.2f} · generation peak ${metrics['peak']:.2f} · "
            "resets excluded"
        )
        chart_message_id = _replace_bot_chart(
            tracker, dashboard_channel_id, output, caption, f"{prefix}-bankroll-chart"
        )
        surfaces.record_surface_event(
            surface_connection, surface_id=surface_ids[1], event_type="PUBLISH",
            detail=f"message_id={chart_message_id}",
        )
        published.append(surface_ids[1])

        held_channel_id = _resolve_channel_id(tracker, f"{prefix}-held-trades")
        held_message_id, _ = tracker.upsert_singleton_message(
            held_channel_id, render_bot_held_trade(score_connection, bot), f"{prefix}-held-trade"
        )
        surfaces.record_surface_event(
            surface_connection, surface_id=surface_ids[2], event_type="PUBLISH",
            detail=f"message_id={held_message_id}",
        )
        published.append(surface_ids[2])

        for surface_id, label, marker, outcome, channel_name in (
            (surface_ids[3], "Winner", "🟩", "WIN", f"{prefix}-winners"),
            (surface_ids[4], "Loser", "🟥", "LOSS", f"{prefix}-losers"),
        ):
            channel_id = _resolve_channel_id(tracker, channel_name)
            _remove_legacy_singleton_card(tracker, channel_id, channel_name)
            trades = scoreboard.recent_closed_trades(
                score_connection, bot, limit=20, outcome=outcome
            )
            for trade in reversed(trades):
                trade_id = str(trade["trade_id"])
                card_message_id, _ = tracker.upsert_singleton_message(
                    channel_id,
                    render_closed_trade_card(bot, label, marker, trade),
                    f"TSQ-{prefix.upper()}-{outcome}-{trade_id}",
                )
                surfaces.record_surface_event(
                    surface_connection, surface_id=surface_id, event_type="PUBLISH",
                    detail=f"trade_id={trade_id}; message_id={card_message_id}",
                )
                published.append(f"{surface_id}:{trade_id}")
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
    never alter or stop trading.
    """
    surfaces.reconcile_canonical_competition_surfaces(surface_connection)
    result: dict[str, Any] = {"ok": False, "published": (), "error": None}
    published: list[str] = []
    try:
        channel_id = _channel_id(tracker)
        cards = (("competition-scoreboard-card", render_scoreboard(score_connection), "TSQ-COMPETITION-SCOREBOARD"),)
        for surface_id, body, token in cards:
            message_id, _ = tracker.upsert_singleton_message(channel_id, body, token)
            surfaces.record_surface_event(
                surface_connection, surface_id=surface_id, event_type="PUBLISH",
                detail=f"message_id={message_id}",
            )
            published.append(surface_id)
        _remove_legacy_rivalry_wall(tracker, channel_id)
        for event in reversed(_verified_rivalry_events(score_connection, rivalry_connection)):
            if str(event.get("discord_message_id") or "").strip():
                continue
            event_id = str(event["rivalry_event_id"])
            message_id, _ = tracker.upsert_singleton_message(
                channel_id, render_rivalry_event(event), f"TSQ-RIVALRY-{event_id}"
            )
            rivalry.record_discord_message_id(
                rivalry_connection,
                rivalry_event_id=event_id,
                discord_message_id=message_id,
            )
            surfaces.record_surface_event(
                surface_connection, surface_id="competition-rivalry-card", event_type="PUBLISH",
                detail=f"event_id={event_id}; message_id={message_id}",
            )
            published.append(f"competition-rivalry-card:{event_id}")
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
