"""A standalone, opt-in historical bar/feature/pattern store for SPY.

Owner: "I want it to remember chart patterns and history and everything
so when we make new strategies we can have all this shit tracked
already." Deliberately NOT wired into any live strategy or the scan
loop - no existing code imports this module, so nothing here can affect
real trading even if it has a bug. A future strategy opts in by
importing get_features/get_recent_patterns/pattern_stats explicitly.

Three real layers, all pure math on OHLCV bars (no chart images, no
"AI vibes"):

1. Bars - daily history goes back SPY_DAILY_HISTORY_DAYS (~2 years) in
   one backfill, refreshed incrementally after that. Intraday (5-minute)
   history only covers TODAY per Tradier's timesales endpoint, so it
   accumulates one real trading day at a time, every day this runs -
   there is no way to backfill years of 5-minute bars in one shot, and
   pretending otherwise would be dishonest about what's actually here.

2. Features - SMA(20/50/200) + EMA(9/20/50/200)/MACD/RSI/ATR(+percentile
   rank)/Bollinger (reusing spy_scanner.py's own shared math, not
   reimplemented here), relative volume, structural flags (higher-high/
   higher-low, inside/outside bar, NR7, gap size, trend-structure run
   length), golden/death cross, and a combined short/medium/long-term
   trend_label (e.g. "SHORT:UP MEDIUM:UP LONG:DOWN", each leg just a
   directional comparison between two moving averages of different
   speeds) - computed once per bar and cached. Every column exports to a
   plain CSV (market_memory_daily.csv / market_memory_intraday_5min.csv,
   refreshed every cycle) so this is directly inspectable without SQL,
   same as every other log in this project.

3. Patterns + outcomes - a registry of named pattern detectors, split
   into "structural" (inside bar, NR7, gap, trend-structure runs,
   volatility contraction, volume climax, golden/death cross - real,
   quantifiable, testable tendencies) and "candlestick" (doji, hammer,
   engulfing - the classic textbook shapes, included because the owner
   asked for "all of them", but every candlestick-category pattern
   carries an explicit evidence_note flagging its predictive value as
   weak/folklore, not a real edge - matches this project's own Learning
   Center content on the same point). Every detected pattern's actual
   forward return (5/10/20 bars later) gets recorded once enough time
   has passed, so a future strategy can query "when this exact pattern
   fired historically, what really happened next" instead of trusting
   the pattern's name alone - and pattern_stats_recent_vs_all_time can
   compare a recent window against the full history for the same
   pattern, which is the real answer to "does more history make the
   read better, or is old data stale": if the two windows roughly agree,
   the extra history is real statistical power; if they've diverged, the
   market's own character has likely shifted and the all-time number
   alone would be misleading.
"""

from __future__ import annotations

import csv
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import spy_scanner as s

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "market_memory.db"
DAILY_CSV_PATH = ROOT / "state" / "market_memory_daily.csv"
INTRADAY_CSV_PATH = ROOT / "state" / "market_memory_intraday_5min.csv"

SPY_DAILY_HISTORY_DAYS = 730
FORWARD_RETURN_HORIZONS = (5, 10, 20)
NR7_LOOKBACK = 7
VOLUME_CLIMAX_MULTIPLE = 2.0
VOLATILITY_CONTRACTION_LOOKBACK = 5
GAP_THRESHOLD_PCT = 0.3
TREND_STRUCTURE_MIN_RUN = 3

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (ticker, timeframe, bar_time)
);
CREATE TABLE IF NOT EXISTS features (
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    sma_20 REAL, sma_50 REAL, sma_200 REAL,
    ema_9 REAL, ema_20 REAL, ema_50 REAL, ema_200 REAL,
    macd_line REAL, macd_signal REAL, macd_histogram REAL, macd_color TEXT,
    rsi_14 REAL,
    atr_14 REAL, atr_percentile REAL,
    bb_upper REAL, bb_mid REAL, bb_lower REAL, bb_width_pct REAL,
    relative_volume REAL,
    higher_high INTEGER, higher_low INTEGER, lower_high INTEGER, lower_low INTEGER,
    trend_run_length INTEGER,
    inside_bar INTEGER, outside_bar INTEGER, nr7 INTEGER,
    gap_pct REAL,
    golden_cross INTEGER, death_cross INTEGER,
    price_above_sma_200 INTEGER, price_above_ema_200 INTEGER,
    short_term_trend TEXT, medium_term_trend TEXT, long_term_trend TEXT, trend_label TEXT,
    market_condition TEXT,
    computed_at TEXT NOT NULL,
    PRIMARY KEY (ticker, timeframe, bar_time)
);
CREATE TABLE IF NOT EXISTS patterns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    bar_time TEXT NOT NULL,
    pattern_name TEXT NOT NULL,
    category TEXT NOT NULL,
    evidence_note TEXT NOT NULL,
    detected_at TEXT NOT NULL,
    UNIQUE (ticker, timeframe, bar_time, pattern_name)
);
CREATE INDEX IF NOT EXISTS patterns_lookup ON patterns(ticker, timeframe, pattern_name);
CREATE TABLE IF NOT EXISTS pattern_outcomes (
    pattern_id INTEGER NOT NULL,
    bars_forward INTEGER NOT NULL,
    forward_return_pct REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    PRIMARY KEY (pattern_id, bars_forward),
    FOREIGN KEY (pattern_id) REFERENCES patterns(id)
);
"""

CANDLESTICK_EVIDENCE_NOTE = (
    "Classic textbook candlestick shape - weak/inconsistent predictive value in "
    "the literature, included for completeness at the owner's request, not treated "
    "as a real edge. Compare against this pattern's own tracked pattern_stats() "
    "before trusting it for anything."
)
STRUCTURAL_EVIDENCE_NOTE = (
    "Quantifiable structural/statistical tendency, not a subjective shape read."
)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(SCHEMA)
    return conn


# ---------------------------------------------------------------------------
# Bar ingestion
# ---------------------------------------------------------------------------

def _daily_bar_rows(history: list[dict[str, Any]]) -> list[tuple[str, float, float, float, float, float]]:
    rows = []
    for day in history:
        bar_time = str(day.get("date") or "")
        if not bar_time:
            continue
        rows.append((
            bar_time,
            s.as_float(day.get("open"), 0.0) or 0.0,
            s.as_float(day.get("high"), 0.0) or 0.0,
            s.as_float(day.get("low"), 0.0) or 0.0,
            s.as_float(day.get("close"), 0.0) or 0.0,
            s.as_float(day.get("volume"), 0.0) or 0.0,
        ))
    return rows


def _intraday_bar_rows(bars: list[dict[str, Any]]) -> list[tuple[str, float, float, float, float, float]]:
    rows = []
    for bar in bars:
        bar_time = str(bar.get("time") or "")
        if not bar_time:
            continue
        rows.append((
            bar_time,
            s.as_float(bar.get("open"), 0.0) or 0.0,
            s.as_float(bar.get("high"), 0.0) or 0.0,
            s.as_float(bar.get("low"), 0.0) or 0.0,
            s.as_float(bar.get("close"), 0.0) or 0.0,
            s.as_float(bar.get("volume"), 0.0) or 0.0,
        ))
    return rows


def store_bars(conn: sqlite3.Connection, ticker: str, timeframe: str, rows: list[tuple]) -> int:
    """INSERT OR IGNORE - a bar already stored (same ticker/timeframe/
    bar_time) is never overwritten, so re-running collection on a day
    already recorded is always a safe, cheap no-op."""
    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO bars (ticker, timeframe, bar_time, open, high, low, close, volume) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(ticker, timeframe, *row) for row in rows],
    )
    conn.commit()
    return conn.total_changes - before


def load_bars(conn: sqlite3.Connection, ticker: str, timeframe: str, limit: int | None = None) -> list[sqlite3.Row]:
    query = "SELECT * FROM bars WHERE ticker = ? AND timeframe = ? ORDER BY bar_time"
    if limit:
        query = f"SELECT * FROM ({query} DESC LIMIT {int(limit)}) ORDER BY bar_time"
    return conn.execute(query, (ticker, timeframe)).fetchall()


# ---------------------------------------------------------------------------
# Feature computation
# ---------------------------------------------------------------------------

def compute_features_for_window(bars: list[sqlite3.Row], index: int) -> dict[str, Any]:
    """Every feature computable using only bars[:index+1] - never looks
    ahead, so features stored for a historical bar are exactly what a
    strategy running live ON that bar would have seen."""
    window = bars[: index + 1]
    closes = [row["close"] for row in window]
    highs = [row["high"] for row in window]
    lows = [row["low"] for row in window]
    volumes = [row["volume"] for row in window]
    current = window[-1]

    sma_20 = s.simple_moving_average(closes, 20)
    sma_50 = s.simple_moving_average(closes, 50)
    sma_200 = s.simple_moving_average(closes, 200)

    ema_9 = s.exponential_moving_average(closes, 9)
    ema_20 = s.exponential_moving_average(closes, 20)
    ema_50 = s.exponential_moving_average(closes, 50)
    ema_200 = s.exponential_moving_average(closes, 200)

    macd_current, macd_previous = s.spy_expansion_macd_histogram(closes) if len(closes) > 1 else (None, None)
    macd_color = s.spy_expansion_macd_color(macd_current, macd_previous) if macd_current is not None else "UNKNOWN"
    fast_ema = s.exponential_moving_average(closes, s.SPY_EXPANSION_MACD_FAST_PERIOD)
    slow_ema = s.exponential_moving_average(closes, s.SPY_EXPANSION_MACD_SLOW_PERIOD)
    macd_line = (fast_ema - slow_ema) if fast_ema is not None and slow_ema is not None else None
    macd_signal = (macd_line - macd_current) if macd_line is not None and macd_current is not None else None

    rsi_14 = s.relative_strength_index(closes, 14)
    atr_14 = s.average_true_range(highs, lows, closes, 14)
    atr_percentile = _atr_percentile(bars, index, atr_14)
    bb_upper, bb_mid, bb_lower = s.bollinger_bands(closes, 20, 2.0)
    bb_width_pct = ((bb_upper - bb_lower) / bb_mid * 100) if bb_upper is not None and bb_mid else None

    # Golden/death cross - the classic long-term trend-shift marker (SMA50
    # crossing SMA200), only meaningful the FIRST bar it happens, so this
    # also needs the prior bar's SMAs, not just the current ones.
    golden_cross = death_cross = None
    if index >= 1:
        prior_window = bars[:index]
        prior_closes = [row["close"] for row in prior_window]
        prior_sma_50 = s.simple_moving_average(prior_closes, 50)
        prior_sma_200 = s.simple_moving_average(prior_closes, 200)
        if None not in (sma_50, sma_200, prior_sma_50, prior_sma_200):
            golden_cross = int(prior_sma_50 <= prior_sma_200 and sma_50 > sma_200)
            death_cross = int(prior_sma_50 >= prior_sma_200 and sma_50 < sma_200)

    price_above_sma_200 = int(current["close"] > sma_200) if sma_200 is not None else None
    price_above_ema_200 = int(current["close"] > ema_200) if ema_200 is not None else None

    # Short/medium/long-term trend read, each just a directional
    # comparison between two moving averages of different speeds - not a
    # shape judgment, three independent numeric facts combined into one
    # readable label (e.g. "SHORT:UP MEDIUM:UP LONG:DOWN").
    short_term_trend = _trend_direction(ema_9, ema_20)
    medium_term_trend = _trend_direction(ema_20, sma_50)
    long_term_trend = _trend_direction(sma_50, sma_200)
    trend_label = f"SHORT:{short_term_trend} MEDIUM:{medium_term_trend} LONG:{long_term_trend}"

    relative_volume = None
    if len(volumes) > 20:
        trailing_avg = sum(volumes[-21:-1]) / 20
        if trailing_avg > 0:
            relative_volume = volumes[-1] / trailing_avg

    higher_high = higher_low = lower_high = lower_low = None
    if index >= 1:
        prior = bars[index - 1]
        higher_high = int(current["high"] > prior["high"])
        higher_low = int(current["low"] > prior["low"])
        lower_high = int(current["high"] < prior["high"])
        lower_low = int(current["low"] < prior["low"])

    trend_run_length = _trend_run_length(bars, index)

    inside_bar = outside_bar = None
    if index >= 1:
        prior = bars[index - 1]
        inside_bar = int(current["high"] <= prior["high"] and current["low"] >= prior["low"])
        outside_bar = int(current["high"] > prior["high"] and current["low"] < prior["low"])

    nr7 = None
    if index >= NR7_LOOKBACK - 1:
        ranges = [bars[i]["high"] - bars[i]["low"] for i in range(index - NR7_LOOKBACK + 1, index + 1)]
        current_range = ranges[-1]
        nr7 = int(current_range > 0 and current_range == min(ranges))

    gap_pct = None
    if index >= 1:
        prior_close = bars[index - 1]["close"]
        if prior_close:
            gap_pct = (current["open"] - prior_close) / prior_close * 100

    return {
        "sma_20": sma_20, "sma_50": sma_50, "sma_200": sma_200,
        "ema_9": ema_9, "ema_20": ema_20, "ema_50": ema_50, "ema_200": ema_200,
        "macd_line": macd_line, "macd_signal": macd_signal,
        "macd_histogram": macd_current, "macd_color": macd_color,
        "rsi_14": rsi_14, "atr_14": atr_14, "atr_percentile": atr_percentile,
        "bb_upper": bb_upper, "bb_mid": bb_mid, "bb_lower": bb_lower, "bb_width_pct": bb_width_pct,
        "relative_volume": relative_volume,
        "higher_high": higher_high, "higher_low": higher_low,
        "lower_high": lower_high, "lower_low": lower_low,
        "trend_run_length": trend_run_length,
        "inside_bar": inside_bar, "outside_bar": outside_bar, "nr7": nr7,
        "gap_pct": gap_pct,
        "golden_cross": golden_cross, "death_cross": death_cross,
        "price_above_sma_200": price_above_sma_200, "price_above_ema_200": price_above_ema_200,
        "short_term_trend": short_term_trend, "medium_term_trend": medium_term_trend,
        "long_term_trend": long_term_trend, "trend_label": trend_label,
    }


def _trend_direction(fast: float | None, slow: float | None) -> str:
    if fast is None or slow is None:
        return "UNKNOWN"
    if fast > slow:
        return "UP"
    if fast < slow:
        return "DOWN"
    return "FLAT"


def _atr_percentile(bars: list[sqlite3.Row], index: int, current_atr: float | None, lookback: int = 100) -> float | None:
    """Where the current ATR ranks (0-100) against its own trailing
    history - answers "is volatility high or low RIGHT NOW relative to
    itself" in a way a raw ATR dollar figure doesn't, since SPY's normal
    ATR level has drifted a lot over the years (regime dependence -
    comparing today's ATR directly to 2023's ATR isn't apples to apples,
    ranking against a rolling window is)."""
    if current_atr is None or index < 14:
        return None
    history: list[float] = []
    start = max(14, index - lookback + 1)
    for i in range(start, index + 1):
        window = bars[: i + 1]
        atr = s.average_true_range(
            [row["high"] for row in window], [row["low"] for row in window],
            [row["close"] for row in window], 14,
        )
        if atr is not None:
            history.append(atr)
    if len(history) < 2:
        return None
    rank = sum(1 for value in history if value <= current_atr)
    return rank / len(history) * 100


def _trend_run_length(bars: list[sqlite3.Row], index: int) -> int | None:
    """Signed count of consecutive higher-high+higher-low bars (positive)
    or lower-high+lower-low bars (negative) ending at index - how long the
    current trend structure has persisted, not just whether it exists
    right now."""
    if index < 1:
        return None
    run = 0
    direction = 0
    i = index
    while i >= 1:
        current, prior = bars[i], bars[i - 1]
        up = current["high"] > prior["high"] and current["low"] > prior["low"]
        down = current["high"] < prior["high"] and current["low"] < prior["low"]
        this_direction = 1 if up else (-1 if down else 0)
        if this_direction == 0:
            break
        if direction == 0:
            direction = this_direction
        elif this_direction != direction:
            break
        run += 1
        i -= 1
    return run * direction


def store_features(conn: sqlite3.Connection, ticker: str, timeframe: str, bar_time: str, features: dict[str, Any], market_condition: str | None) -> None:
    conn.execute(
        """
        INSERT OR REPLACE INTO features (
            ticker, timeframe, bar_time, sma_20, sma_50, sma_200, ema_9, ema_20, ema_50, ema_200,
            macd_line, macd_signal, macd_histogram, macd_color, rsi_14, atr_14, atr_percentile,
            bb_upper, bb_mid, bb_lower, bb_width_pct, relative_volume,
            higher_high, higher_low, lower_high, lower_low, trend_run_length,
            inside_bar, outside_bar, nr7, gap_pct,
            golden_cross, death_cross, price_above_sma_200, price_above_ema_200,
            short_term_trend, medium_term_trend, long_term_trend, trend_label,
            market_condition, computed_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticker, timeframe, bar_time,
            features["sma_20"], features["sma_50"], features["sma_200"],
            features["ema_9"], features["ema_20"], features["ema_50"], features["ema_200"],
            features["macd_line"], features["macd_signal"], features["macd_histogram"], features["macd_color"],
            features["rsi_14"], features["atr_14"], features["atr_percentile"],
            features["bb_upper"], features["bb_mid"], features["bb_lower"], features["bb_width_pct"],
            features["relative_volume"],
            features["higher_high"], features["higher_low"], features["lower_high"], features["lower_low"],
            features["trend_run_length"],
            features["inside_bar"], features["outside_bar"], features["nr7"], features["gap_pct"],
            features["golden_cross"], features["death_cross"],
            features["price_above_sma_200"], features["price_above_ema_200"],
            features["short_term_trend"], features["medium_term_trend"],
            features["long_term_trend"], features["trend_label"],
            market_condition, datetime.now().isoformat(),
        ),
    )


# ---------------------------------------------------------------------------
# Pattern detection - each detector takes (bars, features, index) for the
# bar being evaluated and returns True/False. Registered with a category
# and evidence_note so category=="candlestick" entries are never silently
# indistinguishable from the real structural/statistical ones.
# ---------------------------------------------------------------------------

PatternDetector = Callable[[list[sqlite3.Row], dict[str, Any], int], bool]


def _detect_inside_bar(bars, features, index) -> bool:
    return bool(features.get("inside_bar"))


def _detect_outside_bar(bars, features, index) -> bool:
    return bool(features.get("outside_bar"))


def _detect_nr7(bars, features, index) -> bool:
    return bool(features.get("nr7"))


def _detect_gap_up(bars, features, index) -> bool:
    gap = features.get("gap_pct")
    return gap is not None and gap >= GAP_THRESHOLD_PCT


def _detect_gap_down(bars, features, index) -> bool:
    gap = features.get("gap_pct")
    return gap is not None and gap <= -GAP_THRESHOLD_PCT


def _detect_uptrend_structure(bars, features, index) -> bool:
    run = features.get("trend_run_length")
    return run is not None and run >= TREND_STRUCTURE_MIN_RUN


def _detect_downtrend_structure(bars, features, index) -> bool:
    run = features.get("trend_run_length")
    return run is not None and run <= -TREND_STRUCTURE_MIN_RUN


def _detect_volatility_contraction(bars, features, index) -> bool:
    """ATR trending down over the last VOLATILITY_CONTRACTION_LOOKBACK
    bars - a real, documented precursor to range expansion (a "squeeze"),
    not a shape read."""
    if index < VOLATILITY_CONTRACTION_LOOKBACK:
        return False
    atrs = []
    for i in range(index - VOLATILITY_CONTRACTION_LOOKBACK + 1, index + 1):
        highs = [bars[j]["high"] for j in range(max(0, i - 13), i + 1)]
        lows = [bars[j]["low"] for j in range(max(0, i - 13), i + 1)]
        closes = [bars[j]["close"] for j in range(max(0, i - 13), i + 1)]
        atr = s.average_true_range(highs, lows, closes, 14)
        if atr is None:
            return False
        atrs.append(atr)
    return all(later <= earlier for earlier, later in zip(atrs, atrs[1:]))


def _detect_volume_climax(bars, features, index) -> bool:
    relative_volume = features.get("relative_volume")
    return relative_volume is not None and relative_volume >= VOLUME_CLIMAX_MULTIPLE


def _detect_doji(bars, features, index) -> bool:
    bar = bars[index]
    total_range = bar["high"] - bar["low"]
    if total_range <= 0:
        return False
    body = abs(bar["close"] - bar["open"])
    return (body / total_range) <= 0.1


def _detect_hammer(bars, features, index) -> bool:
    bar = bars[index]
    total_range = bar["high"] - bar["low"]
    if total_range <= 0:
        return False
    body_top = max(bar["open"], bar["close"])
    body_bottom = min(bar["open"], bar["close"])
    body = body_top - body_bottom
    lower_wick = body_bottom - bar["low"]
    upper_wick = bar["high"] - body_top
    return lower_wick >= body * 2 and upper_wick <= body * 0.5 and body > 0


def _detect_bullish_engulfing(bars, features, index) -> bool:
    if index < 1:
        return False
    prior, current = bars[index - 1], bars[index]
    prior_bearish = prior["close"] < prior["open"]
    current_bullish = current["close"] > current["open"]
    return (
        prior_bearish and current_bullish
        and current["open"] <= prior["close"] and current["close"] >= prior["open"]
    )


def _detect_bearish_engulfing(bars, features, index) -> bool:
    if index < 1:
        return False
    prior, current = bars[index - 1], bars[index]
    prior_bullish = prior["close"] > prior["open"]
    current_bearish = current["close"] < current["open"]
    return (
        prior_bullish and current_bearish
        and current["open"] >= prior["close"] and current["close"] <= prior["open"]
    )


def _detect_golden_cross(bars, features, index) -> bool:
    return bool(features.get("golden_cross"))


def _detect_death_cross(bars, features, index) -> bool:
    return bool(features.get("death_cross"))


PATTERN_REGISTRY: dict[str, tuple[str, str, PatternDetector]] = {
    "inside_bar": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_inside_bar),
    "outside_bar": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_outside_bar),
    "nr7": ("volatility", STRUCTURAL_EVIDENCE_NOTE, _detect_nr7),
    "gap_up": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_gap_up),
    "gap_down": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_gap_down),
    "uptrend_structure": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_uptrend_structure),
    "downtrend_structure": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_downtrend_structure),
    "volatility_contraction": ("volatility", STRUCTURAL_EVIDENCE_NOTE, _detect_volatility_contraction),
    "volume_climax": ("volume", STRUCTURAL_EVIDENCE_NOTE, _detect_volume_climax),
    "golden_cross": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_golden_cross),
    "death_cross": ("structural", STRUCTURAL_EVIDENCE_NOTE, _detect_death_cross),
    "doji": ("candlestick", CANDLESTICK_EVIDENCE_NOTE, _detect_doji),
    "hammer": ("candlestick", CANDLESTICK_EVIDENCE_NOTE, _detect_hammer),
    "bullish_engulfing": ("candlestick", CANDLESTICK_EVIDENCE_NOTE, _detect_bullish_engulfing),
    "bearish_engulfing": ("candlestick", CANDLESTICK_EVIDENCE_NOTE, _detect_bearish_engulfing),
}


def detect_patterns_for_bar(bars: list[sqlite3.Row], features: dict[str, Any], index: int) -> list[str]:
    return [name for name, (_, _, detector) in PATTERN_REGISTRY.items() if detector(bars, features, index)]


def store_patterns(conn: sqlite3.Connection, ticker: str, timeframe: str, bar_time: str, pattern_names: list[str]) -> list[int]:
    ids = []
    for name in pattern_names:
        category, evidence_note, _ = PATTERN_REGISTRY[name]
        cursor = conn.execute(
            "INSERT OR IGNORE INTO patterns (ticker, timeframe, bar_time, pattern_name, category, evidence_note, detected_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticker, timeframe, bar_time, name, category, evidence_note, datetime.now().isoformat()),
        )
        if cursor.lastrowid and cursor.rowcount:
            ids.append(cursor.lastrowid)
    conn.commit()
    return ids


# ---------------------------------------------------------------------------
# Outcome tracking - what actually happened after a pattern fired
# ---------------------------------------------------------------------------

def backfill_pattern_outcomes(conn: sqlite3.Connection, ticker: str, timeframe: str) -> int:
    """For every detected pattern whose bars_forward horizon has now
    actually elapsed (enough newer bars exist) and hasn't been recorded
    yet, computes the real forward return and stores it. Safe to call
    every cycle - only ever fills in gaps, never recomputes an already-
    recorded outcome."""
    bars = load_bars(conn, ticker, timeframe)
    bar_time_to_index = {row["bar_time"]: i for i, row in enumerate(bars)}
    pending = conn.execute(
        "SELECT id, bar_time FROM patterns WHERE ticker = ? AND timeframe = ?",
        (ticker, timeframe),
    ).fetchall()
    written = 0
    for pattern in pending:
        detection_index = bar_time_to_index.get(pattern["bar_time"])
        if detection_index is None:
            continue
        entry_close = bars[detection_index]["close"]
        for horizon in FORWARD_RETURN_HORIZONS:
            target_index = detection_index + horizon
            if target_index >= len(bars):
                continue
            already_recorded = conn.execute(
                "SELECT 1 FROM pattern_outcomes WHERE pattern_id = ? AND bars_forward = ?",
                (pattern["id"], horizon),
            ).fetchone()
            if already_recorded:
                continue
            forward_close = bars[target_index]["close"]
            if not entry_close:
                continue
            forward_return_pct = (forward_close - entry_close) / entry_close * 100
            conn.execute(
                "INSERT INTO pattern_outcomes (pattern_id, bars_forward, forward_return_pct, recorded_at) "
                "VALUES (?, ?, ?, ?)",
                (pattern["id"], horizon, forward_return_pct, datetime.now().isoformat()),
            )
            written += 1
    conn.commit()
    return written


# ---------------------------------------------------------------------------
# CSV export - a directly-inspectable view of everything collected, no
# SQL required. Matches how every other log in this project already
# works. Rewritten in full each cycle (cheap at this data volume, and
# safer than trying to append-patch a CSV in place).
# ---------------------------------------------------------------------------

FEATURE_COLUMNS = (
    "sma_20", "sma_50", "sma_200", "ema_9", "ema_20", "ema_50", "ema_200",
    "macd_line", "macd_signal", "macd_histogram", "macd_color",
    "rsi_14", "atr_14", "atr_percentile",
    "bb_upper", "bb_mid", "bb_lower", "bb_width_pct", "relative_volume",
    "higher_high", "higher_low", "lower_high", "lower_low", "trend_run_length",
    "inside_bar", "outside_bar", "nr7", "gap_pct",
    "golden_cross", "death_cross", "price_above_sma_200", "price_above_ema_200",
    "short_term_trend", "medium_term_trend", "long_term_trend", "trend_label",
    "market_condition",
)


def export_features_csv(conn: sqlite3.Connection, ticker: str, timeframe: str, path: Path) -> int:
    feature_select = ", ".join(f"f.{column}" for column in FEATURE_COLUMNS)
    rows = conn.execute(
        f"""
        SELECT b.bar_time AS bar_time, b.open, b.high, b.low, b.close, b.volume, {feature_select}
        FROM bars b
        LEFT JOIN features f ON f.ticker = b.ticker AND f.timeframe = b.timeframe AND f.bar_time = b.bar_time
        WHERE b.ticker = ? AND b.timeframe = ?
        ORDER BY b.bar_time
        """,
        (ticker, timeframe),
    ).fetchall()
    pattern_rows = conn.execute(
        "SELECT bar_time, GROUP_CONCAT(pattern_name, '|') AS names "
        "FROM patterns WHERE ticker = ? AND timeframe = ? GROUP BY bar_time",
        (ticker, timeframe),
    ).fetchall()
    patterns_by_bar = {row["bar_time"]: row["names"] for row in pattern_rows}

    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["bar_time", "open", "high", "low", "close", "volume", *FEATURE_COLUMNS, "patterns_detected"]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            record = {key: row[key] for key in fieldnames if key != "patterns_detected"}
            record["patterns_detected"] = patterns_by_bar.get(row["bar_time"], "")
            writer.writerow(record)
    return len(rows)


# ---------------------------------------------------------------------------
# Query API - what a future strategy actually calls
# ---------------------------------------------------------------------------

def get_features(ticker: str, timeframe: str, bar_time: str) -> dict[str, Any] | None:
    conn = connect()
    try:
        row = conn.execute(
            "SELECT * FROM features WHERE ticker = ? AND timeframe = ? AND bar_time = ?",
            (ticker, timeframe, bar_time),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recent_patterns(ticker: str, timeframe: str, lookback_bars: int = 20) -> list[dict[str, Any]]:
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT * FROM patterns WHERE ticker = ? AND timeframe = ? "
            "ORDER BY bar_time DESC LIMIT ?",
            (ticker, timeframe, lookback_bars),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def pattern_stats(
    ticker: str, timeframe: str, pattern_name: str, *, since_bar_time: str | None = None
) -> dict[str, Any]:
    """The real point of tracking outcomes: for a given pattern, how many
    times has it fired, and what actually happened 5/10/20 bars later -
    average return and win rate (positive forward return), per horizon.
    Empty/None values mean not enough history yet, not zero.

    since_bar_time optionally restricts this to occurrences on or after
    that date - see pattern_stats_recent_vs_all_time, which is what
    actually answers "is old data here skewing the picture:" more
    history means a bigger, statistically stronger sample, but SPY's own
    character (volatility regime, rate environment) isn't constant over
    2+ years, so a pattern's ALL-TIME average can look solid while its
    RECENT behavior has quietly drifted - comparing both is how you'd
    actually notice that, not by assuming either number alone is
    trustworthy."""
    conn = connect()
    try:
        filter_clause = ""
        params: list[Any] = [ticker, timeframe, pattern_name]
        if since_bar_time:
            filter_clause = " AND bar_time >= ?"
            params.append(since_bar_time)
        total = conn.execute(
            f"SELECT COUNT(*) AS n FROM patterns WHERE ticker = ? AND timeframe = ? AND pattern_name = ?{filter_clause}",
            params,
        ).fetchone()["n"]
        by_horizon = {}
        for horizon in FORWARD_RETURN_HORIZONS:
            horizon_filter = "" if not since_bar_time else " AND p.bar_time >= ?"
            horizon_params = [ticker, timeframe, pattern_name, horizon] + ([since_bar_time] if since_bar_time else [])
            rows = conn.execute(
                f"""
                SELECT po.forward_return_pct FROM pattern_outcomes po
                JOIN patterns p ON p.id = po.pattern_id
                WHERE p.ticker = ? AND p.timeframe = ? AND p.pattern_name = ? AND po.bars_forward = ?{horizon_filter}
                """,
                horizon_params,
            ).fetchall()
            returns = [row["forward_return_pct"] for row in rows]
            if returns:
                by_horizon[horizon] = {
                    "n": len(returns),
                    "avg_return_pct": sum(returns) / len(returns),
                    "win_rate_pct": sum(1 for r in returns if r > 0) / len(returns) * 100,
                }
            else:
                by_horizon[horizon] = None
        return {"pattern_name": pattern_name, "total_occurrences": total, "by_horizon": by_horizon}
    finally:
        conn.close()


def pattern_stats_recent_vs_all_time(
    ticker: str, timeframe: str, pattern_name: str, recent_days: int = 180
) -> dict[str, Any]:
    """Side-by-side all-time vs. recent-window stats for the same
    pattern - the direct tool for "shouldn't 2+ years give a better idea
    of trend, or is that old data stale": if the recent numbers roughly
    agree with all-time, the tendency has held up across regimes and the
    extra history is real statistical power, not noise. If they've
    diverged, the pattern's edge (if any) has likely shifted with the
    market's own character, and the all-time figure alone would have
    been misleading."""
    from datetime import timedelta

    cutoff = (datetime.now() - timedelta(days=recent_days)).date().isoformat()
    return {
        "pattern_name": pattern_name,
        "recent_window_days": recent_days,
        "all_time": pattern_stats(ticker, timeframe, pattern_name),
        "recent": pattern_stats(ticker, timeframe, pattern_name, since_bar_time=cutoff),
    }


# ---------------------------------------------------------------------------
# Collection cycle
# ---------------------------------------------------------------------------

def _ingest_and_process(conn: sqlite3.Connection, ticker: str, timeframe: str, rows: list[tuple]) -> dict[str, int]:
    new_bars = store_bars(conn, ticker, timeframe, rows)
    bars = load_bars(conn, ticker, timeframe)
    if not bars:
        return {"new_bars": new_bars, "features_computed": 0, "patterns_detected": 0}

    existing_feature_times = {
        row["bar_time"]
        for row in conn.execute(
            "SELECT bar_time FROM features WHERE ticker = ? AND timeframe = ?", (ticker, timeframe)
        ).fetchall()
    }
    features_computed = 0
    patterns_detected = 0
    market_condition = None
    for index, bar in enumerate(bars):
        if bar["bar_time"] in existing_feature_times:
            continue
        features = compute_features_for_window(bars, index)
        store_features(conn, ticker, timeframe, bar["bar_time"], features, market_condition)
        features_computed += 1
        pattern_names = detect_patterns_for_bar(bars, features, index)
        if pattern_names:
            patterns_detected += len(store_patterns(conn, ticker, timeframe, bar["bar_time"], pattern_names))
    conn.commit()
    return {"new_bars": new_bars, "features_computed": features_computed, "patterns_detected": patterns_detected}


def run_collection_cycle(ticker: str = "SPY") -> dict[str, Any]:
    """One full incremental update: backfill/extend daily history,
    collect today's intraday bars if the market has traded today,
    compute features + detect patterns for anything new, then backfill
    any pattern outcomes that have now had enough time to play out.
    Every step is INSERT OR IGNORE / only-fills-gaps, so running this
    repeatedly (multiple times a day, or after a gap of days) is always
    safe and never duplicates or recomputes existing data."""
    conn = connect()
    try:
        daily_history = s.get_daily_history(ticker, days=SPY_DAILY_HISTORY_DAYS)
        daily_result = _ingest_and_process(conn, ticker, "daily", _daily_bar_rows(daily_history))

        intraday_result = {"new_bars": 0, "features_computed": 0, "patterns_detected": 0}
        try:
            intraday_bars = s.get_intraday_history(ticker, interval="5min")
        except Exception:
            intraday_bars = []
        if intraday_bars:
            intraday_result = _ingest_and_process(conn, ticker, "5min", _intraday_bar_rows(intraday_bars))

        daily_outcomes = backfill_pattern_outcomes(conn, ticker, "daily")
        intraday_outcomes = backfill_pattern_outcomes(conn, ticker, "5min")

        daily_csv_rows = export_features_csv(conn, ticker, "daily", DAILY_CSV_PATH)
        intraday_csv_rows = export_features_csv(conn, ticker, "5min", INTRADAY_CSV_PATH)

        return {
            "ticker": ticker,
            "daily": daily_result,
            "intraday_5min": intraday_result,
            "outcomes_recorded": daily_outcomes + intraday_outcomes,
            "csv_exported": {"daily_rows": daily_csv_rows, "intraday_rows": intraday_csv_rows},
        }
    finally:
        conn.close()


if __name__ == "__main__":
    import json

    from run_with_env import load_env

    load_env()
    print(json.dumps(run_collection_cycle(), indent=2))
