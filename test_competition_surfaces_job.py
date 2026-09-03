from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import discord_surface_manifest as surfaces
import discord_transport
import local_information_engine as lie
import scoreboard


@pytest.fixture
def connections(monkeypatch):
    root = Path(tempfile.mkdtemp())
    monkeypatch.setattr(scoreboard, "DB_PATH", root / "score.db")
    monkeypatch.setattr(surfaces, "DB_PATH", root / "surfaces.db")
    monkeypatch.setattr(lie, "DB_PATH", root / "engine.db")
    monkeypatch.setattr(discord_transport, "DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(discord_transport, "DISCORD_GUILD_ID", "guild")
    return lie.connect_db()


def _stub_publishers(monkeypatch):
    calls = {"bots": []}

    def fake_bot(score_connection, surface_connection, tracker, bot):
        calls["bots"].append(bot)
        return {"ok": True, "published": (), "error": None}

    monkeypatch.setattr(lie.rivalry_presentation, "publish_bot_surfaces", fake_bot)
    return calls


def test_first_run_publishes_everything(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    result = lie.competition_surfaces_job(connections)
    assert calls["bots"] == list(lie.rivalry_presentation.PUBLIC_BOTS)
    assert "unchanged" not in result


def test_second_run_with_no_state_change_skips_every_publish_call(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    lie.competition_surfaces_job(connections)
    calls["bots"] = []

    result = lie.competition_surfaces_job(connections)

    assert calls["bots"] == [], "unchanged state must not repost any per-bot dashboard/chart/held-trade cards"
    for bot in lie.rivalry_presentation.PUBLIC_BOTS:
        assert f"{bot}:unchanged" in result


def test_a_real_trade_change_triggers_a_republish_for_that_bot_only(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    lie.competition_surfaces_job(connections)
    calls["bots"] = []

    score_connection = scoreboard.connect_db()
    scoreboard.record_trade_open(
        score_connection, trade_id="t1", bot="RIPTIDE", generation=1,
        opened_at="2026-08-26T09:30:00-05:00", side="CALL",
        contract_symbol="SPY-SECRET", entry_price=1.0, contracts=1,
        entry_bankroll=1000.0,
    )

    result = lie.competition_surfaces_job(connections)

    assert calls["bots"] == ["RIPTIDE"], "only the active public bot whose state changed should republish"
    assert "RIPTIDE:ok" in result
    assert "BLACKTIDE:unchanged" in result


def test_bot_presentation_format_change_refreshes_both_bot_surfaces(connections, monkeypatch):
    calls = _stub_publishers(monkeypatch)
    lie.competition_surfaces_job(connections)
    calls["combined"] = 0
    calls["bots"] = []

    monkeypatch.setattr(lie.rivalry_presentation, "BOT_SURFACE_FORMAT_VERSION", "test-v2")
    result = lie.competition_surfaces_job(connections)

    assert calls["bots"] == list(lie.rivalry_presentation.PUBLIC_BOTS)
    assert "RIPTIDE:ok" in result
    assert "BLACKTIDE:ok" in result


def test_live_held_job_batch_marks_open_contract_and_publishes_only_changed_bot(connections, monkeypatch):
    score_connection = scoreboard.connect_db()
    scoreboard.record_trade_open(
        score_connection, trade_id="live-1", bot="SURGE", generation=1,
        opened_at="2026-09-03T12:09:50-05:00", side="CALL",
        contract_symbol="SPY260903C00650000", entry_price=1.00,
        contracts=2, entry_bankroll=1000.0,
    )
    quote_calls = []
    monkeypatch.setattr(
        lie.market_data, "get_quotes",
        lambda symbols, include_greeks, priority: quote_calls.append(
            (symbols, include_greeks, priority)
        ) or {"SPY260903C00650000": {"bid": 1.12}},
    )
    published = []
    monkeypatch.setattr(
        lie.rivalry_presentation, "publish_bot_held_surface",
        lambda score, surface, tracker, bot: published.append(bot) or {
            "ok": True, "published": (f"{bot.lower()}-held-trade-card",), "error": None,
        },
    )

    result = lie.live_held_trades_job(connections)
    marked = scoreboard.current_position_status(score_connection, "SURGE")

    assert quote_calls == [(
        ["SPY260903C00650000"], False,
        lie.market_api_budget.PRIORITY_OPEN_POSITION_SAFETY,
    )]
    assert marked["last_mark_price"] == pytest.approx(1.12)
    assert set(published) == set(lie.rivalry_presentation.PUBLIC_BOTS)
    assert "SURGE:ok" in result


def test_live_held_job_skips_unchanged_flat_cards_after_reconciliation(connections, monkeypatch):
    monkeypatch.setattr(lie.market_data, "get_quotes", lambda *args, **kwargs: {})
    published = []
    monkeypatch.setattr(
        lie.rivalry_presentation, "publish_bot_held_surface",
        lambda score, surface, tracker, bot: published.append(bot) or {
            "ok": True, "published": (), "error": None,
        },
    )
    lie.live_held_trades_job(connections)
    published.clear()

    result = lie.live_held_trades_job(connections)

    assert published == []
    assert all(f"{bot}:unchanged" in result for bot in lie.rivalry_presentation.PUBLIC_BOTS)


def test_live_held_job_is_registered_on_ten_second_fast_path():
    job = next(item for item in lie.JOBS if item.name == "live-held-trades")
    assert job.interval.total_seconds() == 10
    assert job.background is True
