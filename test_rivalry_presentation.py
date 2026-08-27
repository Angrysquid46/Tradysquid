from __future__ import annotations

import tempfile
from pathlib import Path

import discord_surface_manifest as surfaces
import rivalry_presentation as presentation
import scoreboard


class Tracker:
    guild_id = "guild"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.cards: list[str] = []
        self.tokens: set[str] = set()

    def _request(self, method, path):
        if self.fail:
            raise RuntimeError("discord down")
        return [{"id": "channel", "name": presentation.CHANNEL_NAME}]

    def upsert_singleton_message(self, channel_id, body, token):
        if token not in self.tokens:
            self.cards.append(body)
            self.tokens.add(token)
        return token, 0


def _connections(monkeypatch):
    root = Path(tempfile.mkdtemp())
    monkeypatch.setattr(scoreboard, "DB_PATH", root / "score.db")
    monkeypatch.setattr(surfaces, "DB_PATH", root / "surfaces.db")
    return scoreboard.connect_db(), surfaces.connect_db()


def _closed_trade() -> object:
    path = Path(tempfile.mkdtemp()) / "scoreboard.db"
    original = scoreboard.DB_PATH
    scoreboard.DB_PATH = path
    try:
        connection = scoreboard.connect_db()
    finally:
        scoreboard.DB_PATH = original
    scoreboard.record_trade_open(
        connection,
        trade_id="closed-trade-1",
        bot="BLACKTIDE",
        generation=1,
        opened_at="2026-08-26T10:03:20-05:00",
        side="CALL",
        contract_symbol="SPY260826C00766000",
        entry_price=0.85,
        contracts=2,
        entry_bankroll=1000.0,
    )
    scoreboard.record_trade_close(
        connection,
        trade_id="closed-trade-1",
        closed_at="2026-08-26T10:12:20-05:00",
        exit_price=0.96,
        pnl_usd=22.0,
    )
    return connection


def test_closed_trade_feed_contains_referee_audit_fields():
    connection = _closed_trade()
    try:
        trade = scoreboard.recent_closed_trades(connection, "BLACKTIDE", outcome="WIN")[0]
        assert trade["contract_symbol"] == "SPY260826C00766000"
        assert trade["side"] == "CALL"
        assert trade["contracts"] == 2
        assert trade["entry_price"] == 0.85
        assert trade["exit_price"] == 0.96
        assert trade["opened_at"] == "2026-08-26T10:03:20-05:00"
    finally:
        connection.close()


def test_winner_card_renders_full_closed_trade_audit_details():
    connection = _closed_trade()
    try:
        card = presentation.render_bot_winners(connection, "BLACKTIDE")
    finally:
        connection.close()
    assert "SPY $766.000 Call · expires Aug 26, 2026" in card
    assert "2 contracts · bought $0.85 → sold $0.96" in card
    assert "+$22.00 (+12.9%)" in card
    assert "Opened Aug 26, 2026 10:03 AM · closed Aug 26, 2026 10:12 AM" in card
    assert "Trade ID: `closed-trade-1`" in card


def test_winner_card_segregates_trades_by_close_date():
    connection = _closed_trade()
    try:
        scoreboard.record_trade_open(
            connection, trade_id="closed-trade-2", bot="BLACKTIDE", generation=1,
            opened_at="2026-08-27T10:03:20-05:00", side="CALL",
            contract_symbol="SPY260827C00766000", entry_price=0.85,
            contracts=1, entry_bankroll=1022.0,
        )
        scoreboard.record_trade_close(
            connection, trade_id="closed-trade-2", closed_at="2026-08-27T10:12:20-05:00",
            exit_price=0.96, pnl_usd=11.0,
        )
        card = presentation.render_bot_winners(connection, "BLACKTIDE")
    finally:
        connection.close()
    assert "### Closed Aug 27, 2026" in card
    assert "### Closed Aug 26, 2026" in card
    assert card.index("### Closed Aug 27, 2026") < card.index("### Closed Aug 26, 2026")


def test_closed_winner_posts_one_immutable_card_not_a_trade_wall(monkeypatch):
    score, manifest = _connections(monkeypatch)
    scoreboard.record_trade_open(
        score, trade_id="winner-event", bot="BLACKTIDE", generation=1,
        opened_at="2026-08-27T10:00:00-05:00", side="CALL",
        contract_symbol="SPY260827C00766000", entry_price=1.0,
        contracts=1, entry_bankroll=1000.0,
    )
    scoreboard.record_trade_close(
        score, trade_id="winner-event", closed_at="2026-08-27T10:05:00-05:00",
        exit_price=1.1, pnl_usd=10.0,
    )
    monkeypatch.setattr(presentation, "_resolve_channel_id", lambda *_args: "channel")
    monkeypatch.setattr(presentation, "render_bankroll_chart", lambda *_args: {"current": 1010.0, "peak": 1010.0, "busts": 0})
    monkeypatch.setattr(presentation, "_replace_bot_chart", lambda *_args: "chart")
    tracker = Tracker()
    first = presentation.publish_bot_surfaces(score, manifest, tracker, "BLACKTIDE")
    second = presentation.publish_bot_surfaces(score, manifest, tracker, "BLACKTIDE")
    winner_cards = [card for card in tracker.cards if "Trade ID: `winner-event`" in card]
    assert first["ok"] is True
    assert second["ok"] is True
    assert len(winner_cards) == 1
    assert "## BLACKTIDE — Winner · Official Close" in winner_cards[0]
    assert "SPY $766.000 Call · expires Aug 27, 2026" in winner_cards[0]


def test_live_held_trade_remains_redacted():
    path = Path(tempfile.mkdtemp()) / "scoreboard.db"
    original = scoreboard.DB_PATH
    scoreboard.DB_PATH = path
    try:
        connection = scoreboard.connect_db()
    finally:
        scoreboard.DB_PATH = original
    try:
        scoreboard.record_trade_open(
            connection,
            trade_id="open-trade-1",
            bot="BLACKTIDE",
            generation=1,
            opened_at="2026-08-26T10:03:20-05:00",
            side="CALL",
            contract_symbol="SPY260826C00766000",
            entry_price=0.85,
            contracts=2,
            entry_bankroll=1000.0,
        )
        card = presentation.render_bot_held_trade(connection, "BLACKTIDE")
    finally:
        connection.close()
    assert "SPY260826C00766000" not in card
    assert "OPEN" in card
