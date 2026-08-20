"""The generic engine has to reproduce the old one, and not know about
any strategy.

Two properties matter more than any individual number here:

1. `premium_exit()` must produce byte-identical trades to
   `spy_option_backtest.simulate_option_trades` for every exit shape the
   system has ever measured. Without that, adopting this engine silently
   rewrites the BASELINE.
2. Deleting a live strategy must not affect the engine at all. That is
   exactly what broke in #274 and #281, where the harness held strategy
   names and an erasure killed it.
"""

from __future__ import annotations

import backtest_lab as lab
import spy_option_backtest as ob


def _session(closes: list[float], session: str = "2026-01-02") -> list[dict]:
    return [
        {"session_date": session, "open": price, "high": price + 0.05,
         "low": price - 0.05, "close": price, "minutes_since_open": minute,
         "vwap": 500.0}
        for minute, price in enumerate(closes)
    ]


def _drifting(minutes: int = 200, start: float = 500.0, step: float = 0.03):
    return _session([start + step * i for i in range(minutes)])


def _choppy(minutes: int = 200, start: float = 500.0):
    return _session([start + (2.0 if i % 7 < 3 else -1.5) for i in range(minutes)])


SHAPES = [
    ob.OptionExit(),                                                    # default
    ob.OptionExit(target_pct=115, stop_pct=-75, floor_trigger_pct=None,
                  floor_pct=None),                                      # a live shape
    ob.OptionExit(target_pct=None, stop_pct=None, floor_trigger_pct=None,
                  floor_pct=None, time_stop_minutes=15),                # pure clock
    ob.OptionExit(target_pct=50, stop_pct=-50, floor_trigger_pct=None,
                  floor_pct=None, stagnation_pct=-40, stagnation_minutes=20),
    ob.OptionExit(underlying_stop_pct=0.15, underlying_r_multiple=2.0),  # key-levels
    ob.ratchet_rules(25.0, -50.0),                                      # ratchet
]


def test_premium_exit_reproduces_the_original_engine_exactly() -> None:
    """Same entries, same shape - the two engines must agree trade for trade."""
    signals = [(1, "LONG"), (40, "SHORT"), (90, "LONG")]
    for rows in (_drifting(), _choppy()):
        for shape in SHAPES:
            old = ob.simulate_option_trades(rows, signals, 0.15, shape, strategy="X")
            new = lab.simulate(rows, signals, 0.15, lab.premium_exit(shape), label="X")
            assert len(old) == len(new), shape.name
            for a, b in zip(old, new):
                assert (a.entry_minute, a.exit_minute, a.exit_reason) == \
                       (b.entry_minute, b.exit_minute, b.exit_reason), shape.name
                assert round(a.pnl_dollars, 9) == round(b.pnl_dollars, 9), shape.name


def test_the_engine_does_not_know_any_strategy_exists() -> None:
    """Erasing the whole live roster must not touch the engine.

    #274 and #281 each deleted one symbol and killed the option layer,
    because the harness held strategy names. This one holds none.
    """
    import spy_live_new_strategies as lns

    original = lns.NEW_STRATEGY_SPECS
    lns.NEW_STRATEGY_SPECS = ()          # every live strategy, gone
    try:
        trades = lab.simulate(_drifting(), [(1, "LONG")], 0.15,
                              lab.hold_for(10), label="anything")
        assert len(trades) == 1
    finally:
        lns.NEW_STRATEGY_SPECS = original

    # Check the CODE, not the prose - the docstring explains this history
    # on purpose, and a plain substring search would flag its own
    # explanation. Two things must hold: the engine imports no strategy
    # registry, and no strategy name appears in any live string constant.
    import ast

    tree = ast.parse(open(lab.__file__, encoding="utf-8").read())
    imported = {node.module for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module}
    imported |= {alias.name for node in ast.walk(tree)
                 if isinstance(node, ast.Import) for alias in node.names}
    assert "spy_live_new_strategies" not in imported
    assert "spy_scanner" not in imported
    assert "spy_backtest_report" not in imported

    docstrings = {
        ast.get_docstring(node, clean=False)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef))
    }
    literals = [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value not in docstrings
    ]
    assert not [text for text in literals if "SPY_" in text], literals


def test_an_exit_idea_that_no_dataclass_field_could_express() -> None:
    """The point of a callable: reach any feature on the bar."""
    def out_when_spot_loses_vwap(state: lab.TradeState) -> str | None:
        if state.direction == "LONG" and state.spot < state.row["vwap"]:
            return "lost_vwap"
        return None

    rows = _session([501.0] * 5 + [499.0] * 50)   # vwap is 500.0
    trades = lab.simulate(rows, [(1, "LONG")], 0.15,
                          out_when_spot_loses_vwap, label="vwap idea")
    assert len(trades) == 1
    assert trades[0].exit_reason == "lost_vwap"
    assert trades[0].exit_minute == 5


def test_trade_state_exposes_drawdown_and_underlying_move() -> None:
    seen: list[lab.TradeState] = []

    def recorder(state: lab.TradeState) -> str | None:
        seen.append(state)
        return "done" if state.minutes_held >= 3 else None

    lab.simulate(_drifting(), [(1, "LONG")], 0.15, recorder, label="probe")
    assert seen
    last = seen[-1]
    assert last.drawdown_pct <= 0                       # peak is never below pnl
    assert last.spot_move_pct > 0                       # a rising tape, held LONG


def test_a_short_position_reads_a_falling_tape_as_favourable() -> None:
    seen: list[lab.TradeState] = []

    def recorder(state: lab.TradeState) -> str | None:
        seen.append(state)
        return "done" if state.minutes_held >= 5 else None

    falling = _session([500.0 - 0.05 * i for i in range(60)])
    lab.simulate(falling, [(1, "SHORT")], 0.15, recorder, label="probe")
    assert seen[-1].spot_move_pct > 0


def test_the_bell_closes_a_trade_the_idea_wants_to_keep() -> None:
    """An idea that never exits still gets flattened at 15:45."""
    never = lambda state: None                      # noqa: E731 - the point
    rows = _session([500.0] * (ob.LAST_EXIT_MINUTE + 30))
    trades = lab.simulate(rows, [(ob.LAST_EXIT_MINUTE - 21, "LONG")], 0.15,
                          never, label="stubborn")
    assert len(trades) == 1
    assert trades[0].exit_reason == "eod_close"
    assert trades[0].exit_minute == ob.LAST_EXIT_MINUTE


def test_first_of_takes_the_earliest_rule_in_priority_order() -> None:
    rule = lab.first_of(lab.target_and_stop(1000.0, -1000.0), lab.hold_for(4))
    trades = lab.simulate(_drifting(), [(1, "LONG")], 0.15, rule, label="combo")
    assert trades[0].exit_reason == "time_stop"
    assert trades[0].exit_minute - trades[0].entry_minute == 4


def test_trailing_stop_does_not_arm_below_its_trigger() -> None:
    armed = lab.trailing_stop(give_back_pct=5.0, arm_at_pct=1_000_000.0)
    trades = lab.simulate(_choppy(), [(1, "LONG")], 0.15, armed, label="never arms")
    assert trades[0].exit_reason == "eod_close"


def test_summarize_counts_what_it_says_it_counts() -> None:
    trades = lab.simulate(_drifting(), [(1, "LONG"), (60, "LONG")], 0.15,
                          lab.hold_for(10), label="clock")
    result = lab.summarize("clock", trades)
    assert result.trades == len(trades)
    assert sum(result.exit_reasons.values()) == len(trades)
    assert round(result.total_dollars, 6) == round(
        sum(t.pnl_dollars for t in trades), 6)


def test_coverage_flags_a_window_with_no_daily_0dte() -> None:
    """The archive currently stops in 2021 - a result must say so."""
    stale = lab.Coverage(988, "2010-01-15", "2021-05-05", 12.0)
    assert not stale.covers_daily_0dte_era
    assert "no daily 0DTE" in stale.warning()

    current = lab.Coverage(300, "2024-01-02", "2026-08-19", 12.0)
    assert current.covers_daily_0dte_era
    assert current.warning() == ""


def test_empty_result_is_reportable_rather_than_a_crash() -> None:
    result = lab.summarize("fires never", [])
    assert result.trades == 0
    text = lab.report([result], lab.Coverage(0, None, None, 0.0))
    assert "fires never" in text
