"""system_digest_job is the once-daily, single-upserted-card answer to
"communicate every issue hidden in the back end without spamming me, and
let me ask what happened" - it rolls up stop/floor overshoots (reusing
spy_scanner.compute_stop_overshoot so it can't drift from what the close
card itself shows), diagnostic_upgrade_system's existing infra-health
checks, and the CHANGELOG.jsonl patch log into one card in #system-health,
refreshed in place rather than posted anew each run.
"""

from __future__ import annotations
import json
import tempfile
from pathlib import Path
from unittest import mock

import local_information_engine as engine
import spy_scanner


def _row(**overrides) -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update(
        {
            "trade_id": "SPY-DIGEST-001",
            "ticker": "SPY",
            "play_type": "SPY_0DTE_1M",
            "outcome": "LOSS",
        }
    )
    row.update(overrides)
    return row


def test_overshoot_rollup_ignores_trades_closed_before_the_window():
    now = spy_scanner.now_ct()
    since = now
    row = _row(
        closed_at=(now - __import__("datetime").timedelta(hours=48)).isoformat(),
        last_signal="STOP OUT",
        pct_gain_loss="-40",
    )
    stop_closes, overshoots, worst = engine._overshoot_rollup([row], since)
    assert stop_closes == 0
    assert overshoots == 0
    assert worst == []


def test_overshoot_rollup_counts_a_real_overshoot_within_the_window():
    now = spy_scanner.now_ct()
    since = now - __import__("datetime").timedelta(hours=24)
    target = -(spy_scanner.SPY_STOP_PCT * 100)
    row = _row(
        closed_at=now.isoformat(),
        last_signal="STOP OUT",
        pct_gain_loss=str(target - 10),
    )
    stop_closes, overshoots, worst = engine._overshoot_rollup([row], since)
    assert stop_closes == 1
    assert overshoots == 1
    assert "SPY-DIGEST-001" in worst[0]


def test_overshoot_rollup_counts_the_close_but_not_the_overshoot_when_the_stop_held():
    now = spy_scanner.now_ct()
    since = now - __import__("datetime").timedelta(hours=24)
    target = -(spy_scanner.SPY_STOP_PCT * 100)
    row = _row(closed_at=now.isoformat(), last_signal="STOP OUT", pct_gain_loss=str(target))
    stop_closes, overshoots, worst = engine._overshoot_rollup([row], since)
    assert stop_closes == 1
    assert overshoots == 0
    assert worst == []


def test_recent_changelog_entries_filters_by_window_and_event_type():
    now = spy_scanner.now_ct()
    with tempfile.TemporaryDirectory() as temp:
        events_path = Path(temp) / "CHANGELOG.jsonl"
        old = now - __import__("datetime").timedelta(hours=48)
        recent = now - __import__("datetime").timedelta(hours=1)
        lines = [
            json.dumps({"event": "COMPLETE", "task": "too old", "completed_at": old.isoformat()}),
            json.dumps({"event": "BEGIN", "task": "in progress, not complete", "started_at": recent.isoformat()}),
            json.dumps({"event": "COMPLETE", "task": "recent fix", "completed_at": recent.isoformat()}),
        ]
        events_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        with mock.patch.object(engine.ai_coordination, "EVENTS_PATH", events_path):
            entries = engine._recent_changelog_entries(now - __import__("datetime").timedelta(hours=24))
    assert len(entries) == 1
    assert entries[0]["task"] == "recent fix"


def test_recent_changelog_entries_fails_open_when_the_file_is_missing():
    now = spy_scanner.now_ct()
    with mock.patch.object(engine.ai_coordination, "EVENTS_PATH", Path("/does/not/exist.jsonl")):
        entries = engine._recent_changelog_entries(now)
    assert entries == []


def test_system_digest_job_posts_one_upserted_card_with_all_three_sections():
    original_log = spy_scanner.LOG_PATH
    original_db = engine.DB_PATH
    calls: list[tuple] = []

    class FakeTracker:
        ready = True

        def upsert_channel_message(self, logical_name, state, state_key, content, search_token=""):
            calls.append((logical_name, state_key, content, search_token))
            return "msg-1"

    with tempfile.TemporaryDirectory() as temp:
        spy_scanner.LOG_PATH = Path(temp) / "plays.csv"
        engine.DB_PATH = Path(temp) / "status.db"
        now = spy_scanner.now_ct()
        target = -(spy_scanner.SPY_STOP_PCT * 100)
        row = _row(closed_at=now.isoformat(), last_signal="STOP OUT", pct_gain_loss=str(target - 5))
        spy_scanner.write_log([row])
        connection = engine.connect_db()
        try:
            with (
                mock.patch.object(engine, "discord_tracker", return_value=FakeTracker()),
                mock.patch.object(spy_scanner, "read_report_state", return_value={}),
                mock.patch.object(spy_scanner, "write_report_state"),
                mock.patch.object(
                    engine.diagnostics,
                    "diagnostics_summary",
                    return_value={"counts": {}, "open": [], "last_cycle": ""},
                ),
                mock.patch.object(engine, "_recent_changelog_entries", return_value=[]),
            ):
                result = engine.system_digest_job(connection)
        finally:
            connection.close()
    spy_scanner.LOG_PATH = original_log
    engine.DB_PATH = original_db

    assert len(calls) == 1
    logical_name, state_key, content, search_token = calls[0]
    assert logical_name == "status"
    assert state_key == "system-digest"
    assert search_token == "Daily System Digest"
    assert "Trading Anomalies" in content
    assert "By Market Condition" in content
    assert "Infra Health" in content
    assert "Patch Log" in content
    assert "1 of 1 stop/floor closes" in content
    assert "1 stop closes" in result


def test_system_digest_job_returns_early_when_discord_is_unavailable():
    with mock.patch.object(engine, "discord_tracker", return_value=None):
        result = engine.system_digest_job(mock.Mock())
    assert result == "Discord tracker unavailable"
