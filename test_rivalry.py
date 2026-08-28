from __future__ import annotations

import inspect
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

import rivalry


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(rivalry, "DB_PATH", Path(tempfile.mkdtemp()) / "rivalry.db")
    connection = rivalry.connect_db()
    yield connection
    connection.close()


BASE = datetime(2026, 8, 24, 12, 0, 0)


def _record(db, event_id, *, speaker="BLACKTIDE", event_group_id="g1", trigger="TRADE_CLOSED_WIN", now):
    return rivalry.record_rivalry_event(
        db, rivalry_event_id=event_id, event_group_id=event_group_id, trigger=trigger,
        speaker=speaker, message="gg", public_score_snapshot={"bot": speaker},
        conversation_round=0, now=now,
    )


# --- basic validation -----------------------------------------------------------

def test_record_rivalry_event_succeeds_and_round_trips(db):
    _record(db, "e1", now=BASE)
    history = rivalry.public_rivalry_history(db)
    assert len(history) == 1
    assert history[0]["rivalry_event_id"] == "e1"
    assert history[0]["public_score_snapshot"] == {"bot": "BLACKTIDE"}


def test_record_rivalry_event_rejects_unknown_trigger(db):
    with pytest.raises(ValueError, match="Unknown trigger"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="e1", event_group_id="g1", trigger="MADE_UP",
            speaker="BLACKTIDE", message="x", public_score_snapshot={}, now=BASE,
        )


def test_record_rivalry_event_rejects_unknown_speaker(db):
    with pytest.raises(ValueError, match="Unknown speaker"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="e1", event_group_id="g1", trigger="SESSION_OPEN",
            speaker="Nobody", message="x", public_score_snapshot={}, now=BASE,
        )


def test_record_rivalry_event_rejects_a_removed_competitor_as_speaker(db):
    """AXIOM permanently removed 2026-08-27 (owner directive) - it must be
    rejected exactly like any other unregistered name now, not treated
    specially."""
    with pytest.raises(ValueError, match="Unknown speaker"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="e1", event_group_id="g1", trigger="SESSION_OPEN",
            speaker="AXIOM", message="x", public_score_snapshot={}, now=BASE,
        )


def test_record_rivalry_event_rejects_duplicate_id(db):
    _record(db, "e1", now=BASE)
    with pytest.raises(ValueError, match="already recorded"):
        _record(db, "e1", now=BASE + timedelta(seconds=30))


# --- the bounded-chain limits, each isolated -------------------------------

def test_per_event_limit_blocks_the_fourth_message_in_one_event(db):
    for i in range(3):
        _record(db, f"e{i}", event_group_id="g1", now=BASE + timedelta(seconds=i * 30))
    with pytest.raises(rivalry.RivalryLimitExceeded, match="max 3"):
        _record(db, "e3", event_group_id="g1", now=BASE + timedelta(seconds=90))


def test_per_event_limit_does_not_block_a_different_event_group(db):
    for i in range(3):
        _record(db, f"e{i}", event_group_id="g1", now=BASE + timedelta(seconds=i * 30))
    _record(db, "e-other", event_group_id="g2", now=BASE + timedelta(seconds=90))  # does not raise


def test_per_day_limit_blocks_the_twenty_first_message(db):
    for i in range(20):
        _record(
            db, f"e{i}", event_group_id=f"g{i}",
            now=BASE + timedelta(minutes=2 * i),
        )
    with pytest.raises(rivalry.RivalryLimitExceeded, match="max 20"):
        _record(db, "e20", event_group_id="g20", now=BASE + timedelta(minutes=42))


# Owner directive 2026-08-27: AXIOM permanently removed. rivalry.py's own
# BOTS is currently ("BLACKTIDE",) - RIPTIDE (Codex's new second
# competitor, launched the same day) has not been wired into rivalry.py's
# roster yet, that is Codex's own follow-up. RIVALRY_MAX_TOTAL_MESSAGES_
# PER_MINUTE (6) counts ALL speakers combined, distinct from the
# per-speaker RIVALRY_MIN_MESSAGE_GAP_SECONDS (20) - the old test proved
# that distinction by alternating two real speakers. With only one
# registered bot, min-gap alone forces >=100s to send 6 legal messages
# (0,20,40,60,80,100s), so no 60-second rolling window can ever contain 6
# - the total-per-minute limit is currently structurally unreachable
# through legal single-speaker traffic. The limit's own code stays intact
# and correct for whenever a second bot is registered here; this is a
# documented, honest coverage gap, not a deleted guarantee.


def test_min_gap_limit_blocks_the_same_bot_speaking_too_soon(db):
    _record(db, "e1", speaker="BLACKTIDE", event_group_id="g1", now=BASE)
    with pytest.raises(rivalry.RivalryLimitExceeded, match="min gap"):
        _record(db, "e2", speaker="BLACKTIDE", event_group_id="g2", now=BASE + timedelta(seconds=5))


# test_min_gap_limit_does_not_apply_across_different_speakers removed
# 2026-08-27 (AXIOM permanently removed) - proving independence across
# speakers needs a second real registered bot in rivalry.py's own BOTS,
# which does not currently exist.


def test_min_gap_limit_clears_after_enough_time(db):
    _record(db, "e1", speaker="BLACKTIDE", event_group_id="g1", now=BASE)
    _record(
        db, "e2", speaker="BLACKTIDE", event_group_id="g2",
        now=BASE + timedelta(seconds=rivalry.RIVALRY_MIN_MESSAGE_GAP_SECONDS),
    )  # exactly at the boundary - does not raise


# --- SESSION_OPEN/SESSION_CLOSE: once per speaker per day -----------------------

def test_session_open_blocks_a_second_one_the_same_day(db):
    _record(db, "e1", trigger="SESSION_OPEN", event_group_id="g1", now=BASE)
    with pytest.raises(rivalry.RivalryLimitExceeded, match="once per day"):
        _record(
            db, "e2", trigger="SESSION_OPEN", event_group_id="g2",
            now=BASE + timedelta(minutes=5),
        )


def test_session_close_blocks_a_second_one_the_same_day(db):
    _record(db, "e1", trigger="SESSION_CLOSE", event_group_id="g1", now=BASE)
    with pytest.raises(rivalry.RivalryLimitExceeded, match="once per day"):
        _record(
            db, "e2", trigger="SESSION_CLOSE", event_group_id="g2",
            now=BASE + timedelta(minutes=5),
        )


def test_session_open_and_session_close_both_allowed_same_day(db):
    _record(db, "e1", trigger="SESSION_OPEN", event_group_id="g1", now=BASE)
    _record(
        db, "e2", trigger="SESSION_CLOSE", event_group_id="g2",
        now=BASE + timedelta(minutes=5),
    )  # different triggers - does not raise


def test_session_open_allowed_again_the_next_day(db):
    _record(db, "e1", trigger="SESSION_OPEN", event_group_id="g1", now=BASE)
    _record(
        db, "e2", trigger="SESSION_OPEN", event_group_id="g2",
        now=BASE + timedelta(days=1),
    )  # does not raise


# --- public_score_snapshot schema ------------------------------------------------

def test_record_rivalry_event_rejects_an_unrecognized_snapshot_key(db):
    with pytest.raises(ValueError, match="unrecognized key"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="e1", event_group_id="g1", trigger="TRADE_CLOSED_WIN",
            speaker="BLACKTIDE", message="x",
            public_score_snapshot={"bot": "BLACKTIDE", "private_hypothesis_name": "trend_continuation"},
            now=BASE,
        )


def test_allowed_public_snapshot_keys_matches_scoreboard_real_shape():
    """rivalry.py can't import scoreboard.py (architectural isolation,
    enforced below), so its allowlist is a duplicated literal - this test
    is what catches drift between the two instead."""
    import scoreboard
    assert rivalry.ALLOWED_PUBLIC_SNAPSHOT_KEYS == scoreboard.SCOREBOARD_SNAPSHOT_KEYS


# --- public_rivalry_history -----------------------------------------------------

def test_public_rivalry_history_orders_newest_first(db):
    _record(db, "e1", speaker="BLACKTIDE", event_group_id="g1", now=BASE)
    _record(db, "e2", speaker="BLACKTIDE", event_group_id="g2", now=BASE + timedelta(seconds=30))
    history = rivalry.public_rivalry_history(db)
    assert [item["rivalry_event_id"] for item in history] == ["e2", "e1"]


def test_public_rivalry_history_filters_by_bot_as_speaker(db):
    """Narrowed from the old speaker-or-target version 2026-08-27 (AXIOM
    permanently removed) - filtering by target as a DIFFERENT bot from the
    speaker needs a second real bot registered in rivalry.py's own BOTS,
    which does not currently exist. The speaker-filter half of this
    behavior is still fully real and tested here."""
    _record(db, "e1", speaker="BLACKTIDE", event_group_id="g1", now=BASE)
    history = rivalry.public_rivalry_history(db, bot="BLACKTIDE")
    assert len(history) == 1
    assert history[0]["rivalry_event_id"] == "e1"


# --- architectural separation from trading/competition writes -------------------

def test_module_has_no_reference_to_scoreboard_write_functions():
    source = inspect.getsource(rivalry)
    for forbidden in ("record_trade_open", "record_trade_close", "import scoreboard"):
        assert forbidden not in source, f"rivalry.py must never reference {forbidden!r}"


def test_never_open_position_chat_flag_is_false():
    assert rivalry.RIVALRY_OPEN_POSITION_CHAT is False
    assert rivalry.RIVALRY_CAN_INFLUENCE_TRADING is False
    assert rivalry.RIVALRY_PRIVATE_STRATEGY_ACCESS is False


def test_rejects_detailed_live_position_snapshot(db):
    with pytest.raises(ValueError, match="OPEN or FLAT"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="leak", event_group_id="g", trigger="SESSION_OPEN",
            speaker="BLACKTIDE", message="no", now=BASE,
            public_score_snapshot={"current_position_status": {"symbol": "SECRET"}},
        )


def test_reply_chain_is_finite_and_sequential(db):
    _record(db, "root", now=BASE)
    rivalry.record_rivalry_event(
        db, rivalry_event_id="reply", event_group_id="g1", trigger="TRADE_CLOSED_WIN",
        speaker="BLACKTIDE", message="reply", public_score_snapshot={},
        reply_to_id="root", conversation_round=1, now=BASE + timedelta(seconds=20),
    )
    with pytest.raises(rivalry.RivalryLimitExceeded, match="finite reply-chain"):
        rivalry.record_rivalry_event(
            db, rivalry_event_id="too-deep", event_group_id="g1", trigger="TRADE_CLOSED_WIN",
            speaker="BLACKTIDE", message="deep", public_score_snapshot={},
            reply_to_id="reply", conversation_round=rivalry.RIVALRY_MAX_CONVERSATION_ROUNDS,
            now=BASE + timedelta(seconds=40),
        )
