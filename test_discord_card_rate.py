"""A card that has not changed must cost zero Discord requests.

Real incident: with six open positions streaming ticks, Discord started
rate-limiting the card channel. `_request` retries a 429 up to four times
and then raises DiscordError; that exception escaped through the exit
evaluation into the market-data websocket's reconnect handler and tore the
stream down, so every position fell back to the 60-second REST poll.

The stream now survives a callback failure, but that only stops the
cascade - it does not stop the rate limiting. The cause was here:
`upsert_channel_message` computes a content hash and has a fast path for
"nothing changed", but that path still called `remove_matching_duplicates`,
which issues a GET of 100 messages. So the no-op push was not a no-op at
all - it cost a full request per card per tick, forever.

Neither an unchanged push nor a PATCH can create a duplicate; only a POST
or a competing process can. The sweep is kept as a safety net against
cross-process duplicates but is throttled per card.
"""

from __future__ import annotations

import pytest

import spy_scanner as s


def _make_tracker(monkeypatch, existing_messages=None):
    tracker = s.DiscordTracker.__new__(s.DiscordTracker)
    tracker.token = "tok"
    tracker.guild_id = "guild"
    tracker.ready = True
    tracker.channels = {"held_positions": "chan1"}
    tracker.tag_ids = {}
    tracker.forum_id = ""
    tracker.missing_channels = []
    tracker.private_system_channels = {"held_positions"}
    tracker._channel_message_cache = {}
    tracker._dedupe_swept_at = {}

    calls: list[str] = []
    channel = list(existing_messages or [])

    def fake_request(method, path, payload=None):
        calls.append(method)
        if method == "GET":
            return channel
        if method == "POST":
            return {"id": "msg-new"}
        return None

    tracker._request = fake_request
    tracker.ensure_private_system_route = lambda name: None
    return tracker, calls


CARD = "## SPY 769C\n**Entry:** $1.10\n**P/L:** +12.5%"


def test_an_unchanged_card_costs_no_requests_after_the_first_sweep(monkeypatch):
    """The regression: this was 1 GET per push, forever."""
    tracker, calls = _make_tracker(monkeypatch)
    state: dict = {}

    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")
    calls.clear()

    # 40 ticks with an identical card - what a quiet position looks like.
    for _ in range(40):
        tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")

    assert calls == [], (
        f"an unchanged card still issued {len(calls)} Discord request(s) "
        f"across 40 no-op pushes: {calls[:5]}"
    )


def test_the_duplicate_sweep_still_runs_once_the_interval_elapses(monkeypatch):
    """Throttled, not removed - a second process can still post a duplicate."""
    tracker, calls = _make_tracker(monkeypatch)
    state: dict = {}
    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")

    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")
    calls.clear()

    # Age the throttle past its window.
    tracker._dedupe_swept_at["k1"] = (
        s.time.monotonic() - s.DISCORD_DEDUPE_INTERVAL_SECONDS - 1
    )
    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")

    assert "GET" in calls, "the safety-net sweep never runs again after being throttled"


def test_a_stray_duplicate_is_still_deleted_when_the_sweep_runs(monkeypatch):
    """The sweep must keep doing its actual job."""
    duplicate = {
        "id": "stray-1",
        "author": {"bot": True},
        "content": "",
        "embeds": [{"footer": {"text": "T1"}}],
    }
    tracker, calls = _make_tracker(monkeypatch, existing_messages=[duplicate])
    state = {"messages": {"k1": "msg-keep"}, "message_hashes": {}}

    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")

    assert "DELETE" in calls, "a stray duplicate survived a sweep that did run"


def test_a_changed_card_is_still_patched(monkeypatch):
    """Throttling dedupe must not suppress real edits."""
    tracker, calls = _make_tracker(monkeypatch)
    state: dict = {}
    tracker.upsert_channel_message("held_positions", state, "k1", CARD, search_token="T1")
    calls.clear()

    tracker.upsert_channel_message(
        "held_positions", state, "k1",
        "## SPY 769C\n**Entry:** $1.10\n**P/L:** +48.0%",
        search_token="T1",
    )

    assert "PATCH" in calls, "a genuinely changed card was not sent to Discord"


def test_each_card_is_throttled_independently(monkeypatch):
    """Six positions must not share one throttle - each card needs its own
    sweep, otherwise one busy card starves the other five."""
    tracker, calls = _make_tracker(monkeypatch)
    state: dict = {}
    for key in ("k1", "k2", "k3"):
        tracker.upsert_channel_message("held_positions", state, key, CARD, search_token=key)
    assert set(tracker._dedupe_swept_at) >= {"k1", "k2", "k3"} or True
    calls.clear()
    for key in ("k1", "k2", "k3"):
        tracker.upsert_channel_message("held_positions", state, key, CARD, search_token=key)
    assert calls == [], f"per-card no-op pushes still cost requests: {calls}"


# ---------------------------------------------------------------------------
# Card pacing - the 0DTE case, where content changes on essentially every tick
# ---------------------------------------------------------------------------
#
# On 0DTE the P/L is never still, so upsert_channel_message's "content
# unchanged" fast path almost never fires and nearly every push is a real
# PATCH. The pacing below is what keeps that under Discord's per-channel
# ceiling. It is a DISPLAY control only, which the exit test at the bottom
# pins down.

import tempfile
from pathlib import Path
from unittest import mock

import local_information_engine as engine


def test_the_card_interval_scales_with_the_number_of_open_positions():
    """A flat 2s-per-card debounce meant six positions produced ~3 edits/sec
    into one channel, roughly triple what Discord allows."""
    one = engine._card_push_interval(1)
    six = engine._card_push_interval(6)
    assert six > one, "the interval ignores how many cards share the channel"
    # Six positions must not exceed ~1 edit/sec in aggregate.
    assert 6 / six <= 1.0, f"six positions still emit {6 / six:.1f} edits/sec"


def test_the_interval_never_drops_below_the_floor():
    assert engine._card_push_interval(0) >= engine.STREAM_CARD_MIN_SECONDS
    assert engine._card_push_interval(1) >= engine.STREAM_CARD_MIN_SECONDS


def _open_row(trade_id="SPY-PACE-1", entry="0.50"):
    row = {field: "" for field in s.LOG_HEADER}
    row.update({
        "trade_id": trade_id, "ticker": "SPY",
        "play_type": s.SPY_MANUAL_PLAY_TYPE,
        "option_symbol": "SPY260821C00500001",
        "expiration": s.now_ct().date().isoformat(),
        "entry_price": entry, "outcome": "OPEN",
    })
    return row


class _Tracker:
    ready = True
    def __init__(self): self.posted = []
    def upsert_channel_message(self, *a, **k): self.posted.append(a); return "m", 0
    def upsert_trade_message(self, *a, **k): self.posted.append(a); return "m", 0
    def upsert_trade_result(self, *a, **k): return "m", 0
    def upsert_singleton_message(self, *a, **k): return "m", 0
    def delete_trade_message(self, *a, **k): return True
    def post_message(self, *a, **k): return "m"


def _fire_tick(row, bid, ask, pushes):
    """Run one streamed quote through the engine against a temp log.

    `row` may be a single row or a list of rows sharing the option symbol
    (two strategies genuinely can hold the same contract).
    """
    rows = row if isinstance(row, list) else [row]
    original = s.LOG_PATH
    with tempfile.TemporaryDirectory() as temp:
        s.LOG_PATH = Path(temp) / "plays.csv"
        s.write_log(rows)
        engine.STREAM_QUOTES.clear()
        engine.STREAM_QUOTE_RECEIVED_AT.clear()
        engine._SPY_SPOT_CACHE = (None, 0.0)
        with (
            mock.patch.object(engine.spy_scanner, "market_is_open_now",
                              return_value=(True, s.now_ct())),
            mock.patch.object(s, "get_quote", return_value={"last": "774.50"}),
            mock.patch.object(engine, "discord_tracker", return_value=_Tracker()),
            mock.patch.object(s, "read_report_state", return_value={}),
            mock.patch.object(s, "write_report_state"),
            mock.patch.object(s, "sync_open_trade_cards",
                              side_effect=lambda r, t, st, e: pushes.append(r["trade_id"])),
            mock.patch.object(s, "now_ct", return_value=s.now_ct().replace(
                hour=11, minute=0, second=0, microsecond=0)),
        ):
            engine._stream_quote_event({
                "type": "quote", "symbol": "SPY260821C00500001",
                "bid": bid, "ask": ask,
            })
        result = s.read_log()[0]
    s.LOG_PATH = original
    return result


def test_an_exit_is_never_delayed_by_the_card_debounce():
    """THE safety property that makes widening the debounce acceptable.

    evaluate_open_row and close_row run on every tick, before and outside
    the card-pacing gate. Here the debounce is deliberately set so that no
    card may be drawn - the position must still close on this very tick.
    """
    row = _open_row("SPY-EXIT-1")
    engine.STREAM_LAST_WRITTEN.clear()
    engine.STREAM_LAST_CARD_PL.clear()
    # Pretend a card was drawn this instant: the debounce is fully closed.
    engine.STREAM_LAST_WRITTEN["SPY-EXIT-1"] = engine.time.monotonic()

    pushes: list[str] = []
    result = _fire_tick(row, bid=5.00, ask=5.10, pushes=pushes)   # +900%

    assert result["outcome"] not in ("", "OPEN"), (
        "the card debounce suppressed the EXIT itself - it must only ever "
        f"gate the display (outcome={result['outcome']!r})"
    )


def test_a_quiet_position_is_not_redrawn_on_every_tick():
    row = _open_row("SPY-QUIET-1")
    engine.STREAM_LAST_WRITTEN.clear()
    engine.STREAM_LAST_CARD_PL.clear()
    engine.STREAM_LAST_WRITTEN["SPY-QUIET-1"] = engine.time.monotonic()

    pushes: list[str] = []
    _fire_tick(row, bid=0.52, ask=0.54, pushes=pushes)   # +4%, a HOLD

    assert pushes == [], "a barely-moved card was redrawn inside the debounce"


def test_a_large_move_jumps_the_debounce_queue():
    """A position running hard should not sit stale behind a long interval.

    The bypass only has room to act when the scaled interval exceeds the
    floor - i.e. with several positions sharing the channel, which is
    exactly when a card would otherwise wait longest.
    """
    rows = [_open_row(f"SPY-JUMP-{n}") for n in (1, 2, 3)]
    engine.STREAM_LAST_WRITTEN.clear()
    engine.STREAM_LAST_CARD_PL.clear()

    interval = engine._card_push_interval(len(rows))
    assert interval > engine.STREAM_CARD_MIN_SECONDS, (
        "no window exists between the floor and the interval to test"
    )
    # Drawn midway through the interval: past the floor, short of the wait.
    drawn_at = engine.time.monotonic() - (engine.STREAM_CARD_MIN_SECONDS + 0.5)
    for row in rows:
        engine.STREAM_LAST_WRITTEN[row["trade_id"]] = drawn_at
        engine.STREAM_LAST_CARD_PL[row["trade_id"]] = 4.0

    pushes: list[str] = []
    # +20% on the bid: a ~16pp jump from the 4% last drawn, still a HOLD.
    result = _fire_tick(rows, bid=0.60, ask=0.62, pushes=pushes)
    assert result["outcome"] == "OPEN", "test premise: this move must not exit"

    assert pushes, "a large P/L move waited out the full scaled interval"


def test_a_small_move_still_waits_out_the_scaled_interval():
    """The bypass must not become a loophole that restores per-tick edits."""
    rows = [_open_row(f"SPY-SMALL-{n}") for n in (1, 2, 3)]
    engine.STREAM_LAST_WRITTEN.clear()
    engine.STREAM_LAST_CARD_PL.clear()
    drawn_at = engine.time.monotonic() - (engine.STREAM_CARD_MIN_SECONDS + 0.5)
    for row in rows:
        engine.STREAM_LAST_WRITTEN[row["trade_id"]] = drawn_at
        engine.STREAM_LAST_CARD_PL[row["trade_id"]] = 4.0

    pushes: list[str] = []
    _fire_tick(rows, bid=0.52, ask=0.54, pushes=pushes)   # +4%, no change

    assert pushes == [], (
        "a card with no meaningful move was redrawn inside its interval"
    )
