"""Sit out sessions too quiet for a 0DTE to reach its target.

These entries test PATTERN, not MAGNITUDE: a break above the 20-bar high
is still a break when the day's whole range is $3.40. The signal fires
exactly as designed and then there is no room to reach +115%. Owner: "in
sideways days when the boys get signals and go marching into losses is
just wild."

Measured over 17,998 backtested option trades, bucketed by trailing ATR-3
known at the open:

    <0.7%     3,318 trades   -$0.05/trade   <- loses
    0.7-1.0%  3,745 trades   +$2.10
    1.0-1.4%  3,972 trades   +$3.11
    1.4-2.0%  3,308 trades   +$5.40
    >2.0%     3,655 trades   +$8.87

Skipping <0.7%: 18% fewer trades, +23% per trade, total P/L still rises.
"""

from __future__ import annotations

import spy_live_new_strategies as lns
import spy_scanner


def test_the_gate_uses_only_prior_sessions():
    """The day's own range would be lookahead - the filter has to be
    decidable at the open, before any entry."""
    import inspect

    src = inspect.getsource(lns.session_atr_pct)
    assert "session_date < ?" in src, "must exclude the session being traded"


def test_a_quiet_stretch_is_blocked():
    """2026-08-11/13/17 were the days that prompted this."""
    for quiet in ("2026-08-11", "2026-08-13", "2026-08-17"):
        assert lns.atr_regime_blocked(quiet), f"{quiet} should be skipped"


def test_an_active_stretch_is_not_blocked():
    """The filter must not simply stop trading - late July ran $11-13
    ranges and is exactly when this system makes its money."""
    for busy in ("2026-08-03", "2026-08-05"):
        assert not lns.atr_regime_blocked(busy), f"{busy} should trade"


def test_a_short_lookback_is_used_because_atr14_lags():
    """ATR-14 read 1.04-1.17% through the entire quiet stretch - still
    carrying late July's ranges - and would have waved every one of those
    days through. The short window is the whole point."""
    lookback, floor = lns._atr_gate_settings()
    assert lookback <= 5, "a long lookback cannot react to a fresh compression"
    assert floor > 0

    quiet = "2026-08-17"
    assert lns.session_atr_pct(quiet, 3) < floor
    assert lns.session_atr_pct(quiet, 14) > floor, (
        "ATR-14 does not detect this session - that is why ATR-3 is used"
    )


def test_the_gate_fails_open_when_data_is_missing(monkeypatch):
    """A missing or unreadable daily_bars table must degrade to today's
    behaviour, never silently halt every strategy."""
    monkeypatch.setattr(lns, "session_atr_pct", lambda *a, **k: None)
    assert lns.atr_regime_blocked("2026-08-17") == ""


def test_the_gate_can_be_disabled_by_config(monkeypatch):
    monkeypatch.setattr(lns, "_atr_gate_settings", lambda: (3, 0.0))
    assert lns.atr_regime_blocked("2026-08-17") == ""


def test_the_value_is_cached_per_session(monkeypatch):
    """The 1-minute scan must not re-read the database every cycle."""
    lns._ATR_GATE_CACHE.clear()
    calls = {"n": 0}
    real = lns.sif.connect

    def counting_connect():
        calls["n"] += 1
        return real()

    monkeypatch.setattr(lns.sif, "connect", counting_connect)
    for _ in range(5):
        lns.session_atr_pct("2026-08-17", 3)
    assert calls["n"] == 1, f"hit the database {calls['n']} times instead of once"


def test_the_gate_runs_before_any_provider_call():
    """A skipped session must cost zero API budget."""
    import inspect

    src = inspect.getsource(spy_scanner.scan_new_strategy_entries)
    assert src.index("atr_regime_blocked") < src.index("get_quote(TICKER)")


def test_the_gate_blocks_entries_only_not_exits():
    """Held positions must keep being managed and flattened at EOD - a
    quiet day is a reason not to OPEN, never a reason to stop closing."""
    import inspect

    src = inspect.getsource(spy_scanner.scan_new_strategy_entries)
    assert "regime_blocked" in src
    # the exit evaluator is a different function entirely
    exit_src = inspect.getsource(spy_scanner.evaluate_open_new_strategy_row)
    assert "atr_regime_blocked" not in exit_src
