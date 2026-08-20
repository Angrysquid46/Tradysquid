"""The fast sweep must agree with the slow engine, trade for trade.

exit_sweep prices each signal once and replays exit rules over the stored
path. That is only worth having if it produces exactly what
backtest_lab.simulate produces running the same rule directly - otherwise
it is a faster way to be wrong, which is how this project got here.
"""

from __future__ import annotations

import backtest_lab as lab
import exit_sweep as es
import spy_option_backtest as ob


def _session(closes: list[float], session: str = "2026-01-02") -> list[dict]:
    return [
        {"session_date": session, "open": price, "high": price + 0.05,
         "low": price - 0.05, "close": price, "minutes_since_open": minute,
         "vwap": 500.0}
        for minute, price in enumerate(closes)
    ]


def _drifting(minutes=240, start=500.0, step=0.03):
    return _session([start + step * i for i in range(minutes)])


def _choppy(minutes=240, start=500.0):
    return _session([start + (3.0 if i % 11 < 5 else -2.0) for i in range(minutes)])


def _volatile(minutes=240, start=500.0):
    return _session([start + (i % 17) * 0.4 - (i % 7) * 0.3 for i in range(minutes)])


RULES = {
    "clock 5m": lab.hold_for(5),
    "clock 30m": lab.hold_for(30),
    "t50/s50": lab.target_and_stop(50.0, -50.0),
    "t115/s75": lab.target_and_stop(115.0, -75.0),
    "trail 25 after 40": lab.trailing_stop(25.0, 40.0),
    "combo": lab.first_of(lab.target_and_stop(100.0, -60.0), lab.hold_for(20)),
    "never": lambda state: None,
}

SIGNALS = [(1, "LONG"), (12, "LONG"), (30, "SHORT"), (75, "LONG"), (140, "SHORT")]


def test_the_sweep_reproduces_the_engine_trade_for_trade() -> None:
    for rows in (_drifting(), _choppy(), _volatile()):
        paths = es.build_paths(rows, SIGNALS, 0.15)
        for name, rule in RULES.items():
            direct = lab.simulate(rows, SIGNALS, 0.15, rule, label="X")
            swept = es.apply_rule(paths, rule, label="X")
            assert len(direct) == len(swept), name
            for a, b in zip(direct, swept):
                assert (a.entry_minute, a.exit_minute, a.exit_reason) == \
                       (b.entry_minute, b.exit_minute, b.exit_reason), name
                assert round(a.pnl_dollars, 9) == round(b.pnl_dollars, 9), name


def test_one_position_at_a_time_is_preserved() -> None:
    """A fast exit takes signals a slow exit is still holding through."""
    rows = _drifting()
    paths = es.build_paths(rows, SIGNALS, 0.15)
    quick = es.apply_rule(paths, lab.hold_for(2), label="q")
    slow = es.apply_rule(paths, lab.hold_for(200), label="s")
    assert len(quick) > len(slow)
    assert len(slow) == 1


def test_paths_are_priced_once_per_signal_not_per_rule() -> None:
    """The whole point: pricing cost does not grow with the number of
    exits tested."""
    calls = {"n": 0}
    real = es.om.quote

    def counting(*args, **kwargs):
        calls["n"] += 1
        return real(*args, **kwargs)

    es.om.quote = counting
    try:
        rows = _drifting()
        paths = es.build_paths(rows, SIGNALS, 0.15)
        after_build = calls["n"]
        for rule in RULES.values():
            es.apply_rule(paths, rule, label="X")
        assert calls["n"] == after_build      # not one more quote
    finally:
        es.om.quote = real


def test_a_rule_that_never_exits_is_flattened_at_the_bell() -> None:
    rows = _session([500.0] * (ob.LAST_EXIT_MINUTE + 30))
    paths = es.build_paths(rows, [(ob.LAST_EXIT_MINUTE - 21, "LONG")], 0.15)
    trades = es.apply_rule(paths, lambda state: None, label="X")
    assert len(trades) == 1
    assert trades[0].exit_reason == "eod_close"
    assert trades[0].exit_minute == ob.LAST_EXIT_MINUTE
