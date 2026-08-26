from __future__ import annotations

import tempfile
from pathlib import Path

import discord_surface_manifest as surfaces
import rivalry
import rivalry_presentation as presentation
import scoreboard


class Tracker:
    guild_id = "guild"

    def __init__(self, fail: bool = False):
        self.fail = fail
        self.cards: list[str] = []

    def _request(self, method, path):
        if self.fail:
            raise RuntimeError("discord down")
        return [{"id": "channel", "name": presentation.CHANNEL_NAME}]

    def upsert_singleton_message(self, channel_id, body, token):
        self.cards.append(body)
        return token, 0


def _connections(monkeypatch):
    root = Path(tempfile.mkdtemp())
    monkeypatch.setattr(scoreboard, "DB_PATH", root / "score.db")
    monkeypatch.setattr(rivalry, "DB_PATH", root / "rivalry.db")
    monkeypatch.setattr(surfaces, "DB_PATH", root / "surfaces.db")
    return scoreboard.connect_db(), rivalry.connect_db(), surfaces.connect_db()


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


def test_presentation_redacts_open_trade_and_reconciles_cards(monkeypatch):
    score, chat, manifest = _connections(monkeypatch)
    scoreboard.record_trade_open(
        score, trade_id="live", bot="BLACKTIDE", generation=1,
        opened_at="2026-08-25T09:30:00-05:00",
        side="CALL", contract_symbol="SPY-SECRET", entry_price=1.0,
        contracts=1, entry_bankroll=1000.0,
    )
    tracker = Tracker()
    result = presentation.publish_competition_surfaces(score, chat, manifest, tracker)
    assert result["ok"] is True
    rendered = "\n".join(tracker.cards)
    assert "Position OPEN" in rendered
    assert "SPY-SECRET" not in rendered
    assert len(result["published"]) == 2


def test_discord_outage_is_returned_and_cannot_touch_official_trade(monkeypatch):
    score, chat, manifest = _connections(monkeypatch)
    before = scoreboard.current_bankroll(score, "BLACKTIDE")
    result = presentation.publish_competition_surfaces(score, chat, manifest, Tracker(fail=True))
    assert result["ok"] is False
    assert "discord down" in result["error"]
    assert scoreboard.current_bankroll(score, "BLACKTIDE") == before
    assert surfaces.compute_health(manifest, "competition-scoreboard-card") == surfaces.PUBLISH_FAILED


def test_rivalry_card_hides_a_claim_without_a_matching_closed_trade(monkeypatch):
    score, chat, _manifest = _connections(monkeypatch)
    rivalry.record_rivalry_event(
        chat, rivalry_event_id="stale-demo", event_group_id="demo", trigger="TRADE_CLOSED_WIN",
        speaker="AXIOM", message="invented win", trade_reference="not-in-referee",
        public_score_snapshot={"bot": "AXIOM"}, now=__import__("datetime").datetime.now().astimezone(),
    )
    assert "invented win" not in presentation.render_rivalry(score, chat)


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
