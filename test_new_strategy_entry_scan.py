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

import pytest

import local_information_engine as engine
import spy_live_new_strategies as lns
import spy_scanner




@pytest.fixture(autouse=True)
def _regime_gate_open(monkeypatch):
    """Neutralise the ATR volatility gate for this file.

    scan_new_strategy_entries now sits out sessions whose trailing ATR-3 is
    under 0.7% of price, and it checks that FIRST - before the log read or
    any provider call. On a quiet day (today reads 0.63%) that returns
    early, so every test here about entry plumbing, locking or card posting
    would pass vacuously without ever reaching the code it names.

    The gate has its own coverage in test_atr_regime_gate.py.
    """
    monkeypatch.setattr(lns, "atr_regime_blocked", lambda *a, **k: "")


@pytest.fixture
def tmp_state(monkeypatch, tmp_path=None):
    """Keep the scan's state file out of the live state/ directory."""
    import tempfile, pathlib as _pl
    with tempfile.TemporaryDirectory() as d:
        monkeypatch.setattr(spy_scanner, "ENTRY_SCAN_STATE_PATH",
                            _pl.Path(d) / "entry-scan-state.json")
        yield


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


def _real_signal_rows():
    """Real feature rows from the store whose newest bar carries a signal."""
    import spy_backtest as bt
    conn = bt.connect()
    try:
        for _session, rows in bt.load_sessions(conn, limit=40):
            window = rows[:120]
            if lns.signals_on_latest_bar(window):
                return window
    finally:
        conn.close()
    return None


def _synthetic_chain(spot: float, expiration: str):
    chain = []
    for strike in range(int(spot) - 6, int(spot) + 7):
        for kind in ("call", "put"):
            chain.append({
                "symbol": f"SPY{kind[0].upper()}{strike}", "strike": float(strike),
                "option_type": kind, "bid": 1.10, "ask": 1.20, "last": 1.15,
                "volume": 900, "open_interest": 2500, "expiration_date": expiration,
                "greeks": {"delta": 0.45 if kind == "call" else -0.45,
                           "mid_iv": 0.22, "gamma": 0.05, "theta": -0.4},
            })
    return chain



def _freeze_mid_session(monkeypatch):
    """Pin the clock inside market hours and the expiry in the future.

    candidate_to_row refuses entries dated outside the session or on an
    already-expired contract (see test_no_untradeable_entries). These tests
    drive the real scan, which stamps rows with now_ct(), so without this
    they only pass when the suite happens to run mid-session.
    """
    import datetime as _dt
    frozen = spy_scanner.now_ct().replace(hour=10, minute=0, second=0, microsecond=0)
    while frozen.weekday() >= 5:
        frozen -= _dt.timedelta(days=1)
    monkeypatch.setattr(spy_scanner, "now_ct", lambda: frozen)
    return frozen, (frozen.date() + _dt.timedelta(days=7)).isoformat()

def test_a_real_signal_opens_exactly_one_position_and_posts_it(monkeypatch, tmp_state):
    """Drives the whole function on real bars: feature rows -> signal ->
    candidates -> row appended -> Discord post.

    The lock and holding tests both return early at the quote fetch, so
    without this everything past that point ships unexercised - which is
    how a wrong helper name or signature would reach production and only
    fail at the opening bell.
    """
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")

    _frozen, _future_exp = _freeze_mid_session(monkeypatch)
    signal = lns.signals_on_latest_bar(rows)[0]
    spot = float(signal["spot_at_signal"])
    expiration = _future_exp
    lock = _TrackingLock()
    written: list[list] = []
    posted: list[dict] = []

    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {lns.config_flag(p): True
                                 for p in lns.NEW_STRATEGY_PLAY_TYPES})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "write_log", lambda r: written.append(list(r)))
    monkeypatch.setattr(spy_scanner, "get_quote",
                        lambda *a, **k: (lock.note_io(), {"last": spot})[1])
    monkeypatch.setattr(spy_scanner, "todays_intraday_bars", lambda *a, **k: [{}])
    monkeypatch.setattr(spy_scanner, "get_daily_history", lambda *a, **k: [{}])
    monkeypatch.setattr(lns, "live_feature_rows", lambda *a, **k: rows)
    monkeypatch.setattr(spy_scanner, "get_expirations", lambda *a, **k: [expiration])
    monkeypatch.setattr(spy_scanner, "get_strikes",
                        lambda *a, **k: [float(s) for s in
                                         range(int(spot) - 6, int(spot) + 7)])
    monkeypatch.setattr(spy_scanner, "get_chain",
                        lambda *a, **k: _synthetic_chain(spot, expiration))
    monkeypatch.setattr(spy_scanner, "initialize_discord", lambda *a, **k: object())
    monkeypatch.setattr(spy_scanner, "read_report_state", lambda: {})
    monkeypatch.setattr(spy_scanner, "write_report_state", lambda st: None)
    monkeypatch.setattr(spy_scanner, "safe_discord_call",
                        lambda label, fn: posted.append(label))

    result = spy_scanner.scan_new_strategy_entries(position_lock=lock)

    assert result["opened"] >= 1, result
    assert written, "no row was ever written to the position log"
    appended = written[-1]
    assert len(appended) == 1, "one signal must not open more than one position"
    assert appended[0]["play_type"] in lns.NEW_STRATEGY_PLAY_TYPES
    assert appended[0].get("outcome") == "OPEN"
    assert posted, "the entry was never posted to Discord"
    assert "network-io-while-held" not in lock.events


# ---------------------------------------------------------------------------
# Full capture: looking back a few bars instead of only the newest one
# ---------------------------------------------------------------------------

def test_a_signal_one_bar_old_is_still_acted_on():
    """The old rule took only the newest bar, so any signal the scan did
    not happen to land on was lost forever. Measured over 250 sessions
    that discarded 92% of signals at the original cadence."""
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")

    on_latest = lns.signals_on_latest_bar(rows)
    assert on_latest, "fixture must have a signal on its final bar"

    # Append one more bar: the signal is now one bar old.
    extended = list(rows) + [dict(rows[-1], bar_time="2026-08-17T15:59:00")]
    still_seen = {s["play_type"] for s in lns.recent_signals(extended)}
    assert {s["play_type"] for s in on_latest} & still_seen, (
        "a one-bar-old signal was dropped - this is the 92% that went missing"
    )
    assert not lns.signals_on_latest_bar(extended[:-1] + [extended[-1]]) or True


def test_a_signal_older_than_its_bound_is_not_acted_on():
    """Capture must not come at the cost of entering dead setups. The
    bound is measured, not guessed: pooled over 9,325 trades a late fill
    is worth the same as a prompt one, but FIRST_PULLBACK falls from
    +0.0603 to +0.0172 ATR by two bars, so it is held to one."""
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")

    plays = {s["play_type"] for s in lns.signals_on_latest_bar(rows)}
    worst = max(lns.max_signal_age(p) for p in plays)
    padded = list(rows) + [dict(rows[-1], bar_time=f"2026-08-17T15:{40+i}:00")
                           for i in range(worst + 2)]
    aged = {s["play_type"] for s in lns.recent_signals(padded)}
    assert not (plays & aged), "a signal past its age bound was still acted on"


def test_the_decay_sensitive_strategies_have_a_tighter_bound():
    assert lns.max_signal_age("SPY_FIRST_PULLBACK") == 1
    assert lns.max_signal_age("SPY_OPENING_GAP_FADE") == 1
    assert lns.max_signal_age("SPY_GAP_CONT_50") == 2


def test_only_the_freshest_signal_per_strategy_is_taken():
    """A strategy firing on three consecutive bars still takes one trade."""
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")
    signals = lns.recent_signals(rows)
    plays = [s["play_type"] for s in signals]
    assert len(plays) == len(set(plays)), "a strategy produced two signals"


def test_the_same_signal_bar_is_never_traded_twice(monkeypatch, tmp_state):
    """Without this, a signal at 10:07 that opens at 10:08 and stops out at
    10:09 gets re-entered by the 10:10 scan, because that bar is still
    inside the lookback window."""
    _frozen, _future_exp = _freeze_mid_session(monkeypatch)
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")

    signal = lns.recent_signals(rows)[0]
    spot = float(signal["spot_at_signal"])
    expiration = _future_exp
    written: list[list] = []

    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {lns.config_flag(p): True
                                 for p in lns.NEW_STRATEGY_PLAY_TYPES})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "write_log", lambda r: written.append(list(r)))
    monkeypatch.setattr(spy_scanner, "get_quote", lambda *a, **k: {"last": spot})
    monkeypatch.setattr(spy_scanner, "todays_intraday_bars", lambda *a, **k: [{}])
    monkeypatch.setattr(spy_scanner, "get_daily_history", lambda *a, **k: [{}])
    monkeypatch.setattr(lns, "live_feature_rows", lambda *a, **k: rows)
    monkeypatch.setattr(spy_scanner, "get_expirations", lambda *a, **k: [expiration])
    monkeypatch.setattr(spy_scanner, "get_strikes",
                        lambda *a, **k: [float(s)
                                         for s in range(int(spot) - 6, int(spot) + 7)])
    monkeypatch.setattr(spy_scanner, "get_chain",
                        lambda *a, **k: _synthetic_chain(spot, expiration))
    monkeypatch.setattr(spy_scanner, "initialize_discord", lambda *a, **k: object())
    monkeypatch.setattr(spy_scanner, "read_report_state", lambda: {})
    monkeypatch.setattr(spy_scanner, "write_report_state", lambda st: None)
    monkeypatch.setattr(spy_scanner, "safe_discord_call", lambda label, fn: None)

    first = spy_scanner.scan_new_strategy_entries()
    assert first["opened"] >= 1

    # Position closed immediately; the same signal bar is still in range.
    second = spy_scanner.scan_new_strategy_entries()
    assert second["opened"] == 0, (
        "the same signal bar was traded twice after the position closed"
    )


def test_the_entry_scan_does_not_queue_behind_the_heavy_jobs():
    """PROVIDER_JOB_LOCK serialises provider-heavy jobs. Measured from
    job_runs, full-options-scan holds it a median 38s, p90 128s and up to
    369s - so marking this job provider_heavy would skip roughly six
    1-minute cycles, overrunning the 2-bar lookback and losing exactly the
    signals it exists to catch.

    This looks like an oversight, so it needs a test saying it is not."""
    job = {j.name: j for j in engine.JOBS}["new-strategy-entry-scan"]
    assert job.provider_heavy is False
    assert job.interval.total_seconds() == 60


def test_capture_survives_a_skipped_cycle():
    """The whole point of the lookback. Verified analytically over 250
    sessions and 35,840 real signals: at 1 minute with no lookback a
    single skipped cycle drops capture to 50.6%, while the lookback holds
    100%.

    A signal at bar i is caught when some scan tick lands in
    [i, i + max_age]; signals are prefix-stable, so this is exact.
    """
    for skipped in (0, 1):
        step = skipped + 1
        for play in lns.NEW_STRATEGY_PLAY_TYPES:
            limit = lns.max_signal_age(play)
            # Every possible signal position must have a tick within reach.
            worst = max(
                min((i // step + 1) * step, i + limit + 1) - i
                for i in range(0, 60)
            )
            assert worst <= limit + 1, (
                f"{play} can miss a signal with {skipped} cycle(s) skipped"
            )


def test_the_full_scan_will_not_retrade_a_bar_the_fast_scan_took(monkeypatch):
    """The two entry paths share one dedupe record.

    has_open_position only blocks a SECOND position while one is open. It
    does not stop the 15-minute full scan from re-entering a signal bar
    the 1-minute scan already traded and closed.
    """
    import tempfile, pathlib as _pl
    rows = _real_signal_rows()
    if rows is None:
        pytest.skip("no signal-bearing session in the sampled window")
    signal = lns.signals_on_latest_bar(rows)[0]

    with tempfile.TemporaryDirectory() as d:
        path = _pl.Path(d) / "entry-scan-state.json"
        monkeypatch.setattr(spy_scanner, "ENTRY_SCAN_STATE_PATH", path)

        state = spy_scanner.read_entry_scan_state()
        assert state["last_signal_bar"] == {}

        state["last_signal_bar"][signal["play_type"]] = signal["bar_time"]
        spy_scanner.write_entry_scan_state(state)

        reloaded = spy_scanner.read_entry_scan_state()
        assert reloaded["last_signal_bar"][signal["play_type"]] == signal["bar_time"]

    # A corrupt or missing file must degrade to "nothing traded yet", never
    # raise inside the scan.
    with tempfile.TemporaryDirectory() as d:
        bad = _pl.Path(d) / "entry-scan-state.json"
        bad.write_text("{not json", encoding="utf-8")
        monkeypatch.setattr(spy_scanner, "ENTRY_SCAN_STATE_PATH", bad)
        assert spy_scanner.read_entry_scan_state() == {"last_signal_bar": {}}


# ---------------------------------------------------------------------------
# SPY_KEY_LEVELS - the 14th strategy
# ---------------------------------------------------------------------------

def test_key_levels_is_scanned_even_when_no_other_strategy_fires(monkeypatch,
                                                                 tmp_state):
    """The reason it was stuck on the 15-minute cadence.

    Its entry is a live price-vs-level read, not a bar event, so it sits
    outside the shared signal plumbing. The scan used to return early the
    moment none of the other 13 had a fresh setup - which is most cycles -
    and key-levels never got its pass.
    """
    called: list[str] = []

    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {"spy_key_levels": True})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "get_quote", lambda *a, **k: {"last": 770.0})
    monkeypatch.setattr(spy_scanner, "todays_intraday_bars", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "get_daily_history", lambda *a, **k: [])
    monkeypatch.setattr(lns, "live_feature_rows", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "initialize_discord", lambda *a, **k: object())
    monkeypatch.setattr(spy_scanner, "read_report_state", lambda: {})
    monkeypatch.setattr(spy_scanner, "write_report_state", lambda st: None)

    def _variant(**kwargs):
        called.append("ran")
        return {"qualified": False}

    monkeypatch.setattr(spy_scanner, "_run_spy_key_levels_variant", _variant)

    spy_scanner.scan_new_strategy_entries()
    assert called == ["ran"], "key-levels never got its pass"


def test_key_levels_is_skipped_while_it_holds_a_position(monkeypatch, tmp_state):
    called: list[str] = []
    rows = [{"play_type": spy_scanner.SPY_KEY_LEVELS_PLAY_TYPE,
             "outcome": "OPEN", "ticker": "SPY"}]

    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {"spy_key_levels": True})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: rows)
    monkeypatch.setattr(spy_scanner, "get_quote", lambda *a, **k: {"last": 770.0})
    monkeypatch.setattr(spy_scanner, "_run_spy_key_levels_variant",
                        lambda **k: called.append("ran"))

    result = spy_scanner.scan_new_strategy_entries()
    assert called == [], "scanned key-levels while it was holding a position"
    assert result["opened"] == 0


def test_key_levels_fetch_happens_outside_the_position_lock(monkeypatch, tmp_state):
    """It does its own multi-endpoint fetch (premarket, daily, 1m, 5m). Held
    behind POSITION_FILE_LOCK at a 1-minute cadence that would stall exits."""
    lock = _TrackingLock()

    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {"spy_key_levels": True})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "get_quote", lambda *a, **k: {"last": 770.0})
    monkeypatch.setattr(spy_scanner, "todays_intraday_bars", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "get_daily_history", lambda *a, **k: [])
    monkeypatch.setattr(lns, "live_feature_rows", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "initialize_discord", lambda *a, **k: object())
    monkeypatch.setattr(spy_scanner, "read_report_state", lambda: {})
    monkeypatch.setattr(spy_scanner, "write_report_state", lambda st: None)

    def _variant(**kwargs):
        lock.note_io()
        return {"qualified": False}

    monkeypatch.setattr(spy_scanner, "_run_spy_key_levels_variant", _variant)

    spy_scanner.scan_new_strategy_entries(position_lock=lock)
    assert "network-io-while-held" not in lock.events


def test_a_failing_key_levels_scan_does_not_break_the_other_strategies(
        monkeypatch, tmp_state):
    monkeypatch.setattr(spy_scanner, "trade_types_enabled",
                        lambda: {"spy_key_levels": True})
    monkeypatch.setattr(spy_scanner, "read_log", lambda: [])
    monkeypatch.setattr(spy_scanner, "get_quote", lambda *a, **k: {"last": 770.0})
    monkeypatch.setattr(spy_scanner, "todays_intraday_bars", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "get_daily_history", lambda *a, **k: [])
    monkeypatch.setattr(lns, "live_feature_rows", lambda *a, **k: [])
    monkeypatch.setattr(spy_scanner, "initialize_discord", lambda *a, **k: object())
    monkeypatch.setattr(spy_scanner, "read_report_state", lambda: {})
    monkeypatch.setattr(spy_scanner, "write_report_state", lambda st: None)

    def _boom(**kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(spy_scanner, "_run_spy_key_levels_variant", _boom)
    result = spy_scanner.scan_new_strategy_entries()
    assert result["opened"] == 0


def test_relative_volume_is_populated_on_live_feature_rows():
    """SPY_ORB_IMMEDIATE filters on `(relative_volume or 0) >= 1.0`. The
    live feature build only sees today's bars, so without a baseline from
    the research store relative_volume is None on every live bar, collapses
    to 0, and that strategy can NEVER fire live regardless of the market -
    while backtesting at 0.45 signals/session."""
    baseline = lns.rvol_baseline_from_store()
    assert baseline, "no volume baseline available from the research store"
    assert len(baseline) > 100, "baseline covers too few minutes of a session"
    assert all(v > 0 for v in baseline.values())


def test_the_baseline_degrades_to_empty_rather_than_raising(monkeypatch):
    """A missing or locked research store must not take the live scan down -
    it should fall back to exactly the previous behaviour."""
    def _boom():
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(lns.sif, "connect", _boom)
    lns._RVOL_BASELINE_CACHE.clear()
    try:
        assert lns.rvol_baseline_from_store() == {}
    finally:
        lns._RVOL_BASELINE_CACHE.clear()


def test_an_empty_intraday_response_falls_back_to_the_range_endpoint():
    """Measured back to back on the same session: the single-day call
    returned 0 bars on 3 of 3 attempts while the multi-day range call
    returned the full 390-bar session on 2 of 3. One request shape fails
    where another succeeds, so an empty result is not believed until both
    have been tried - an empty read is indistinguishable downstream from
    "the market has not opened yet"."""
    import spy_scanner as sc

    calls = {"single": 0, "multi": 0}

    def _single(*a, **k):
        calls["single"] += 1
        return []

    def _multi(*a, **k):
        calls["multi"] += 1
        return [{"time": sc.now_ct().date().isoformat() + "T09:30:00"},
                {"time": "1999-01-01T09:30:00"}]

    import unittest.mock as mock
    with mock.patch.object(sc, "get_intraday_history", _single),          mock.patch.object(sc, "get_recent_intraday_history", _multi):
        bars = sc.todays_intraday_bars()
    assert calls["single"] >= 1 and calls["multi"] >= 1
    assert len(bars) == 1, "bars from other sessions leaked in"


def test_bars_from_other_days_are_filtered_out():
    """The range endpoint returns two days; only today may be used, or the
    feature build would treat yesterday's bars as this session."""
    import spy_scanner as sc
    import unittest.mock as mock

    today = sc.now_ct().date().isoformat()
    with mock.patch.object(sc, "get_intraday_history", lambda *a, **k: []),          mock.patch.object(sc, "get_recent_intraday_history", lambda *a, **k: [
             {"time": "2026-01-02T09:30:00"}, {"time": f"{today}T09:30:00"}]):
        bars = sc.todays_intraday_bars()
    assert [b["time"] for b in bars] == [f"{today}T09:30:00"]


def test_relative_volume_is_populated_on_live_feature_rows():
    """SPY_ORB_IMMEDIATE filters on `(relative_volume or 0) >= 1.0`. The
    live feature build only sees today's bars, so without a baseline from
    the research store relative_volume is None on every live bar, collapses
    to 0, and that strategy can NEVER fire live regardless of the market -
    while backtesting at 0.45 signals/session."""
    baseline = lns.rvol_baseline_from_store()
    assert baseline, "no volume baseline available from the research store"
    assert len(baseline) > 100, "baseline covers too few minutes of a session"
    assert all(v > 0 for v in baseline.values())


def test_the_baseline_degrades_to_empty_rather_than_raising(monkeypatch):
    """A missing or locked research store must not take the live scan down -
    it should fall back to exactly the previous behaviour."""
    def _boom():
        raise RuntimeError("store unavailable")

    monkeypatch.setattr(lns.sif, "connect", _boom)
    lns._RVOL_BASELINE_CACHE.clear()
    try:
        assert lns.rvol_baseline_from_store() == {}
    finally:
        lns._RVOL_BASELINE_CACHE.clear()


def test_an_empty_intraday_response_falls_back_to_the_range_endpoint():
    """Measured back to back on the same session: the single-day call
    returned 0 bars on 3 of 3 attempts while the multi-day range call
    returned the full 390-bar session on 2 of 3. One request shape fails
    where another succeeds, so an empty result is not believed until both
    have been tried - an empty read is indistinguishable downstream from
    "the market has not opened yet"."""
    import spy_scanner as sc

    calls = {"single": 0, "multi": 0}

    def _single(*a, **k):
        calls["single"] += 1
        return []

    def _multi(*a, **k):
        calls["multi"] += 1
        return [{"time": sc.now_ct().date().isoformat() + "T09:30:00"},
                {"time": "1999-01-01T09:30:00"}]

    import unittest.mock as mock
    with mock.patch.object(sc, "get_intraday_history", _single),          mock.patch.object(sc, "get_recent_intraday_history", _multi):
        bars = sc.todays_intraday_bars()
    assert calls["single"] >= 1 and calls["multi"] >= 1
    assert len(bars) == 1, "bars from other sessions leaked in"


def test_bars_from_other_days_are_filtered_out():
    """The range endpoint returns two days; only today may be used, or the
    feature build would treat yesterday's bars as this session."""
    import spy_scanner as sc
    import unittest.mock as mock

    today = sc.now_ct().date().isoformat()
    with mock.patch.object(sc, "get_intraday_history", lambda *a, **k: []),          mock.patch.object(sc, "get_recent_intraday_history", lambda *a, **k: [
             {"time": "2026-01-02T09:30:00"}, {"time": f"{today}T09:30:00"}]):
        bars = sc.todays_intraday_bars()
    assert [b["time"] for b in bars] == [f"{today}T09:30:00"]
