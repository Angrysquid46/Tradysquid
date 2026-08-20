"""The option backtest engine has to actually run.

Written 2026-08-20 after finding `simulate_option_trades` raised
AttributeError on every call: #281 removed `OptionExit.step_pct` while
erasing the ratchet strategies but left both readers in place
(`_exit_signal` opens with `if rules.step_pct`, and `ratchet_rules()`
still passes it). The entire option layer was dead for weeks and nothing
reported it, because no test called it.

These are deliberately about the ENGINE, not about any strategy's numbers:
that a trade is produced at all, that each exit shape reaches its own
branch, and that a pure clock exit closes on time.
"""

from __future__ import annotations

import spy_option_backtest as ob


def _rows(closes: list[float], session: str = "2026-01-02") -> list[dict]:
    """One session of bars, one per minute from the open."""
    return [
        {
            "session_date": session,
            "open": price,
            "close": price,
            "high": price,
            "low": price,
            "minutes_since_open": minute,
        }
        for minute, price in enumerate(closes)
    ]


def _flat_session(minutes: int = 120, price: float = 500.0) -> list[dict]:
    return _rows([price] * minutes)


def test_the_engine_produces_a_trade_at_all() -> None:
    # Fails with AttributeError before the step_pct restore.
    trades = ob.simulate_option_trades(
        _flat_session(), [(1, "LONG")], 0.15, ob.OptionExit(), strategy="X"
    )
    assert len(trades) == 1
    assert trades[0].contracts == 1


def test_every_exit_shape_can_be_evaluated() -> None:
    """Each shape must reach its own branch of _exit_signal without raising."""
    shapes = [
        ob.OptionExit(),                                  # default target/stop
        ob.ratchet_rules(25.0, -50.0),                    # step_pct branch
        ob.OptionExit(target_pct=None, stop_pct=None,
                      floor_trigger_pct=None, floor_pct=None,
                      time_stop_minutes=10),              # pure clock
        ob.OptionExit(underlying_stop_pct=0.15,
                      underlying_r_multiple=2.0),         # SPY_KEY_LEVELS
    ]
    for shape in shapes:
        trades = ob.simulate_option_trades(
            _flat_session(), [(1, "LONG")], 0.15, shape, strategy="X"
        )
        assert len(trades) == 1, shape.name


def test_a_pure_clock_exit_closes_on_its_own_minute() -> None:
    """No target, no stop - the only thing that can end the trade is time."""
    rules = ob.OptionExit(target_pct=None, stop_pct=None, floor_trigger_pct=None,
                          floor_pct=None, time_stop_minutes=15, name="15m")
    trades = ob.simulate_option_trades(
        _flat_session(), [(1, "LONG")], 0.15, rules, strategy="X"
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "time_stop"
    assert trade.exit_minute - trade.entry_minute == 15


def test_a_clock_exit_still_flattens_at_the_bell() -> None:
    """A 30-minute hold opened near the close exits at the close, not later."""
    rules = ob.OptionExit(target_pct=None, stop_pct=None, floor_trigger_pct=None,
                          floor_pct=None, time_stop_minutes=30, name="30m")
    rows = _flat_session(minutes=ob.LAST_EXIT_MINUTE + 20)
    entry_signal = ob.LAST_EXIT_MINUTE - 11  # fills on the next bar
    trades = ob.simulate_option_trades(
        rows, [(entry_signal, "LONG")], 0.15, rules, strategy="X"
    )
    assert len(trades) == 1
    trade = trades[0]
    assert trade.exit_reason == "eod_close"
    assert trade.exit_minute == ob.LAST_EXIT_MINUTE
    assert trade.exit_minute - trade.entry_minute < 30


def test_a_shorter_clock_frees_the_strategy_to_trade_again() -> None:
    """One position at a time: a 5m exit can take trades a 30m exit cannot.

    This is why trade counts differ across horizons rather than staying
    fixed - it is the behaviour of the rule, not a sampling artifact.
    """
    signals = [(1, "LONG"), (10, "LONG"), (20, "LONG")]
    rows = _flat_session(minutes=120)
    quick = ob.OptionExit(target_pct=None, stop_pct=None, floor_trigger_pct=None,
                          floor_pct=None, time_stop_minutes=5, name="5m")
    slow = ob.OptionExit(target_pct=None, stop_pct=None, floor_trigger_pct=None,
                         floor_pct=None, time_stop_minutes=30, name="30m")
    fast_trades = ob.simulate_option_trades(rows, signals, 0.15, quick, strategy="X")
    slow_trades = ob.simulate_option_trades(rows, signals, 0.15, slow, strategy="X")
    assert len(fast_trades) == 3
    assert len(slow_trades) == 1
