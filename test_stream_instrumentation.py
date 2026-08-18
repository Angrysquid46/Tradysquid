"""The live exit path must be measurable, and must never be debounced.

Two things were unclear and had to be read from source rather than data:
whether a triggered exit waits on the 2-second card gate, and what the
0.5s staleness bound actually costs in REST calls. The first is answered
by a test; the second needs a session of real counters.

Exit latency matters here specifically: at a 2.0s staleness bound a
$0.16 0DTE put peaked +31% and closed -25% against a -15% target,
because the whole swing happened inside one window.
"""

from __future__ import annotations

import inspect

import local_information_engine as engine


def test_a_triggered_exit_is_not_debounced():
    """The 2-second gate applies to the DISPLAY branch only.

    If a close ever moved inside that gate, a stop could sit un-actioned
    for up to two seconds - on a 0DTE that is real money, and it would
    look identical to Discord simply lagging.
    """
    src = inspect.getsource(engine._stream_quote_event)
    close_at = src.index("CLOSING_SIGNALS")
    debounce_at = src.index("last_write >= 2")
    assert close_at < debounce_at, (
        "the close path must be reached before the debounce gate"
    )
    # the debounce lives in the else-branch, after the close branch
    between = src[close_at:debounce_at]
    assert "else:" in between, "debounce is no longer confined to the else branch"


def test_the_stream_counters_exist_and_cover_the_hot_path():
    for key in ("ticks", "relevant_ticks", "evaluations", "refetches",
                "closes", "card_pushes", "eval_seconds"):
        assert key in engine.STREAM_STATS, key


def test_counters_are_incremented_on_the_live_path():
    src = inspect.getsource(engine._stream_quote_event)
    for key in ("ticks", "relevant_ticks", "evaluations", "refetches",
                "closes", "card_pushes"):
        assert f'STREAM_STATS["{key}"]' in src, f"{key} is never incremented"


def test_the_counters_are_flushed_to_history():
    """Counters that only live in memory die with the process and can
    never be read after the session they describe."""
    src = inspect.getsource(engine)
    assert '"stream-stats"' in src


def test_the_staleness_bound_is_tighter_than_the_card_gate():
    """The refetch bound governs exit freshness; the 2s gate governs only
    the display. If the bound ever exceeded the gate, the card would be
    fresher than the data the exit decision uses."""
    assert engine.STREAM_QUOTE_STALE_SECONDS < 2.0


def test_the_rest_fallback_is_a_floor_not_the_live_path():
    """60s is the guarantee if the socket drops - it is not how often
    positions are normally checked."""
    assert engine.POSITION_SAFETY_POLL_SECONDS <= 60
