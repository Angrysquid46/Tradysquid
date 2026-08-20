"""The activity log must be readable, safe, and impossible to break.

Written after 2026-08-20 12:00:49, when twelve positions opened stamped
"/force-all-strategies", the owner had not run it, and a scan of all 123
Discord channels found zero interactions. The only record of the
invocation was the trades it produced. There was nothing to read.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

import activity_log


@pytest.fixture(autouse=True)
def isolated_log(monkeypatch):
    # tempfile, not pytest's tmp_path - its shared pytest-of-<user> base
    # raises PermissionError on this checkout (see conftest.py).
    path = Path(tempfile.mkdtemp(prefix="activity-")) / "activity.jsonl"
    monkeypatch.setattr(activity_log, "LOG_PATH", path)
    return path


def test_an_event_is_one_readable_json_line(isolated_log) -> None:
    activity_log.record("trade.open", trade_id="SPY-20260820-010",
                        play_type="SPY_TOD_FINAL30")
    lines = isolated_log.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["event"] == "trade.open"
    assert entry["trade_id"] == "SPY-20260820-010"
    assert entry["at"] and entry["pid"]


def test_secrets_are_recorded_as_presence_not_value(isolated_log) -> None:
    """The bot token is in this process's environment. It must never land
    in a file that exists to be read."""
    activity_log.record(
        "discord.interaction",
        has_signature=True,
        signature="abc123deadbeef",
        authorization="Bot super-secret",
        api_key="sk-live-9999",
        user="angrysquid46",
    )
    text = isolated_log.read_text(encoding="utf-8")
    assert "abc123deadbeef" not in text
    assert "super-secret" not in text
    assert "sk-live-9999" not in text
    assert "angrysquid46" in text          # non-secret fields survive


def test_logging_never_raises_even_when_the_path_is_unusable(monkeypatch) -> None:
    """A logger that can break its caller is worse than no logger."""
    monkeypatch.setattr(activity_log, "LOG_PATH",
                        Path("Z:/definitely/not/a/real/path/activity.jsonl"))
    activity_log.record("trade.open", trade_id="X")     # must not raise


def test_an_unserialisable_value_does_not_lose_the_event(isolated_log) -> None:
    class Weird:
        def __repr__(self) -> str:
            return "<weird>"

    activity_log.record("job.error", job="x", exc=Weird())
    entry = json.loads(isolated_log.read_text(encoding="utf-8").strip())
    assert entry["event"] == "job.error"


def test_read_returns_newest_last_and_can_filter(isolated_log) -> None:
    for n in range(5):
        activity_log.record("trade.open", trade_id=f"T{n}")
    activity_log.record("job.error", job="entry-scan")

    everything = activity_log.read()
    assert everything[-1]["event"] == "job.error"

    opens = activity_log.read(event="trade.open")
    assert [e["trade_id"] for e in opens] == ["T0", "T1", "T2", "T3", "T4"]


def test_read_survives_a_torn_line(isolated_log) -> None:
    """Append-only means a crash costs one line, not the file."""
    activity_log.record("trade.open", trade_id="T1")
    with isolated_log.open("a", encoding="utf-8") as handle:
        handle.write('{"event": "torn", "at"\n')
    activity_log.record("trade.open", trade_id="T2")

    ids = [e.get("trade_id") for e in activity_log.read(event="trade.open")]
    assert ids == ["T1", "T2"]


def test_it_rotates_instead_of_growing_without_bound(isolated_log, monkeypatch) -> None:
    monkeypatch.setattr(activity_log, "MAX_BYTES", 200)
    for n in range(40):
        activity_log.record("trade.open", trade_id=f"T{n}", padding="x" * 40)
    rotated = isolated_log.with_suffix(".jsonl.1")
    assert rotated.exists()
    assert isolated_log.stat().st_size < 4000


def test_the_entry_choke_point_is_wired(isolated_log) -> None:
    """candidate_to_row is the one function every entry path funnels
    through - the 1-minute scan, SPY_KEY_LEVELS, and every /force-*
    command. If it stops logging, a forced burst goes unrecorded again."""
    import inspect

    import spy_scanner

    source = inspect.getsource(spy_scanner.candidate_to_row)
    assert "activity_log.record" in source
    assert "trade.open" in source
    assert "market_condition" in source


def test_the_interaction_endpoint_logs_before_it_verifies() -> None:
    """A rejected or replayed request must still leave a line. Logging
    after verification would have recorded nothing for the 12:00:49 burst
    if that request had failed verification."""
    import inspect

    import discord_command_bot

    source = inspect.getsource(discord_command_bot.interactions)
    record_at = source.index("activity_log.record")
    verify_at = source.index("verify_discord_request()")
    assert record_at < verify_at
    assert "interaction_id" in source
    assert "signature_timestamp" in source

