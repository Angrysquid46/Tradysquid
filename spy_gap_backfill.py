"""Resumable backfill for the 2021-2026 minute-data hole.

The research store jumps from 2021-05-06 to 2026-07-17. That gap cannot be
closed by the providers already wired in - Tradier caps 1-minute history
around 20 days, Yahoo at 30, Robinhood returns synthetic flat bars beyond
its retention, and Finnhub's candle endpoint is premium-only. It needs a
provider that actually sells historical intraday.

Those providers meter by request. Alpha Vantage's free tier allows a
handful of calls per day against a gap of roughly 62 months, so a single
run cannot finish the job and a naive loop would spend its quota and then
start from the beginning again tomorrow. Everything here is built around
that constraint:

* **Resumable.** Completed months are recorded, so each run continues
  where the last stopped rather than repeating work.
* **Newest-first.** The months closest to today describe the regime the
  system actually trades, so they land on day one and the 2021 tail
  arrives last. A backfill that dies halfway has still delivered the part
  that matters.
* **Rate limits are a normal outcome, not a failure.** Hitting the wall
  ends the run cleanly and schedules the rest for the next one.
* **Nothing is written until it is checked.** The store already holds
  2021-01 through 2021-05, so a provider's data for those months can be
  compared against bars we already trust before any new row is committed.
  Robinhood returned 2,340 consecutive synthetic bars for a range past its
  retention rather than an error; that must never reach the store.

The provider adapter is deliberately one function. Swapping Alpha Vantage
for Polygon or a paid tier changes `fetch_month` and nothing else.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any, Callable, Iterable

import spy_intraday_features as sif
import spy_research_data as srd

STATE_PATH = Path("state/gap-backfill.json")

# The hole, inclusive of partial months at each end.
GAP_FIRST_MONTH = "2021-05"
GAP_LAST_MONTH = "2026-07"

# Months present in BOTH the existing store and any provider with real
# history - used to prove a provider is returning genuine data.
OVERLAP_MONTHS = ("2021-03", "2021-04")


class RateLimited(Exception):
    """The provider refused further calls this period. Not an error."""


class SuspectData(Exception):
    """The provider answered, but the answer does not look like real bars."""


def months_between(first: str, last: str) -> list[str]:
    out: list[str] = []
    year, month = int(first[:4]), int(first[5:7])
    end_year, end_month = int(last[:4]), int(last[5:7])
    while (year, month) <= (end_year, end_month):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def read_state() -> dict[str, Any]:
    if not STATE_PATH.exists():
        return {"done": [], "failed": {}, "verified_provider": None}
    try:
        loaded = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"done": [], "failed": {}, "verified_provider": None}
    if not isinstance(loaded, dict):
        return {"done": [], "failed": {}, "verified_provider": None}
    loaded.setdefault("done", [])
    loaded.setdefault("failed", {})
    loaded.setdefault("verified_provider", None)
    return loaded


def write_state(state: dict[str, Any]) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, sort_keys=True),
                          encoding="utf-8")


def pending_months(state: dict[str, Any]) -> list[str]:
    """Months still needed, newest first.

    Newest-first is the point: a run that stops early has still delivered
    the months closest to the regime being traded.
    """
    done = set(state.get("done") or [])
    every = months_between(GAP_FIRST_MONTH, GAP_LAST_MONTH)
    return [m for m in reversed(every) if m not in done]


# ---------------------------------------------------------------------------
# Provider adapter
# ---------------------------------------------------------------------------

def fetch_month_alphavantage(month: str) -> list[dict[str, Any]]:
    """One calendar month of 1-minute SPY bars.

    Raises RateLimited when the quota is spent so the caller can stop
    cleanly rather than treating it as a data problem.
    """
    import requests

    key = os.environ.get("ALPHAVANTAGE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("ALPHAVANTAGE_API_KEY is not configured")

    response = requests.get(
        "https://www.alphavantage.co/query",
        params={
            "function": "TIME_SERIES_INTRADAY", "symbol": "SPY",
            "interval": "1min", "month": month, "outputsize": "full",
            "adjusted": "false", "extended_hours": "false", "apikey": key,
        },
        timeout=90,
    )
    response.raise_for_status()
    payload = response.json()

    # Rate limits and errors arrive as HTTP 200 with a prose field.
    for field_name in ("Note", "Information", "Error Message"):
        text = payload.get(field_name)
        if not text:
            continue
        lowered = str(text).lower()
        if "limit" in lowered or "thank you" in lowered or "premium" in lowered:
            raise RateLimited(str(text)[:200])
        raise RuntimeError(str(text)[:200])

    series = payload.get("Time Series (1min)") or {}
    bars: list[dict[str, Any]] = []
    for stamp, values in series.items():
        try:
            bars.append({
                "bar_time": stamp.replace(" ", "T")[:19],
                "open": float(values["1. open"]), "high": float(values["2. high"]),
                "low": float(values["3. low"]), "close": float(values["4. close"]),
                "volume": float(values["5. volume"]),
            })
        except (KeyError, TypeError, ValueError):
            continue
    bars.sort(key=lambda b: b["bar_time"])
    return bars


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def looks_synthetic(bars: Iterable[dict[str, Any]]) -> bool:
    """Flat prices or dead volume - the shape Robinhood returned for ranges
    past its retention, 2,340 consecutive identical bars with no error."""
    bars = list(bars)
    if len(bars) < 30:
        return False
    closes = {round(b["close"], 4) for b in bars}
    if len(closes) <= 2:
        return True
    if all((b.get("volume") or 0) <= 0 for b in bars):
        return True
    return False


def verify_against_store(conn, month: str, bars: list[dict[str, Any]],
                         tolerance_pct: float = 0.5) -> dict[str, Any]:
    """Compare a provider's month against bars already in the store.

    Run before anything is written. A provider that disagrees with data we
    already trust is not going to be trusted for the months we cannot
    check.
    """
    if not bars:
        raise SuspectData(f"{month}: provider returned no bars")
    if looks_synthetic(bars):
        raise SuspectData(f"{month}: bars look synthetic (flat price or no volume)")

    theirs = {b["bar_time"]: b for b in bars}
    rows = conn.execute(
        "SELECT bar_time, close FROM minute_bars WHERE ticker='SPY' "
        "AND bar_time >= ? AND bar_time < ? AND regular_session=1",
        (f"{month}-01T", f"{month}-32T"),
    ).fetchall()
    compared = 0
    worst = 0.0
    for row in rows:
        mine = theirs.get(row["bar_time"])
        if not mine or not row["close"]:
            continue
        diff = abs(mine["close"] - row["close"]) / row["close"] * 100.0
        worst = max(worst, diff)
        compared += 1
    if compared < 100:
        raise SuspectData(
            f"{month}: only {compared} overlapping bars, too few to verify")
    if worst > tolerance_pct:
        raise SuspectData(
            f"{month}: disagrees with the existing store by {worst:.2f}% "
            f"(limit {tolerance_pct}%) across {compared} bars")
    return {"month": month, "compared": compared, "worst_diff_pct": worst}


# ---------------------------------------------------------------------------
# Backfill
# ---------------------------------------------------------------------------

@dataclass
class BackfillResult:
    months_done: list[str] = field(default_factory=list)
    bars_written: int = 0
    stopped_because: str = ""
    remaining: int = 0
    verification: dict[str, Any] | None = None


def _write_bars(conn, bars: list[dict[str, Any]]) -> int:
    rows = [
        ("SPY", b["bar_time"], b["open"], b["high"], b["low"], b["close"],
         b.get("volume"), None, None, srd._is_regular_session(b["bar_time"]))
        for b in bars
    ]
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO minute_bars (ticker, bar_time, open, high, low, "
        "close, volume, bar_count, average, regular_session) VALUES (?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    return conn.total_changes - before


def backfill(
    conn,
    fetch_month: Callable[[str], list[dict[str, Any]]] = fetch_month_alphavantage,
    *,
    max_months: int = 25,
    provider: str = "alphavantage",
    build_features: bool = True,
) -> BackfillResult:
    """Pull as many missing months as the quota allows, newest first."""
    state = read_state()
    result = BackfillResult()

    # A provider proves itself against months we already have before it is
    # allowed to write months we cannot check.
    if state.get("verified_provider") != provider:
        for month in OVERLAP_MONTHS:
            try:
                check = verify_against_store(conn, month, fetch_month(month))
            except RateLimited as exc:
                result.stopped_because = f"rate limited during verification: {exc}"
                result.remaining = len(pending_months(state))
                return result
            except SuspectData as exc:
                # The provider failed the only check we can actually make.
                # Refusing to write anything is the entire point.
                result.stopped_because = f"provider rejected: {exc}"
                result.remaining = len(pending_months(state))
                return result
            except Exception as exc:
                result.stopped_because = f"verification failed: {exc}"
                result.remaining = len(pending_months(state))
                return result
            result.verification = check
            state["verified_provider"] = provider
            write_state(state)
            break

    written_sessions: set[str] = set()
    for month in pending_months(state)[:max_months]:
        try:
            bars = fetch_month(month)
        except RateLimited as exc:
            result.stopped_because = f"rate limited: {exc}"
            break
        except Exception as exc:  # provider hiccup on one month only
            state["failed"][month] = str(exc)[:200]
            write_state(state)
            continue

        if not bars or looks_synthetic(bars):
            state["failed"][month] = "empty or synthetic response"
            write_state(state)
            continue

        result.bars_written += _write_bars(conn, bars)
        written_sessions.update(b["bar_time"][:10] for b in bars)
        state["done"] = sorted(set(state["done"]) | {month})
        state["failed"].pop(month, None)
        write_state(state)
        result.months_done.append(month)

    if build_features and written_sessions:
        sif.build_features(conn, "SPY", sessions=sorted(written_sessions),
                           progress_every=0)

    result.remaining = len(pending_months(read_state()))
    if not result.stopped_because:
        result.stopped_because = "quota for this run spent" if result.months_done \
            else "nothing left to do"
    return result


def main() -> None:
    conn = sif.connect()
    try:
        outcome = backfill(conn)
        print(json.dumps({
            "months_done": outcome.months_done,
            "bars_written": outcome.bars_written,
            "months_remaining": outcome.remaining,
            "stopped_because": outcome.stopped_because,
            "verification": outcome.verification,
        }, indent=2, default=str))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
