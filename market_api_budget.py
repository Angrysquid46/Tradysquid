"""Phase 7: shared API budget and priority scheme (Master Spec Section 8).

Every Tradier call in this codebase already funnels through
market_data.tradier_get() - the "one shared factual market service"
Section 8 asks for structurally already exists. This module adds the
missing pieces: capturing the real rate-limit telemetry Tradier already
sends on every response, the named 8-tier priority scheme, and a gate
that uses both.

Verified live against the real API (not assumed): /markets/quotes then
/markets/options/chains back to back returned X-Ratelimit-Allowed: 120,
X-Ratelimit-Used incrementing 1->2 across both calls with the same
X-Ratelimit-Expiry - the spec's "provisional ~120/min" is exactly right,
and quotes/chain share one combined bucket, not separate ones.
"""

from __future__ import annotations

import sqlite3
import time
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Section 8's priority order, exactly as listed. Only 4 and 5 have a
# real caller today (market_data_collector.py's jobs) - 1-3 have no
# caller until a bot exists (Phase 11+), but the ranking has to exist
# now so that phase has something to plug into instead of inventing it
# under pressure later. 6-8 map to the existing research/reporting jobs.
PRIORITY_OPEN_POSITION_SAFETY = 1
PRIORITY_EXIT_CRITICAL_DATA = 2
PRIORITY_ENTRY_CRITICAL_DATA = 3
PRIORITY_SHARED_SPY_OBSERVATIONS = 4
PRIORITY_SHARED_OPTIONS_COLLECTION = 5
PRIORITY_SECONDARY_CONTEXT = 6
PRIORITY_NONESSENTIAL_RESEARCH = 7
PRIORITY_RIVALRY_PRESENTATION = 8

# Never-blocked tiers: matches this codebase's existing principle that an
# open-position exit/safety path is never debounced or delayed by a
# display/research concern (see local_information_engine.py's card-push
# pacing comments for the same reasoning applied elsewhere).
_ALWAYS_ALLOWED = {
    PRIORITY_OPEN_POSITION_SAFETY,
    PRIORITY_EXIT_CRITICAL_DATA,
    PRIORITY_ENTRY_CRITICAL_DATA,
}

# Minimum fraction of the allowed budget that must remain for a tier to
# proceed. Policy, not measurement: today's real usage is roughly 2
# calls/minute against a 120/min budget, nowhere near either floor, so
# there is no real contention data to derive these from yet. Starting
# defaults, meant to be retuned once real contention is observed - same
# basis as Phase 5's daily_data_manifest grade thresholds.
_RESERVE_FRACTION = {
    PRIORITY_SHARED_SPY_OBSERVATIONS: 0.20,
    PRIORITY_SHARED_OPTIONS_COLLECTION: 0.20,
    PRIORITY_SECONDARY_CONTEXT: 0.40,
    PRIORITY_NONESSENTIAL_RESEARCH: 0.40,
    PRIORITY_RIVALRY_PRESENTATION: 0.40,
}

DB_PATH = Path(os.environ.get(
    "TRADYSQUID_API_BUDGET_DB",
    str(Path(__file__).resolve().parent / "state" / "market-api-budget.db"),
))


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA busy_timeout=10000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("CREATE TABLE IF NOT EXISTS quota (id INTEGER PRIMARY KEY CHECK(id=1), allowed INTEGER NOT NULL, used INTEGER NOT NULL, available INTEGER NOT NULL, expiry INTEGER NOT NULL, reservations INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL)")
    return db


@contextmanager
def _database():
    db = _connect()
    try:
        yield db
    finally:
        db.close()


def record_response_headers(response: Any) -> dict[str, int] | None:
    """Parse X-Ratelimit-* from a real requests.Response and update the
    shared state. Silently no-ops (returns None) if the headers aren't
    present - not every provider/endpoint is guaranteed to send them, and
    a missing header is not itself an error worth raising over."""
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        allowed = int(headers["X-Ratelimit-Allowed"])
        used = int(headers["X-Ratelimit-Used"])
        available = int(headers["X-Ratelimit-Available"])
        expiry = int(headers["X-Ratelimit-Expiry"])
    except (KeyError, TypeError, ValueError):
        return None
    state = {
        "allowed": allowed, "used": used,
        "available": available, "expiry": expiry,
    }
    with _database() as db:
        db.execute("BEGIN IMMEDIATE")
        prior = db.execute("SELECT expiry, reservations FROM quota WHERE id=1").fetchone()
        reservations = max(0, int(prior["reservations"]) - 1) if prior and int(prior["expiry"]) == expiry else 0
        db.execute(
            "INSERT INTO quota(id,allowed,used,available,expiry,reservations,updated_at) VALUES(1,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET allowed=excluded.allowed,used=excluded.used,available=excluded.available,expiry=excluded.expiry,reservations=excluded.reservations,updated_at=excluded.updated_at",
            (allowed, used, available, expiry, reservations, time.time()),
        )
        db.commit()
    return state


def current_state() -> dict[str, int] | None:
    with _database() as db:
        row = db.execute("SELECT allowed,used,available,expiry FROM quota WHERE id=1").fetchone()
    return dict(row) if row else None


def request_allowed(priority: int) -> bool:
    """Whether a call at this priority may proceed right now.

    Fails open (True) when no telemetry has been recorded yet - blocking
    every caller before the first real response arrives would be worse
    than the rare case where an early burst goes ungated for one cycle.
    """
    with _database() as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM quota WHERE id=1").fetchone()
        if row is None:
            # Conservative bootstrapping against the verified combined limit.
            now = int(time.time())
            db.execute("INSERT INTO quota VALUES(1,120,0,120,?,0,?)", (now + 60, time.time()))
            row = db.execute("SELECT * FROM quota WHERE id=1").fetchone()
        expiry = int(row["expiry"])
        now_value = int(time.time())
        reservations = int(row["reservations"])
        available = int(row["available"])
        if expiry < 10_000_000_000 and expiry <= now_value:
            reservations, available, expiry = 0, int(row["allowed"]), now_value + 60
            db.execute("UPDATE quota SET used=0,available=?,expiry=?,reservations=0,updated_at=? WHERE id=1", (available, expiry, time.time()))
        effective = max(0, available - reservations)
        reserve = 0 if priority in _ALWAYS_ALLOWED else int(int(row["allowed"]) * _RESERVE_FRACTION.get(priority, 0.0))
        permitted = effective > reserve
        if permitted:
            db.execute("UPDATE quota SET reservations=reservations+1,updated_at=? WHERE id=1", (time.time(),))
        db.commit()
        return permitted


def release_reservation() -> None:
    """Release an in-flight reservation when no usable response arrived."""
    with _database() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "UPDATE quota SET reservations=MAX(0,reservations-1),updated_at=? WHERE id=1",
            (time.time(),),
        )
        db.commit()


def reset_for_test() -> None:
    for suffix in ("", "-shm", "-wal"):
        path = Path(str(DB_PATH) + suffix)
        try:
            path.unlink()
        except FileNotFoundError:
            pass
