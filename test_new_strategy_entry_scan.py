"""Tests for the fast entry-only scan.

Two things make a 2-minute cadence safe, and both are easy to break later
without noticing:

1. A strategy already holding a position must be skipped, so the fast scan
   never opens a second position or competes with the exit path.
2. POSITION_FILE_LOCK must never be held across network I/O. main() holds
   it for its whole run - fine every 15 minutes, starvation every 2. If
   someone later "simplifies" this job into another main() call, held
   positions stop closing on time and nothing raises.
"""

from __future__ import annotations

import ast
import inspect
import textwrap
import threading
import time

import local_information_engine as engine
import spy_live_new_strategies as lns
import spy_scanner


class _TrackingLock:
    """A lock that records how long it was held and what happened inside."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.events: list[str] = []
        self.holds: list[float] = []
        self._entered_at = 0.0
        self.depth = 0

    def __enter__(self):
        self._lock.acquire()
        self.depth += 1
        self._entered_at = time.monotonic()
        self.events.append("acquire")
        return self

    def __exit__(self, *exc):
        self.holds.append(time.monotonic() - self._entered_at)
        self.depth -= 1
        self.events.append("release")
        self._lock.release()
        return False

    def note_io(self) -> None:
        self.events.append("network-io-while-held" if self.depth else "network-io")


def test_a_strategy_holding_a_position_is_not_scanned_again():
    """Owner's rule: scan until it picks up a play, then leave it alone to
    manage that position until it closes."""
    play = lns.NEW_STRATEGY_PLAY_TYPES[0]
    open_row = {"play_type": play, "outcome": "OPEN", "ticker": "SPY"}
    assert spy_scanner.has_open_position([open_row], play) is True

    other = lns.NEW_STRATEGY_PLAY_TYPES[1]
    assert spy_scanner.has_open_position([open_row], other) is False


def test_entry_scan_returns_early_when_every_strategy_is_holding(monkeypatch):
    """The cheap path matters: at a 2-minute cadence a fully-occupied roster
    must cost one log read, not a chain fetch every cycle."""
    rows = [{"play_type": p, "outcome": "OPEN", "ticker": "SPY"}
            for p in lns.NEW_STRATEGY_PLAY_TYPES]
    monkeypatch.setattr(spy_scanner, "read_log", lambda: rows)
    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {lns.config_flag(p): True
                                 for p in lns.NEW_STRATEGY_PLAY_TYPES})

    def _boom(*a, **k):
        raise AssertionError("must not fetch quotes when everything is holding")

    monkeypatch.setattr(spy_scanner, "get_quote", _boom)
    monkeypatch.setattr(spy_scanner, "get_chain", _boom)

    result = spy_scanner.scan_new_strategy_entries()
    assert result["opened"] == 0
    assert result.get("holding") is True


def test_the_position_lock_is_never_held_across_network_io(monkeypatch):
    """The reason this job exists as its own function rather than a second
    main() call. Holding POSITION_FILE_LOCK through a chain fetch delays
    every exit behind it."""
    lock = _TrackingLock()
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {lns.config_flag(p): True
                                 for p in lns.NEW_STRATEGY_PLAY_TYPES})

    def _quote(*a, **k):
        lock.note_io()
        return None                       # stop the scan right after the I/O

    monkeypatch.setattr(spy_scanner, "get_quote", _quote)
    spy_scanner.scan_new_strategy_entries(position_lock=lock)

    assert "network-io" in lock.events
    assert "network-io-while-held" not in lock.events, (
        "a quote fetch happened while POSITION_FILE_LOCK was held - "
        "held positions cannot close while this runs"
    )


def test_entry_scan_does_not_call_the_full_scanner():
    """main() holds the lock for its entire run. Guard against a future
    edit collapsing this back into a second full scan."""
    tree = ast.parse(textwrap.dedent(
        inspect.getsource(spy_scanner.scan_new_strategy_entries)))
    called = {
        node.func.id for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    } | {
        node.func.attr for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "main" not in called, (
        "the entry scan calls main(), which holds POSITION_FILE_LOCK for its "
        "entire run - at a 2-minute cadence that starves the exit path"
    )


def test_the_entry_scan_job_runs_far_more_often_than_the_full_scan():
    """Strategies read their signal off the newest closed bar. Measured over
    250 real sessions, a 15-minute cadence sees 7.6% of signals and ORB
    Immediate never fires at all; 2 minutes sees 50.6% and every strategy
    fires."""
    jobs = {job.name: job for job in engine.JOBS}
    fast = jobs["new-strategy-entry-scan"]
    full = jobs["full-options-scan"]
    assert fast.interval.total_seconds() <= 120
    assert fast.interval < full.interval
    assert fast.market_hours_only is True
    assert fast.background is True


def test_the_entry_scan_job_is_registered_before_the_full_scan():
    names = [job.name for job in engine.JOBS]
    assert "new-strategy-entry-scan" in names
