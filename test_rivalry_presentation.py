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
