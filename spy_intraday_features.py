"""Phase 2 of the SPY research build: per-minute market state.

Turns the 1.43M raw minute bars ingested in Phase 1 into the "GLOBAL SPY
MARKET MAP" the strategy specs require every strategy to have access to:
previous-day and previous-week levels, premarket range, the gap, opening
ranges at three definitions, session-anchored VWAP, ATR, time-of-day
normalised relative volume, multi-timeframe alignment, a ten-state
regime, and an evolving day-type classification.

## No lookahead - the rule this module exists to obey

Both `indicators instructions.txt` and the strategy spec state it
outright: do not look forward when testing. Every value written for bar
i is computed from bars[:i+1] plus information genuinely knowable before
the session opened (yesterday's levels, the prior 14 days' ATR, the
prior 20 sessions' volume profile). Nothing reads a later bar.

That is enforced two ways rather than asserted: the session builder is a
single forward pass that physically cannot see ahead, and a test
truncates a session mid-way and requires every overlapping value to be
identical to the full-session run. A backtest that quietly peeks is the
single easiest way to manufacture a beautiful, worthless edge, which the
source material warns about repeatedly.

## Relative volume, done honestly

Relative volume compares the session's cumulative volume so far against
what is normal *at that same minute of the session* - comparing 10:15's
cumulative volume against a whole-day average would make every morning
look quiet and every afternoon look busy. The baseline is built from a
trailing window of PRIOR sessions only, so it never contains the day it
is describing.
"""

from __future__ import annotations

import re
import sqlite3
import statistics
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Iterator, Sequence

import spy_research_data as srd

DB_PATH = srd.DB_PATH

SESSION_OPEN_MINUTES = 9 * 60 + 30
SESSION_CLOSE_MINUTES = 15 * 60 + 59
OPENING_RANGE_WINDOWS = (5, 15, 30)
ATR_PERIOD = 14
RVOL_BASELINE_SESSIONS = 20
VWAP_SLOPE_LOOKBACK = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS minute_features (
    ticker TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    session_date TEXT NOT NULL,
    minutes_since_open INTEGER,
    minutes_until_close INTEGER,
    time_bucket TEXT,

    open REAL, high REAL, low REAL, close REAL, volume REAL,

    prev_day_high REAL, prev_day_low REAL, prev_day_close REAL,
    prev_day_mid REAL, prev_day_range REAL,
    prev_week_high REAL, prev_week_low REAL, prev_week_close REAL,

    premarket_high REAL, premarket_low REAL, premarket_mid REAL, premarket_range REAL,
    gap_dollars REAL, gap_pct REAL, gap_atr REAL, gap_direction TEXT,

    session_open REAL, session_high REAL, session_low REAL, session_range REAL,
    close_vs_range_pct REAL,

    vwap REAL, vwap_slope REAL, vwap_distance REAL, vwap_distance_pct REAL,
    vwap_distance_atr REAL, above_vwap INTEGER, vwap_crosses INTEGER,

    atr_14 REAL, atr_pct REAL,
    cumulative_volume REAL, relative_volume REAL,

    or5_high REAL, or5_low REAL, or5_mid REAL, or5_width REAL,
    or5_width_atr REAL, or5_state TEXT, or5_break_minute INTEGER,
    or15_high REAL, or15_low REAL, or15_mid REAL, or15_width REAL,
    or15_width_atr REAL, or15_state TEXT, or15_break_minute INTEGER,
    or30_high REAL, or30_low REAL, or30_mid REAL, or30_width REAL,
    or30_width_atr REAL, or30_state TEXT, or30_break_minute INTEGER,

    trend_5m TEXT, trend_15m TEXT, trend_60m TEXT, trend_daily TEXT,
    alignment TEXT, alignment_score INTEGER,

    regime TEXT, day_type TEXT,

    PRIMARY KEY (ticker, bar_time)
);
CREATE INDEX IF NOT EXISTS minute_features_session
    ON minute_features(ticker, session_date);
CREATE INDEX IF NOT EXISTS minute_features_regime
    ON minute_features(ticker, regime);
"""

FEATURE_COLUMNS: tuple[str, ...] = (
    "minutes_since_open", "minutes_until_close", "time_bucket",
    "open", "high", "low", "close", "volume",
    "prev_day_high", "prev_day_low", "prev_day_close", "prev_day_mid", "prev_day_range",
    "prev_week_high", "prev_week_low", "prev_week_close",
    "premarket_high", "premarket_low", "premarket_mid", "premarket_range",
    "gap_dollars", "gap_pct", "gap_atr", "gap_direction",
    "session_open", "session_high", "session_low", "session_range", "close_vs_range_pct",
    "vwap", "vwap_slope", "vwap_distance", "vwap_distance_pct", "vwap_distance_atr",
    "above_vwap", "vwap_crosses",
    "atr_14", "atr_pct", "cumulative_volume", "relative_volume",
    *[f"or{w}_{f}" for w in OPENING_RANGE_WINDOWS
      for f in ("high", "low", "mid", "width", "width_atr", "state", "break_minute")],
    "trend_5m", "trend_15m", "trend_60m", "trend_daily",
    "alignment", "alignment_score", "regime", "day_type",
)


def _declared_columns() -> list[tuple[str, str]]:
    """Column name/type pairs declared in SCHEMA's minute_features table."""
    match = re.search(r"CREATE TABLE IF NOT EXISTS minute_features \((.*?)\n\);", SCHEMA, re.S)
    if not match:
        return []
    columns: list[tuple[str, str]] = []
    for part in match.group(1).split(","):
        tokens = part.strip().split()
        if len(tokens) >= 2 and tokens[0].upper() not in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK"}:
            columns.append((tokens[0], tokens[1]))
    return columns


def _migrate_columns(conn: sqlite3.Connection) -> list[str]:
    """Add any SCHEMA-declared column the live table is missing.

    `CREATE TABLE IF NOT EXISTS` is a complete no-op against an existing
    table, so adding a feature column to SCHEMA alone would leave the
    deployed table short a column and break the next insert. This is the
    same trap that silently broke market_memory's `vwap` rollout."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(minute_features)").fetchall()}
    if not existing:
        return []
    added: list[str] = []
    for name, column_type in _declared_columns():
        if name not in existing:
            conn.execute(f"ALTER TABLE minute_features ADD COLUMN {name} {column_type}")
            added.append(name)
    if added:
        conn.commit()
    return added


def connect() -> sqlite3.Connection:
    conn = srd.connect()
    conn.executescript(SCHEMA)
    _migrate_columns(conn)
    return conn


# ---------------------------------------------------------------------------
# Session context - everything knowable BEFORE the session opens
# ---------------------------------------------------------------------------

@dataclass
class SessionContext:
    """Strictly prior-session information. Nothing here may be derived
    from the session being processed."""
    prev_day_high: float | None = None
    prev_day_low: float | None = None
    prev_day_close: float | None = None
    prev_week_high: float | None = None
    prev_week_low: float | None = None
    prev_week_close: float | None = None
    atr_14: float | None = None
    daily_trend: str = "UNKNOWN"
    rvol_baseline: dict[int, float] = field(default_factory=dict)

    @property
    def prev_day_mid(self) -> float | None:
        if self.prev_day_high is None or self.prev_day_low is None:
            return None
        return (self.prev_day_high + self.prev_day_low) / 2

    @property
    def prev_day_range(self) -> float | None:
        if self.prev_day_high is None or self.prev_day_low is None:
            return None
        return self.prev_day_high - self.prev_day_low


def _minutes_of_day(bar_time: str) -> int:
    return int(bar_time[11:13]) * 60 + int(bar_time[14:16])


def _time_bucket(minutes_since_open: int) -> str:
    """The spec's own time-of-day segmentation, which several strategies
    key off directly (the 10:30 reversal, the lunch lull, power hour)."""
    if minutes_since_open < 0:
        return "PREMARKET"
    if minutes_since_open < 30:
        return "OPEN"
    if minutes_since_open < 60:
        return "MORNING"
    if minutes_since_open < 120:
        return "MIDMORNING"
    if minutes_since_open < 240:
        return "MIDDAY"
    if minutes_since_open < 360:
        return "AFTERNOON"
    if minutes_since_open < 375:
        return "FINAL_30"
    return "FINAL_15"


def _direction(current: float | None, reference: float | None, *, tolerance: float = 0.0) -> str:
    if current is None or reference is None:
        return "UNKNOWN"
    if current > reference + tolerance:
        return "UP"
    if current < reference - tolerance:
        return "DOWN"
    return "FLAT"


# ---------------------------------------------------------------------------
# Multi-timeframe trend, built causally from the 1-minute stream
# ---------------------------------------------------------------------------

class _TimeframeTrend:
    """Maintains a higher-timeframe trend read from 1-minute bars without
    ever using an incomplete bucket. A 15-minute trend at 10:07 is the
    read as of the last CLOSED 15-minute bar, which is what a live system
    would actually have had."""

    def __init__(self, minutes: int, lookback: int = 3) -> None:
        self.minutes = minutes
        self.lookback = lookback
        self._closed_closes: deque[float] = deque(maxlen=lookback + 1)
        self._bucket_index: int | None = None
        self._bucket_close: float | None = None

    def update(self, minutes_since_open: int, close: float) -> None:
        bucket = minutes_since_open // self.minutes
        if self._bucket_index is None:
            self._bucket_index = bucket
        elif bucket != self._bucket_index:
            if self._bucket_close is not None:
                self._closed_closes.append(self._bucket_close)
            self._bucket_index = bucket
        self._bucket_close = close

    @property
    def trend(self) -> str:
        if len(self._closed_closes) < 2:
            return "UNKNOWN"
        return _direction(self._closed_closes[-1], self._closed_closes[0])


def _alignment(trends: Sequence[str]) -> tuple[str, int]:
    """The spec is explicit that NOT every timeframe has to agree - it
    asks for a graded classification instead of an all-or-nothing gate."""
    known = [t for t in trends if t in ("UP", "DOWN")]
    if not known:
        return "UNKNOWN", 0
    ups = sum(1 for t in known if t == "UP")
    downs = len(known) - ups
    score = ups - downs
    if ups == len(trends) and len(known) == len(trends):
        return "STRONG_BULLISH", score
    if downs == len(trends) and len(known) == len(trends):
        return "STRONG_BEARISH", score
    if score > 0:
        return "BULLISH", score
    if score < 0:
        return "BEARISH", score
    return "NEUTRAL", score


# ---------------------------------------------------------------------------
# Regime and day type
# ---------------------------------------------------------------------------

def classify_regime(
    *, alignment: str, alignment_score: int, session_range: float | None,
    atr: float | None, vwap_crosses: int, relative_volume: float | None,
    minutes_since_open: int,
) -> str:
    """The spec's ten states. Deliberately rule-based and inspectable
    rather than clustered: the source material suggests K-means/GMM as an
    option, but an unsupervised regime that cannot be explained makes
    "strategy X works in regime 4" impossible to reason about, and
    clustering can be layered on later once these have a track record."""
    if minutes_since_open < 15 or atr in (None, 0):
        return "UNCERTAIN"

    range_vs_atr = (session_range / atr) if session_range is not None and atr else None
    hot = relative_volume is not None and relative_volume >= 1.5
    expanded = range_vs_atr is not None and range_vs_atr >= 1.0
    compressed = range_vs_atr is not None and range_vs_atr <= 0.35
    choppy = vwap_crosses >= 6

    if expanded and hot and choppy:
        return "HIGH_VOLATILITY_REVERSAL"
    if expanded and hot and alignment in ("STRONG_BULLISH", "STRONG_BEARISH"):
        return "HIGH_VOLATILITY_TREND"
    if compressed and not hot:
        return "COMPRESSION"
    if expanded and abs(alignment_score) <= 1:
        return "EXPANSION"
    if choppy or alignment == "NEUTRAL":
        return "RANGE"
    if alignment == "STRONG_BULLISH":
        return "STRONG_BULL_TREND"
    if alignment == "BULLISH":
        return "WEAK_BULL_TREND"
    if alignment == "STRONG_BEARISH":
        return "STRONG_BEAR_TREND"
    if alignment == "BEARISH":
        return "WEAK_BEAR_TREND"
    return "UNCERTAIN"


def classify_day_type(
    *, minutes_since_open: int, gap_pct: float | None, session_open: float | None,
    close: float, session_high: float, session_low: float, atr: float | None,
    vwap_crosses: int, or30_state: str,
) -> str:
    """Evolves through the session rather than being fixed at 09:35 - the
    source material asks for exactly this ("9:35 Unknown -> 10:00
    Potential trend day -> 11:00 Strong trend day -> 1:00 Trend
    weakening")."""
    if minutes_since_open < 30 or session_open is None:
        return "FORMING"

    session_range = session_high - session_low
    range_vs_atr = (session_range / atr) if atr else None
    move_from_open = close - session_open
    # How much of the day's range the close currently sits in: near 1.0
    # means closing at the high, near 0 the low. This is what separates a
    # trend day from a reversal day.
    position = ((close - session_low) / session_range) if session_range > 0 else 0.5

    big_gap = gap_pct is not None and abs(gap_pct) >= 0.4
    if big_gap:
        gap_held = (gap_pct > 0 and move_from_open > 0) or (gap_pct < 0 and move_from_open < 0)
        if minutes_since_open >= 60:
            return "GAP_AND_GO" if gap_held else "GAP_AND_FADE"

    if vwap_crosses >= 8:
        return "CHOPPY_DAY"
    if range_vs_atr is not None and range_vs_atr >= 1.2:
        if position >= 0.8 or position <= 0.2:
            return "TREND_DAY"
        return "HIGH_VOLATILITY_DAY"
    if range_vs_atr is not None and range_vs_atr <= 0.4:
        return "LOW_VOLATILITY_DAY"
    if position >= 0.75 or position <= 0.25:
        return "NORMAL_DAY"
    return "RANGE_DAY"


# ---------------------------------------------------------------------------
# The single forward pass
# ---------------------------------------------------------------------------

def compute_session_features(
    bars: Sequence[dict[str, Any]], context: SessionContext
) -> list[dict[str, Any]]:
    """One strictly forward pass over a session's bars.

    `bars` must be chronological and may include premarket/after-hours
    rows (they carry regular_session=0). Returns one feature dict per
    REGULAR-SESSION bar - premarket bars contribute to the premarket
    range and nothing else."""
    premarket_high: float | None = None
    premarket_low: float | None = None
    session_open: float | None = None
    session_high: float | None = None
    session_low: float | None = None
    cumulative_pv = 0.0
    cumulative_volume = 0.0
    vwap_history: deque[float] = deque(maxlen=VWAP_SLOPE_LOOKBACK + 1)
    vwap_crosses = 0
    last_side: int | None = None

    opening_ranges: dict[int, dict[str, Any]] = {
        window: {"high": None, "low": None, "state": "FORMING", "break_minute": None}
        for window in OPENING_RANGE_WINDOWS
    }
    trends = {
        5: _TimeframeTrend(5), 15: _TimeframeTrend(15), 60: _TimeframeTrend(60),
    }

    out: list[dict[str, Any]] = []
    atr = context.atr_14

    for bar in bars:
        bar_time = bar["bar_time"]
        close = bar["close"]
        high = bar["high"]
        low = bar["low"]
        volume = bar["volume"] or 0.0
        minutes = _minutes_of_day(bar_time)
        since_open = minutes - SESSION_OPEN_MINUTES

        if not bar["regular_session"]:
            if since_open < 0:  # premarket only; after-hours is not "premarket"
                premarket_high = high if premarket_high is None else max(premarket_high, high)
                premarket_low = low if premarket_low is None else min(premarket_low, low)
            continue

        if session_open is None:
            session_open = bar["open"]
        session_high = high if session_high is None else max(session_high, high)
        session_low = low if session_low is None else min(session_low, low)
        session_range = session_high - session_low

        typical = (high + low + close) / 3
        cumulative_pv += typical * volume
        cumulative_volume += volume
        vwap = (cumulative_pv / cumulative_volume) if cumulative_volume > 0 else None
        if vwap is not None:
            vwap_history.append(vwap)
            side = 1 if close > vwap else (-1 if close < vwap else 0)
            if side != 0 and last_side is not None and side != last_side:
                vwap_crosses += 1
            if side != 0:
                last_side = side

        vwap_slope = None
        if len(vwap_history) >= 2:
            vwap_slope = vwap_history[-1] - vwap_history[0]

        for window, state in opening_ranges.items():
            if since_open < window:
                state["high"] = high if state["high"] is None else max(state["high"], high)
                state["low"] = low if state["low"] is None else min(state["low"], low)
            else:
                if state["state"] == "FORMING":
                    state["state"] = "INSIDE"
                if state["high"] is not None and state["state"] in ("INSIDE",):
                    if close > state["high"]:
                        state["state"] = "BROKEN_UP"
                        state["break_minute"] = since_open
                    elif close < state["low"]:
                        state["state"] = "BROKEN_DOWN"
                        state["break_minute"] = since_open

        for tf in trends.values():
            tf.update(since_open, close)

        trend_values = (
            trends[5].trend, trends[15].trend, trends[60].trend, context.daily_trend,
        )
        alignment, alignment_score = _alignment(trend_values)

        relative_volume = None
        baseline = context.rvol_baseline.get(since_open)
        if baseline and baseline > 0:
            relative_volume = cumulative_volume / baseline

        gap_dollars = gap_pct = gap_atr = None
        gap_direction = "NONE"
        if context.prev_day_close and session_open is not None:
            gap_dollars = session_open - context.prev_day_close
            gap_pct = gap_dollars / context.prev_day_close * 100
            gap_atr = (gap_dollars / atr) if atr else None
            gap_direction = "UP" if gap_dollars > 0 else ("DOWN" if gap_dollars < 0 else "NONE")

        regime = classify_regime(
            alignment=alignment, alignment_score=alignment_score,
            session_range=session_range, atr=atr, vwap_crosses=vwap_crosses,
            relative_volume=relative_volume, minutes_since_open=since_open,
        )
        day_type = classify_day_type(
            minutes_since_open=since_open, gap_pct=gap_pct, session_open=session_open,
            close=close, session_high=session_high, session_low=session_low, atr=atr,
            vwap_crosses=vwap_crosses, or30_state=opening_ranges[30]["state"],
        )

        row: dict[str, Any] = {
            "bar_time": bar_time,
            "session_date": bar_time[:10],
            "minutes_since_open": since_open,
            "minutes_until_close": SESSION_CLOSE_MINUTES - minutes,
            "time_bucket": _time_bucket(since_open),
            # The bar's own OHLCV, so the feature store is self-contained
            # and downstream consumers need no join back to minute_bars.
            "open": bar["open"],
            "high": bar["high"],
            "low": bar["low"],
            "close": close,
            "volume": bar["volume"],
            "prev_day_high": context.prev_day_high,
            "prev_day_low": context.prev_day_low,
            "prev_day_close": context.prev_day_close,
            "prev_day_mid": context.prev_day_mid,
            "prev_day_range": context.prev_day_range,
            "prev_week_high": context.prev_week_high,
            "prev_week_low": context.prev_week_low,
            "prev_week_close": context.prev_week_close,
            "premarket_high": premarket_high,
            "premarket_low": premarket_low,
            "premarket_mid": ((premarket_high + premarket_low) / 2)
                             if premarket_high is not None and premarket_low is not None else None,
            "premarket_range": (premarket_high - premarket_low)
                               if premarket_high is not None and premarket_low is not None else None,
            "gap_dollars": gap_dollars, "gap_pct": gap_pct, "gap_atr": gap_atr,
            "gap_direction": gap_direction,
            "session_open": session_open, "session_high": session_high,
            "session_low": session_low, "session_range": session_range,
            "close_vs_range_pct": ((close - session_low) / session_range)
                                  if session_range > 0 else None,
            "vwap": vwap, "vwap_slope": vwap_slope,
            "vwap_distance": (close - vwap) if vwap is not None else None,
            "vwap_distance_pct": ((close - vwap) / vwap * 100) if vwap else None,
            "vwap_distance_atr": ((close - vwap) / atr) if vwap is not None and atr else None,
            "above_vwap": int(close > vwap) if vwap is not None else None,
            "vwap_crosses": vwap_crosses,
            "atr_14": atr, "atr_pct": (atr / close * 100) if atr and close else None,
            "cumulative_volume": cumulative_volume, "relative_volume": relative_volume,
            "trend_5m": trend_values[0], "trend_15m": trend_values[1],
            "trend_60m": trend_values[2], "trend_daily": trend_values[3],
            "alignment": alignment, "alignment_score": alignment_score,
            "regime": regime, "day_type": day_type,
        }
        for window in OPENING_RANGE_WINDOWS:
            state = opening_ranges[window]
            width = (state["high"] - state["low"]) if state["high"] is not None and state["low"] is not None else None
            row[f"or{window}_high"] = state["high"]
            row[f"or{window}_low"] = state["low"]
            row[f"or{window}_mid"] = ((state["high"] + state["low"]) / 2) if width is not None else None
            row[f"or{window}_width"] = width
            row[f"or{window}_width_atr"] = (width / atr) if width is not None and atr else None
            row[f"or{window}_state"] = state["state"]
            row[f"or{window}_break_minute"] = state["break_minute"]
        out.append(row)

    return out


# ---------------------------------------------------------------------------
# Context assembly across sessions
# ---------------------------------------------------------------------------

def session_dates(conn: sqlite3.Connection, ticker: str = "SPY") -> list[str]:
    return [
        row["d"] for row in conn.execute(
            "SELECT DISTINCT substr(bar_time,1,10) AS d FROM minute_bars "
            "WHERE ticker=? AND regular_session=1 ORDER BY d", (ticker,)
        ).fetchall()
    ]


def load_session_bars(conn: sqlite3.Connection, session: str, ticker: str = "SPY") -> list[dict[str, Any]]:
    """Bars for one session, as a range scan on the (ticker, bar_time)
    primary key.

    The obvious `substr(bar_time,1,10)=?` form does not get optimised -
    SQLite ignores the expression index on it and falls back to the
    ticker-only autoindex, scanning all 1.43M SPY rows for every single
    session. A half-open range on the stored `YYYY-MM-DDTHH:MM:SS` text
    hits the primary key directly and returns rows already ordered."""
    return [
        dict(row) for row in conn.execute(
            "SELECT bar_time, open, high, low, close, volume, regular_session FROM minute_bars "
            "WHERE ticker=? AND bar_time >= ? AND bar_time < ? ORDER BY bar_time",
            (ticker, f"{session}T", f"{session}U"),
        ).fetchall()
    ]


def _session_ohlc(bars: Sequence[dict[str, Any]]) -> dict[str, float] | None:
    regular = [b for b in bars if b["regular_session"]]
    if not regular:
        return None
    return {
        "open": regular[0]["open"],
        "high": max(b["high"] for b in regular),
        "low": min(b["low"] for b in regular),
        "close": regular[-1]["close"],
    }


def _true_range(current: dict[str, float], prior_close: float | None) -> float:
    if prior_close is None:
        return current["high"] - current["low"]
    return max(
        current["high"] - current["low"],
        abs(current["high"] - prior_close),
        abs(current["low"] - prior_close),
    )


def all_session_ohlc(conn: sqlite3.Connection, ticker: str = "SPY") -> list[tuple[str, dict[str, float]]]:
    """Every session's regular-hours OHLC in ONE query.

    Previously this was derived by pulling each session's bars into
    Python, which meant a partial rebuild still dragged all 1.43M rows
    across the wire just to reconstruct prior-day levels. One grouped
    query with window functions gives the same answer in a fraction of a
    second."""
    rows = conn.execute(
        """
        SELECT d, open, high, low, close FROM (
            SELECT substr(bar_time,1,10) AS d,
                   FIRST_VALUE(open) OVER w AS open,
                   MAX(high) OVER w AS high,
                   MIN(low) OVER w AS low,
                   LAST_VALUE(close) OVER w AS close,
                   ROW_NUMBER() OVER w AS rn
            FROM minute_bars
            WHERE ticker = ? AND regular_session = 1
            WINDOW w AS (
                PARTITION BY substr(bar_time,1,10) ORDER BY bar_time
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
            )
        ) WHERE rn = 1 ORDER BY d
        """,
        (ticker,),
    ).fetchall()
    return [(r["d"], {"open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]}) for r in rows]


class ContextBuilder:
    """Walks sessions forward, carrying only what was knowable at each
    session's open. Fed sessions in order and never shown the current
    one, so the context it hands out is causal by construction.

    Everything it tracks is maintained incrementally - O(1) per session.
    The first version recomputed the previous week by rescanning every
    prior session and calling date.fromisoformat().isocalendar() on each,
    which is O(N^2) with an expensive constant and made even a 40-session
    build take minutes."""

    def __init__(self) -> None:
        self._prior: dict[str, float] | None = None
        self._true_ranges: deque[float] = deque(maxlen=ATR_PERIOD)
        self._recent_closes: deque[float] = deque(maxlen=6)
        self._rvol: deque[dict[int, float]] = deque(maxlen=RVOL_BASELINE_SESSIONS)
        self._week_key: tuple[int, int] | None = None
        self._week: dict[str, float] | None = None
        self._prev_week: dict[str, float] | None = None
        self._baseline_cache: dict[int, float] | None = None

    def context_for(self, session: str) -> SessionContext:
        ctx = SessionContext()
        if self._prior:
            ctx.prev_day_high = self._prior["high"]
            ctx.prev_day_low = self._prior["low"]
            ctx.prev_day_close = self._prior["close"]
        if len(self._true_ranges) == ATR_PERIOD:
            ctx.atr_14 = sum(self._true_ranges) / ATR_PERIOD

        week_key = date.fromisoformat(session).isocalendar()[:2]
        # If this session opens a new week, the week we were accumulating
        # is now the completed previous week.
        completed = self._week if (self._week_key is not None and week_key != self._week_key) else self._prev_week
        if completed:
            ctx.prev_week_high = completed["high"]
            ctx.prev_week_low = completed["low"]
            ctx.prev_week_close = completed["close"]

        if len(self._recent_closes) == self._recent_closes.maxlen:
            ctx.daily_trend = _direction(self._recent_closes[-1], self._recent_closes[0])

        if self._rvol:
            if self._baseline_cache is None:
                minutes: set[int] = set()
                for profile in self._rvol:
                    minutes.update(profile)
                self._baseline_cache = {
                    minute: statistics.median([p[minute] for p in self._rvol if minute in p])
                    for minute in minutes
                }
            ctx.rvol_baseline = self._baseline_cache
        return ctx

    def observe(
        self, session: str, ohlc: dict[str, float], bars: Sequence[dict[str, Any]] | None = None
    ) -> None:
        """ohlc comes from all_session_ohlc; bars are only needed to
        extend the relative-volume baseline, so a caller that does not
        need that for this session can pass None and skip the read."""
        week_key = date.fromisoformat(session).isocalendar()[:2]
        if self._week_key is None:
            self._week_key, self._week = week_key, dict(ohlc)
        elif week_key != self._week_key:
            self._prev_week = self._week
            self._week_key, self._week = week_key, dict(ohlc)
        else:
            assert self._week is not None
            self._week["high"] = max(self._week["high"], ohlc["high"])
            self._week["low"] = min(self._week["low"], ohlc["low"])
            self._week["close"] = ohlc["close"]

        prior_close = self._prior["close"] if self._prior else None
        self._true_ranges.append(_true_range(ohlc, prior_close))
        self._recent_closes.append(ohlc["close"])
        self._prior = dict(ohlc)

        if bars is not None:
            cumulative = 0.0
            profile: dict[int, float] = {}
            for bar in bars:
                if not bar["regular_session"]:
                    continue
                cumulative += bar["volume"] or 0.0
                profile[_minutes_of_day(bar["bar_time"]) - SESSION_OPEN_MINUTES] = cumulative
            if profile:
                self._rvol.append(profile)
                self._baseline_cache = None  # deque changed; recompute lazily


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def _insert_rows(conn: sqlite3.Connection, ticker: str, rows: Sequence[dict[str, Any]]) -> None:
    if not rows:
        return
    columns = ("ticker", "bar_time", "session_date", *FEATURE_COLUMNS)
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT OR REPLACE INTO minute_features ({', '.join(columns)}) VALUES ({placeholders})",
        [tuple([ticker, r["bar_time"], r["session_date"], *[r.get(c) for c in FEATURE_COLUMNS]]) for r in rows],
    )


def build_features(
    conn: sqlite3.Connection, ticker: str = "SPY", *, sessions: Sequence[str] | None = None,
    progress_every: int = 250,
) -> dict[str, Any]:
    """Rebuilds the feature table. Sessions are processed in order so the
    ContextBuilder only ever holds prior information."""
    ohlc_by_session = all_session_ohlc(conn, ticker)
    ordered = [session for session, _ in ohlc_by_session]
    targets = set(sessions) if sessions else set(ordered)

    # Bars are only read for sessions being built, plus the short window
    # immediately BEFORE each target needed to seed the relative-volume
    # baseline. Prior-day, prior-week, ATR and daily-trend context all
    # come from the single OHLC query instead, so a 40-session rebuild
    # reads 40-ish sessions of bars rather than all 1.43M rows.
    target_indices = [i for i, s in enumerate(ordered) if s in targets]
    if not target_indices:
        return {"sessions": 0, "rows": 0}
    needs_bars_at = set(target_indices)
    for i in target_indices:
        needs_bars_at.update(range(max(0, i - RVOL_BASELINE_SESSIONS), i))
    last_target = target_indices[-1]

    builder = ContextBuilder()
    written = 0
    processed = 0
    for index, (session, ohlc) in enumerate(ohlc_by_session):
        if index > last_target:
            break  # nothing left to build; later sessions cannot inform earlier ones
        building = session in targets
        bars = load_session_bars(conn, session, ticker) if index in needs_bars_at else None

        if building:
            context = builder.context_for(session)
            rows = compute_session_features(bars or [], context)
            _insert_rows(conn, ticker, rows)
            written += len(rows)
            processed += 1
            if progress_every and processed % progress_every == 0:
                conn.commit()
                print(f"  {processed} sessions, {written:,} rows", flush=True)
        # Observed regardless, so a partial rebuild still carries correct
        # prior context into the sessions it does compute.
        builder.observe(session, ohlc, bars)
    conn.commit()
    return {"sessions": processed, "rows": written}


if __name__ == "__main__":
    import json

    conn = connect()
    try:
        print(json.dumps(build_features(conn), indent=2))
    finally:
        conn.close()
