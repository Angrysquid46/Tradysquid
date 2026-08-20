"""Store today's SPY 0DTE option chain, so tomorrow it is history.

The option archive is a one-time import that stops at 2023-12-29 and has
no updater. Every backtest therefore prices off either that stale window
or a VIX proxy. Nothing was ever going to fix that retroactively - no
provider sells intraday SPY option history at a price this project would
pay, and Tradier only serves the CURRENT chain.

What is fixable is the future. Tradier's chain endpoint returns real bid,
ask, IV and greeks for every strike, and SPY lists a same-day expiry every
weekday. Captured once a day, that is a real measured 0DTE record growing
by one session per day, in the same `eod_chain` table the backtest already
reads - so a session captured today is scored exactly like a session from
2015, with `provenance = chain` rather than `vix_proxy`.

Deliberately narrow:

- **SPY only, same-day expiry only.** The whole system is SPY 0DTE. Storing
  the full multi-expiry chain would be tens of thousands of rows a day for
  contracts nothing here trades.
- **Near the money only** (`STRIKE_WINDOW_PCT`). Contract selection targets
  0.50 delta and rejects anything over $5.00, so deep wings are never
  bought and would only pad the table.
- **Idempotent.** Re-running replaces that day's rows instead of doubling
  them, because a scheduled job WILL run twice eventually.
- **Its own table, `intraday_chain`.** These rows must NOT go into
  `eod_chain`. That table is an end-of-day snapshot, and for a same-day
  expiry the end of day IS expiry - its 0DTE implied vols are solved on
  contracts with no life left and are unusable (see
  option_session_inputs.measured_session_iv). A capture taken at 11:00
  with four hours of time value remaining is a genuinely different
  measurement, and mixing the two would bury that difference.
- **Read-only against the broker.** This fetches quotes. It places nothing.
"""

from __future__ import annotations

import sqlite3
from datetime import date
from typing import Any, Iterable

import spy_option_data as od

SYMBOL = "SPY"
# Strikes within this percent of spot. 0.50-delta 0DTE contracts sit within
# a fraction of a percent; 5% is generous enough to survive a volatile day
# without storing wings nothing would buy.
STRIKE_WINDOW_PCT = 5.0


def _number(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None


def rows_from_chain(chain: Iterable[dict[str, Any]], *, quote_date: str,
                    expiration: str, spot: float) -> list[tuple]:
    """Fold Tradier's per-contract chain into eod_chain's per-strike shape.

    Tradier returns one record per contract - a call and a put per strike.
    `eod_chain` is one row per strike with call_* and put_* columns, which
    is what every existing query expects.
    """
    by_strike: dict[float, dict[str, Any]] = {}
    for contract in chain:
        strike = _number(contract.get("strike"))
        if strike is None or not spot:
            continue
        if abs(strike - spot) / spot * 100.0 > STRIKE_WINDOW_PCT:  # noqa: E501
            continue
        side = str(contract.get("option_type") or "").lower()
        if side not in ("call", "put"):
            continue
        greeks = contract.get("greeks") or {}
        slot = by_strike.setdefault(strike, {})
        slot[f"{side}_bid"] = _number(contract.get("bid"))
        slot[f"{side}_ask"] = _number(contract.get("ask"))
        slot[f"{side}_iv"] = _number(greeks.get("mid_iv") or greeks.get("smv_vol"))
        slot[f"{side}_delta"] = _number(greeks.get("delta"))
        slot[f"{side}_gamma"] = _number(greeks.get("gamma"))
        slot[f"{side}_vega"] = _number(greeks.get("vega"))

    out = []
    for strike in sorted(by_strike):
        slot = by_strike[strike]
        # A strike with no IV on either side cannot serve the one query
        # that matters (implied_vol_for_session), so it is not worth a row.
        if slot.get("call_iv") is None and slot.get("put_iv") is None:
            continue
        out.append((
            quote_date, expiration, 0, spot, strike,
            abs(strike - spot) / spot,   # unsigned FRACTION, as the archive stores it
            slot.get("call_bid"), slot.get("call_ask"), slot.get("call_iv"),
            slot.get("call_delta"), slot.get("call_gamma"), slot.get("call_vega"),
            slot.get("put_bid"), slot.get("put_ask"), slot.get("put_iv"),
            slot.get("put_delta"), slot.get("put_gamma"), slot.get("put_vega"),
        ))
    return out


TABLE = "intraday_chain"


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.execute(f"""CREATE TABLE IF NOT EXISTS {TABLE} (
        quote_date TEXT, expire_date TEXT, dte INT, underlying REAL,
        strike REAL, strike_distance_pct REAL,
        call_bid REAL, call_ask REAL, call_iv REAL, call_delta REAL,
        call_gamma REAL, call_vega REAL,
        put_bid REAL, put_ask REAL, put_iv REAL, put_delta REAL,
        put_gamma REAL, put_vega REAL,
        captured_at TEXT)""")
    conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_date "
                 f"ON {TABLE} (quote_date, dte)")


def _columns(conn: sqlite3.Connection) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({TABLE})")]


def store(rows: list[tuple], quote_date: str, conn: sqlite3.Connection | None = None) -> int:
    """Replace this quote_date's 0DTE rows with `rows`. Idempotent."""
    owned = conn is None
    conn = conn or od.connect()
    try:
        _ensure_table(conn)
        columns = _columns(conn)
        wanted = ["quote_date", "expire_date", "dte", "underlying", "strike",
                  "strike_distance_pct",
                  "call_bid", "call_ask", "call_iv", "call_delta", "call_gamma",
                  "call_vega",
                  "put_bid", "put_ask", "put_iv", "put_delta", "put_gamma",
                  "put_vega"]
        missing = [c for c in wanted if c not in columns]
        if missing:
            raise RuntimeError(f"intraday_chain is missing columns: {missing}")
        conn.execute("DELETE FROM intraday_chain WHERE quote_date = ? AND dte = 0",
                     (quote_date,))
        conn.executemany(
            f"INSERT INTO intraday_chain ({', '.join(wanted)}) "
            f"VALUES ({', '.join('?' * len(wanted))})", rows)
        conn.commit()
        return len(rows)
    finally:
        if owned:
            conn.close()


def capture(session: str | None = None) -> dict[str, Any]:
    """Fetch and store today's 0DTE chain. Returns a small receipt."""
    import spy_scanner as ss

    session = session or date.today().isoformat()
    quote = ss.get_quote(SYMBOL) or {}
    spot = _number(quote.get("last") or quote.get("close"))
    if not spot:
        return {"stored": 0, "session": session, "detail": "no SPY quote"}

    chain = ss.get_chain(SYMBOL, session)
    if not chain:
        return {"stored": 0, "session": session,
                "detail": "no same-day expiry listed"}

    rows = rows_from_chain(chain, quote_date=session, expiration=session, spot=spot)
    stored = store(rows, session)
    return {"stored": stored, "session": session, "spot": spot,
            "detail": f"stored {stored} near-the-money strikes"}


def capture_job(conn: sqlite3.Connection) -> str:
    """Scheduler entry point. `conn` is the engine's own db, not ours."""
    receipt = capture()
    return f"0DTE chain {receipt['session']}: {receipt['detail']}"


if __name__ == "__main__":
    print(capture())
