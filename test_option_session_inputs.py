"""Session scoreability and volatility provenance.

Both halves of this exist because the option archive stops at 2023-12-29
and had no fallback: every session after it was silently unscoreable, and
the only volatility source died with the table.
"""

from __future__ import annotations

import sqlite3

import capture_0dte_chain as cap
import option_session_inputs as osi


# ---------------------------------------------------------------------------
# Which sessions can be scored
# ---------------------------------------------------------------------------

def test_a_recent_weekday_needs_no_table_to_be_known_scoreable() -> None:
    # 2026-08-19 is a Wednesday, long after daily 0DTE began.
    assert osi.zero_dte_listed("2026-08-19", chain_sessions=set())


def test_a_weekend_is_never_scoreable() -> None:
    assert not osi.zero_dte_listed("2026-08-22", chain_sessions=set())  # Saturday
    assert not osi.zero_dte_listed("2026-08-23", chain_sessions=set())  # Sunday


def test_before_the_cutover_only_the_real_record_counts() -> None:
    """Guessing Mon/Wed/Fri would invent listings that never existed."""
    assert not osi.zero_dte_listed("2015-06-10", chain_sessions=set())
    assert osi.zero_dte_listed("2015-06-10", chain_sessions={"2015-06-10"})


def test_the_cutover_dates_are_the_documented_ones() -> None:
    # The day before daily expiries, a Tuesday, is covered by the Tue/Thu
    # rule; long before either, nothing is assumed.
    assert osi.zero_dte_listed("2022-05-04", chain_sessions=set())
    assert not osi.zero_dte_listed("2022-01-05", chain_sessions=set())


def test_scoreable_sessions_needs_bars_as_well_as_a_listing() -> None:
    bars = {"2026-08-17", "2026-08-18", "2026-08-22"}      # Mon, Tue, Saturday
    got = osi.scoreable_sessions(chain_sessions=set(), bar_sessions=bars)
    assert got == ["2026-08-17", "2026-08-18"]


# ---------------------------------------------------------------------------
# Where the volatility number comes from
# ---------------------------------------------------------------------------

def _chain_db(rows: list[tuple[float, float | None, float | None]]):
    """(strike_distance_pct, call_iv, put_iv) for one session.

    strike_distance_pct is an UNSIGNED FRACTION, the way the archive
    stores it - 0.01 is one percent, not one hundred.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE intraday_chain (
        quote_date TEXT, expire_date TEXT, dte INT, underlying REAL,
        strike REAL, strike_distance_pct REAL,
        call_bid REAL, call_ask REAL, call_iv REAL, call_delta REAL,
        call_gamma REAL, call_vega REAL,
        put_bid REAL, put_ask REAL, put_iv REAL, put_delta REAL,
        put_gamma REAL, put_vega REAL)""")
    for distance, call_iv, put_iv in rows:
        conn.execute(
            "INSERT INTO intraday_chain (quote_date, dte, strike_distance_pct, "
            "call_iv, put_iv) VALUES ('2015-06-10', 0, ?, ?, ?)",
            (distance, call_iv, put_iv))
    return conn


def test_the_end_of_day_archive_is_never_used_as_an_iv_source() -> None:
    """eod_chain 0DTE rows are snapshots AT EXPIRY. On 2010-09-03, with VIX
    at 21.3, its at-the-money row reads 0.019. No band of that table is
    trustworthy, so it is not consulted at all."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE eod_chain (quote_date TEXT, dte INT, "
                 "strike_distance_pct REAL, call_iv REAL, put_iv REAL)")
    conn.execute("INSERT INTO eod_chain VALUES ('2015-06-10', 0, 0.001, 0.21, 0.21)")
    assert osi.measured_session_iv(conn, "2015-06-10") is None


def test_an_intraday_capture_is_a_real_measurement() -> None:
    """Captured mid-session, the contract still has time value."""
    conn = _chain_db([(0.001, 0.104, 0.106), (0.008, 0.11, 0.11)])
    assert osi.measured_session_iv(conn, "2015-06-10") is not None


def test_distance_is_read_as_a_fraction_not_a_percent() -> None:
    """0.02 means 2%, so a 2%-away strike is outside the 1% band. Reading
    it as a percent made the filter <= 300%, i.e. no filter, and dragged
    the whole volatility smile into the median."""
    conn = _chain_db([(0.001, 0.10, 0.10), (0.02, 0.90, 0.90)])
    assert osi.measured_session_iv(conn, "2015-06-10") == 0.10


def test_a_measured_chain_iv_is_labelled_measured() -> None:
    conn = _chain_db([(0.001, 0.21, 0.21), (0.008, 0.21, 0.21)])
    got = osi.session_inputs("2015-06-10", conn)
    assert got.vol == 0.21
    assert got.provenance == "chain"
    assert got.is_measured


def test_falls_back_to_the_vix_proxy_and_says_so(monkeypatch) -> None:
    monkeypatch.setattr(osi, "_vix_by_session", lambda *a, **k: {"2026-08-14": 0.1425})
    got = osi.session_inputs("2026-08-14", _chain_db([]))
    assert got.vol == 0.1425
    assert got.provenance == "vix_proxy"
    assert not got.is_measured


def test_an_absurd_volatility_is_refused_rather_than_used(monkeypatch) -> None:
    """Every IV on the day is degenerate - fall through, do not use it."""
    monkeypatch.setattr(osi, "_vix_by_session", lambda *a, **k: {"2015-06-10": 0.19})
    conn = _chain_db([(0.000, 0.001, 0.002), (0.008, 0.004, None)])
    got = osi.session_inputs("2015-06-10", conn)
    assert got.provenance == "vix_proxy"
    assert got.vol == 0.19


def test_no_source_at_all_returns_none_rather_than_inventing_one(monkeypatch) -> None:
    monkeypatch.setattr(osi, "_vix_by_session", lambda *a, **k: {})
    assert osi.session_inputs("1998-04-04", _chain_db([])) is None


def test_far_from_the_money_strikes_do_not_set_the_session_iv() -> None:
    """A 6%-away wing carries a very different vol and is not the level."""
    conn = _chain_db([(0.001, 0.20, 0.20), (0.06, 0.90, 0.95)])
    assert osi.measured_session_iv(conn, "2015-06-10") == 0.20


# ---------------------------------------------------------------------------
# Capturing today's chain
# ---------------------------------------------------------------------------

def _contract(strike, side, iv, bid=1.0, ask=1.1):
    return {"strike": strike, "option_type": side, "bid": bid, "ask": ask,
            "greeks": {"mid_iv": iv, "delta": 0.5, "gamma": 0.01, "vega": 0.02}}


def test_a_tradier_chain_folds_into_one_row_per_strike() -> None:
    chain = [_contract(500, "call", 0.14), _contract(500, "put", 0.15),
             _contract(501, "call", 0.14), _contract(501, "put", 0.15)]
    rows = cap.rows_from_chain(chain, quote_date="2026-08-20",
                               expiration="2026-08-20", spot=500.0)
    assert len(rows) == 2
    assert rows[0][0] == "2026-08-20"
    assert rows[0][2] == 0                      # dte
    assert rows[0][8] == 0.14                   # call_iv
    assert rows[0][14] == 0.15                  # put_iv


def test_far_out_of_the_money_strikes_are_not_stored() -> None:
    chain = [_contract(500, "call", 0.14), _contract(500, "put", 0.15),
             _contract(700, "call", 0.30), _contract(700, "put", 0.31)]
    rows = cap.rows_from_chain(chain, quote_date="2026-08-20",
                               expiration="2026-08-20", spot=500.0)
    assert [r[4] for r in rows] == [500]


def test_a_strike_with_no_iv_is_dropped() -> None:
    """implied_vol_for_session is the one query that matters; a row that
    cannot answer it is not worth storing."""
    chain = [_contract(500, "call", None), _contract(500, "put", None)]
    assert cap.rows_from_chain(chain, quote_date="2026-08-20",
                               expiration="2026-08-20", spot=500.0) == []


def test_capturing_twice_does_not_double_the_day() -> None:
    """A scheduled job will run twice eventually."""
    conn = sqlite3.connect(":memory:")
    chain = [_contract(500, "call", 0.14), _contract(500, "put", 0.15)]
    rows = cap.rows_from_chain(chain, quote_date="2026-08-20",
                               expiration="2026-08-20", spot=500.0)
    cap.store(rows, "2026-08-20", conn)
    cap.store(rows, "2026-08-20", conn)
    assert conn.execute(
        f"SELECT COUNT(*) FROM {cap.TABLE}").fetchone()[0] == len(rows)


def test_a_stored_capture_is_readable_as_a_measured_iv() -> None:
    """The whole point: today's capture becomes a measured session."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    chain = [_contract(500, "call", 0.14), _contract(500, "put", 0.15)]
    cap.store(cap.rows_from_chain(chain, quote_date="2026-08-20",
                                  expiration="2026-08-20", spot=500.0),
              "2026-08-20", conn)
    got = osi.session_inputs("2026-08-20", conn)
    assert got.provenance == "chain"
    assert got.is_measured
    # It blends the two sides of the strike: (0.14 + 0.15) / 2.
    assert round(got.vol, 6) == 0.145


def test_capture_stores_distance_the_way_the_reader_expects() -> None:
    """Written as a percent, every distance filter downstream breaks."""
    chain = [_contract(505, "call", 0.14), _contract(505, "put", 0.15)]
    rows = cap.rows_from_chain(chain, quote_date="2026-08-20",
                               expiration="2026-08-20", spot=500.0)
    assert round(rows[0][5], 4) == 0.01          # 1%, as a fraction
