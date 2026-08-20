"""Which sessions can be scored, and at what volatility - without the
dead 2023 chain table being the only answer.

The option backtest needs exactly two facts per session:

1. **Did a same-day expiry exist?** This used to be answered only by
   looking for rows in `eod_chain`, which stops at 2023-12-29. So every
   session after that was silently unscoreable, including every session
   from the era these strategies actually trade in.
2. **What was implied volatility?** Same table, same cliff.

Both now have a fallback, and every answer carries its PROVENANCE, because
a modelled input and a measured one are not the same evidence and must not
be reported as if they were.

## The listing rule

SPY same-day expiries are a calendar fact, not a lookup:

- before 2022-04-25: Mon/Wed/Fri only, and not on every one of them -
  `eod_chain` is the authority and there is no substitute
- 2022-04-25: Tuesday and Thursday added
- 2022-05-04 onward: every weekday

So after 2022-05-04 the table is not needed to know a 0DTE existed. Before
it, the table is the only honest source.

## The volatility input

Best first:

- `chain` - real IV from an INTRADAY capture (`intraday_chain`, written by
  `capture_0dte_chain`). Only exists from 2026-08-20 forward, and grows by
  one session a day.
- `vix_proxy` - `Benchmark_VIX_Close` / 100 from `daily_indicators`,
  covering 1993 to the present. This is what the entire historical archive
  now uses.

**`eod_chain` is not an IV source.** It is an end-of-day snapshot, so its
0DTE rows are snapshots AT EXPIRY and their solved IVs are degenerate -
see `measured_session_iv`. Using it was not a small error: it priced 480
of 988 sessions at under 3% volatility.

**`SPY_9D_IV` is deliberately not used.** It looks like the right column
and is not: measured over 654 sessions since 2024 it correlates +0.005
with VIX and moves 43.8% day over day against VIX's 5.7%. It printed 9.83
and 31.11 on consecutive days while VIX sat at 14.3 and 14.6. It is noise.
`SPY_9D_IV_Proxy` is the opposite problem - it correlates +1.000 with VIX
because it IS VIX rescaled by 0.95, so it adds nothing over using VIX
directly and hides that fact behind a name that implies a measurement.

**A VIX proxy is a 30-day number standing in for a same-day one.** 0DTE
implied vol is routinely far from 30-day, especially into an event. Every
result built on `vix_proxy` is weaker evidence than one built on `chain`,
which is why the provenance travels with the number instead of being
mentioned once in a docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import Any, Literal

Provenance = Literal["chain", "vix_proxy"]

# SPY added Tuesday/Thursday same-day expiries on this date...
ZERO_DTE_TUE_THU_FROM = "2022-04-25"
# ...and completed the weekday set here.
ZERO_DTE_DAILY_FROM = "2022-05-04"

MIN_SANE_VOL = 0.03      # 3% - below this the model prices nothing
MAX_SANE_VOL = 3.00      # 300% - above this the input is broken, not the market


@dataclass(frozen=True)
class SessionInputs:
    session: str
    vol: float
    provenance: Provenance

    @property
    def is_measured(self) -> bool:
        return self.provenance == "chain"


def _weekday(session: str) -> int:
    return date.fromisoformat(session).weekday()


def zero_dte_listed(session: str, *, chain_sessions: set[str] | None = None) -> bool:
    """Did SPY have a same-day expiry on this session?

    After the calendar cutovers this is knowable without any data. Before
    them it is not, and `chain_sessions` (the real listing record) is the
    only honest answer - guessing Mon/Wed/Fri would invent listings that
    did not exist on holidays and half the weeks of 2010.
    """
    if session >= ZERO_DTE_DAILY_FROM:
        return _weekday(session) < 5
    if session >= ZERO_DTE_TUE_THU_FROM:
        return _weekday(session) in (0, 1, 2, 3, 4)
    return bool(chain_sessions and session in chain_sessions)


@lru_cache(maxsize=1)
def _vix_by_session(db_path: str | None = None) -> dict[str, float]:
    """Daily VIX close, as a decimal volatility."""
    import spy_intraday_features as sif

    conn = sif.connect()
    try:
        rows = conn.execute(
            "SELECT bar_date, value FROM daily_indicators "
            "WHERE column_name = 'Benchmark_VIX_Close' AND value IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()
    return {row[0]: float(row[1]) / 100.0 for row in rows}


def measured_session_iv(conn: Any, session: str) -> float | None:
    """Near-the-money IV from an INTRADAY capture, or None.

    Deliberately does not touch `eod_chain`. That table is an end-of-day
    snapshot, so for a same-day expiry it is a snapshot AT EXPIRY, and an
    IV solved on a contract with no life left is not a volatility. It shows
    up plainly in the data: on 2010-09-03, with VIX at 21.3, the exactly-
    at-the-money 0DTE row reads 0.019 while strikes a dollar away read
    0.083, 0.155 and 0.223.

    There is no band of that table that rescues it. Measured against VIX
    across 61 sampled sessions, the median near-the-money 0DTE IV comes out
    at 0.44x VIX; widen to the whole +/-5% chain and it is 1.30x. Every
    choice in between is available, and the choice alone moves the backtest
    from "all 15 strategies profitable" to "all 15 losing". That is a knob,
    not a measurement, and picking a value would be inventing the number
    that decides everything.

    `intraday_chain` has no such problem: `capture_0dte_chain` records the
    live Tradier chain DURING the session, with hours of time value left
    and a real `mid_iv`. Those sessions get a genuinely measured IV.
    Everything else falls back to the VIX proxy, labelled as such.
    """
    try:
        rows = conn.execute(
            """
            SELECT call_iv, put_iv FROM intraday_chain
            WHERE quote_date = ? AND dte = 0
              AND abs(strike_distance_pct) <= 0.01
              AND (call_iv IS NOT NULL OR put_iv IS NOT NULL)
            """,
            (session,),
        ).fetchall()
    except Exception:
        return None          # table absent on a checkout that never captured
    values: list[float] = []
    for row in rows:
        pair = (row["call_iv"], row["put_iv"]) if hasattr(row, "keys") else row
        for value in pair:
            if value is None:
                continue
            number = float(value)
            if MIN_SANE_VOL <= number <= MAX_SANE_VOL:
                values.append(number)
    if not values:
        return None
    values.sort()
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def session_inputs(session: str, option_conn: Any = None) -> SessionInputs | None:
    """Volatility for one session, best source first, provenance attached.

    Returns None when neither source has the day at all - the honest
    answer, rather than a made-up number that would look identical to a
    measured one in the output.
    """
    if option_conn is not None:
        measured = measured_session_iv(option_conn, session)
        if measured is not None:
            return SessionInputs(session, measured, "chain")

    proxy = _vix_by_session().get(session)
    if proxy and MIN_SANE_VOL <= proxy <= MAX_SANE_VOL:
        return SessionInputs(session, proxy, "vix_proxy")
    return None


def scoreable_sessions(chain_sessions: set[str], bar_sessions: set[str]) -> list[str]:
    """Every session that has bars AND a same-day expiry, newest last."""
    return sorted(s for s in bar_sessions if zero_dte_listed(s, chain_sessions=chain_sessions))
