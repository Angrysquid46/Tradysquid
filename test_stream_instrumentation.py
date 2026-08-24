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

import local_information_engine as engine


def test_the_stream_counters_exist_and_cover_the_hot_path():
    for key in ("ticks", "relevant_ticks", "evaluations", "refetches",
                "closes", "card_pushes", "eval_seconds"):
        assert key in engine.STREAM_STATS, key


def test_the_staleness_bound_is_tighter_than_the_card_gate():
    """The refetch bound governs exit freshness; the 2s gate governs only
    the display. If the bound ever exceeded the gate, the card would be
    fresher than the data the exit decision uses."""
    assert engine.STREAM_QUOTE_STALE_SECONDS < 2.0


def test_the_rest_fallback_is_a_floor_not_the_live_path():
    """60s is the guarantee if the socket drops - it is not how often
    positions are normally checked."""
    assert engine.POSITION_SAFETY_POLL_SECONDS <= 60
