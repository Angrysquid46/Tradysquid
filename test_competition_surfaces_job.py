from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import discord_surface_manifest as surfaces
import discord_transport
import local_information_engine as lie
import rivalry
import scoreboard


@pytest.fixture
def connections(monkeypatch):
    root = Path(tempfile.mkdtemp())
    monkeypatch.setattr(scoreboard, "DB_PATH", root / "score.db")
    monkeypatch.setattr(rivalry, "DB_PATH", root / "rivalry.db")
    monkeypatch.setattr(surfaces, "DB_PATH", root / "surfaces.db")
    monkeypatch.setattr(lie, "DB_PATH", root / "engine.db")
    monkeypatch.setattr(discord_transport, "DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(discord_transport, "DISCORD_GUILD_ID", "guild")
    return lie.connect_db()


def _stub_publishers(monkeypatch):
    calls = {"combined": 0, "bots": []}

    def fake_combined(*args, **kwargs):
        calls["combined"] += 1
        return {"ok": True, "published": (), "error": None}

    def fake_bot(score_connection, surface_connection, tracker, bot):
        calls["bots"].append(bot)
        return {"ok": True, "published": (), "error": None}

    monkeypatch.setattr(lie.rivalry_presentation, "publish_competition_surfaces", fake_combined)
    monkeypatch.setattr(lie.rivalry_presentation, "publish_bot_surfaces", fake_bot)
    return calls


def test_first_run_publishes_everything(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    result = lie.competition_surfaces_job(connections)
    assert calls["combined"] == 1
    assert calls["bots"] == list(scoreboard.BOTS)
    assert "unchanged" not in result


def test_second_run_with_no_state_change_skips_every_publish_call(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    lie.competition_surfaces_job(connections)
    calls["combined"] = 0
    calls["bots"] = []

    result = lie.competition_surfaces_job(connections)

    assert calls["combined"] == 0, "unchanged state must not repost the combined scoreboard/rivalry cards"
    assert calls["bots"] == [], "unchanged state must not repost any per-bot dashboard/chart/held-trade cards"
    assert "combined:unchanged" in result
    for bot in scoreboard.BOTS:
        assert f"{bot}:unchanged" in result


def test_a_real_trade_change_triggers_a_republish_for_that_bot_only(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    lie.competition_surfaces_job(connections)
    calls["combined"] = 0
    calls["bots"] = []

    score_connection = scoreboard.connect_db()
    scoreboard.record_trade_open(
        score_connection, trade_id="t1", bot="AXIOM", generation=1,
        opened_at="2026-08-26T09:30:00-05:00", side="CALL",
        contract_symbol="SPY-SECRET", entry_price=1.0, contracts=1,
        entry_bankroll=1000.0,
    )

    result = lie.competition_surfaces_job(connections)

    assert calls["bots"] == ["AXIOM"], "only the bot whose state actually changed should republish"
    assert "AXIOM:ok" in result
    assert "BLACKTIDE:unchanged" in result
