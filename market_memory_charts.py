"""Renders the standalone market-memory store as Discord-postable charts.

Owner: "I wanna see it visually how all these different things we track
will look before we attach it to anything... I want everything. ema sma
vwap etc. its own charts... so I can track this over short periods long
periods and in-between. make it useful."

Read-only by construction. This module opens market_memory's SQLite file
directly in `mode=ro` and never imports `market_memory` itself, which
matters for a real reason: the chart job runs inside the live
information engine, while `market_memory.connect()` opens read-write,
runs `executescript(SCHEMA)` and sets WAL. Keeping this a pure reader
preserves the isolation invariant documented in
run_market_memory_collection.ps1 - a research-store problem can never
reach into live trading. It also keeps every function here unit-testable
with no Discord, no engine, and no network: read rows -> return dicts,
write PNGs, return markdown.

Five images, chosen so each one answers a question rather than dumping
46 columns into a wall:
  intraday  - what the last completed session actually did (VWAP lives here)
  short     - 30/90 day swing context
  medium    - one year, with the 200-day and cross events
  long      - five years plus full history back to 1994 on a log axis
  coverage  - a tile per tracked feature: current value, sparkline,
              and how many bars actually have it (including the ones
              that are empty, shown as empty rather than hidden)

Three drawing rules that are corrections of real problems, not polish:
  * Series are split on None runs before drawing, so a moving average
    that only becomes valid at bar 200 does not get a straight line
    dragged across the first 199 bars pretending it existed.
  * VWAP is drawn as one polyline per session, never joined across the
    overnight reset, because the reset is the whole point of anchoring.
  * Dense series are decimated min/max per pixel column rather than
    stride-sampled, so a single-bar spike in 8,000 bars survives.
"""

from __future__ import annotations

import hashlib
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "market_memory.db"
CHART_DIR = ROOT / "docs" / "market-memory"

# Bump to force a re-render after changing drawing code - without this a
# rendering fix stays invisible until the next new bar arrives, because
# the job's fingerprint guard would consider the data unchanged.
RENDER_VERSION = "spy-technicals-v2-focused"

MARKET_TZ = ZoneInfo("America/New_York")

WIDTH, HEIGHT = 1600, 1040
PANEL_W, PANEL_H = 735, 375
PANEL_ORIGINS = ((45, 110), (820, 110), (45, 515), (820, 515))

BACKGROUND = "#09111d"
PANEL_FILL = "#0f1b2b"
PANEL_OUTLINE = "#26384d"
GRID = "#243244"
PRICE = "#f4f7fb"
TEXT = "#f8fafc"
MUTED = "#9fb0c3"
FAINT = "#718399"
GREEN = "#22c55e"
RED = "#ef4444"
AMBER = "#f59e0b"
BLUE = "#38bdf8"
VIOLET = "#a78bfa"
WARN = "#fbbf24"

DISCLAIMER = "Research view of stored history - paper research only, not financial advice or a trade instruction."


def open_readonly() -> sqlite3.Connection:
    """Read-only handle on the market-memory database. Raises
    sqlite3.OperationalError when the file is missing or locked - the
    caller is expected to degrade gracefully rather than treat a
    research-store hiccup as a live-system fault."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def load_joined(
    conn: sqlite3.Connection, ticker: str, timeframe: str, limit: int | None = None
) -> list[dict[str, Any]]:
    """Bars LEFT JOINed to their features, oldest-first. LEFT (not inner)
    so bars whose features have not been computed still appear - the
    chart should show the price and leave the indicator blank, not drop
    the bar entirely."""
    query = (
        "SELECT b.bar_time, b.open, b.high, b.low, b.close, b.volume, f.* "
        "FROM bars b LEFT JOIN features f "
        "ON f.ticker = b.ticker AND f.timeframe = b.timeframe AND f.bar_time = b.bar_time "
        "WHERE b.ticker = ? AND b.timeframe = ? ORDER BY b.bar_time"
    )
    rows = [dict(row) for row in conn.execute(query, (ticker, timeframe)).fetchall()]
    return rows[-limit:] if limit else rows


# ---------------------------------------------------------------------------
# Series shaping
# ---------------------------------------------------------------------------

def _column(rows: Sequence[dict[str, Any]], name: str) -> list[float | None]:
    values: list[float | None] = []
    for row in rows:
        value = row.get(name)
        values.append(float(value) if isinstance(value, (int, float)) else None)
    return values


def _segments(values: Sequence[float | None]) -> list[list[tuple[int, float]]]:
    """Contiguous runs of real values, so a polyline is never drawn
    across a None gap. sma_200 is NULL for the first 199 bars; without
    this the line would start at bar 0 as a straight run to bar 200 and
    imply history that does not exist."""
    runs: list[list[tuple[int, float]]] = []
    current: list[tuple[int, float]] = []
    for index, value in enumerate(values):
        if value is None:
            if len(current) > 1:
                runs.append(current)
            current = []
        else:
            current.append((index, float(value)))
    if len(current) > 1:
        runs.append(current)
    return runs


def _session_segments(
    rows: Sequence[dict[str, Any]], values: Sequence[float | None]
) -> list[list[tuple[int, float]]]:
    """Like _segments, but additionally breaks at every session
    boundary. VWAP resets each morning; joining across that reset would
    draw a vertical cliff that misrepresents the anchoring."""
    runs: list[list[tuple[int, float]]] = []
    current: list[tuple[int, float]] = []
    session: str | None = None
    for index, (row, value) in enumerate(zip(rows, values)):
        bar_session = str(row.get("bar_time", ""))[:10]
        if bar_session != session:
            if len(current) > 1:
                runs.append(current)
            current = []
            session = bar_session
        if value is None:
            if len(current) > 1:
                runs.append(current)
            current = []
        else:
            current.append((index, float(value)))
    if len(current) > 1:
        runs.append(current)
    return runs


def _session_boundaries(rows: Sequence[dict[str, Any]]) -> list[int]:
    boundaries: list[int] = []
    session: str | None = None
    for index, row in enumerate(rows):
        bar_session = str(row.get("bar_time", ""))[:10]
        if session is not None and bar_session != session:
            boundaries.append(index)
        session = bar_session
    return boundaries


def _decimate(points: Sequence[tuple[int, float]], columns: int) -> list[tuple[int, float]]:
    """Bucket to roughly one bucket per pixel column, keeping each
    bucket's min AND max. Stride-sampling 8,000 bars into ~650 pixels
    silently deletes real spikes; keeping both extremes preserves the
    envelope, which is how charting libraries handle this."""
    if len(points) <= columns or columns <= 0:
        return list(points)
    bucket_size = len(points) / columns
    result: list[tuple[int, float]] = []
    for column in range(columns):
        start = int(column * bucket_size)
        stop = max(start + 1, int((column + 1) * bucket_size))
        bucket = points[start:stop]
        if not bucket:
            continue
        lowest = min(bucket, key=lambda item: item[1])
        highest = max(bucket, key=lambda item: item[1])
        pair = sorted({lowest, highest}, key=lambda item: item[0])
        result.extend(pair)
    return result


def _display_time(bar_time: str) -> str:
    """Clock label for an intraday bar. The store holds two encodings -
    Robinhood-sourced bars end in 'Z' (UTC), Tradier-sourced ones are
    naive Eastern - so labelling raw text would put the same session
    open at 14:30 for one span and 09:30 for the other. Display only;
    nothing here changes what is stored."""
    text = str(bar_time)
    if len(text) <= 10:
        return text
    body = text[:19]
    try:
        parsed = datetime.strptime(body, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return text[11:16]
    if text.endswith("Z"):
        parsed = parsed.replace(tzinfo=timezone.utc).astimezone(MARKET_TZ)
    return parsed.strftime("%H:%M")


def _display_date(bar_time: str, *, year_only: bool = False) -> str:
    text = str(bar_time)[:10]
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return text
    return parsed.strftime("%Y") if year_only else parsed.strftime("%m/%d/%y")


# ---------------------------------------------------------------------------
# Panel drawing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Series:
    label: str
    color: str
    values: Sequence[float | None]
    width: int = 2
    segmenter: Callable[[Sequence[float | None]], list[list[tuple[int, float]]]] | None = None


@dataclass(frozen=True)
class HLine:
    value: float
    color: str
    label: str = ""


def _panel_frame(draw: Any, origin: tuple[int, int], title: str, subtitle: str, fonts: dict[str, Any]) -> None:
    x, y = origin
    draw.rounded_rectangle(
        (x, y, x + PANEL_W, y + PANEL_H), radius=14, fill=PANEL_FILL, outline=PANEL_OUTLINE, width=2
    )
    draw.text((x + 16, y + 12), title, fill=TEXT, font=fonts["panel_title"])
    if subtitle:
        draw.text((x + 16, y + 36), subtitle, fill=MUTED, font=fonts["small"])


def _empty_panel(draw: Any, origin: tuple[int, int], title: str, message: str, fonts: dict[str, Any]) -> None:
    _panel_frame(draw, origin, title, "", fonts)
    x, y = origin
    draw.text((x + 20, y + PANEL_H // 2 - 8), message, fill=WARN, font=fonts["normal"])


def _draw_panel(
    draw: Any,
    origin: tuple[int, int],
    title: str,
    subtitle: str,
    fonts: dict[str, Any],
    series: Sequence[Series],
    *,
    n_points: int,
    hlines: Sequence[HLine] = (),
    log_scale: bool = False,
    value_fmt: str = "${:,.2f}",
    x_labels: Sequence[tuple[int, str]] = (),
    dividers: Sequence[int] = (),
    bars: Sequence[float | None] | None = None,
    bar_colors: Sequence[str] | None = None,
) -> None:
    """One chart panel. Every series is segment-split before drawing, so
    None gaps never become straight lines."""
    real = [v for s in series for v in s.values if v is not None]
    if bars:
        real.extend(v for v in bars if v is not None)
    real.extend(line.value for line in hlines)
    if len(real) < 2 or n_points < 2:
        _empty_panel(draw, origin, title, "Insufficient history for this window.", fonts)
        return

    x0, y0 = origin
    plot_left = x0 + 74
    plot_right = x0 + PANEL_W - 18
    plot_top = y0 + 62
    # Leaves two clear rows beneath the plot: axis labels, then legend.
    # Sharing one row made them overlap illegibly.
    plot_bottom = y0 + PANEL_H - 48
    plot_w = plot_right - plot_left
    plot_h = plot_bottom - plot_top

    low, high = min(real), max(real)
    if log_scale:
        low = max(low, 0.01)
        high = max(high, low * 1.0001)
        span_low, span_high = math.log10(low), math.log10(high)
    else:
        pad = max((high - low) * 0.08, abs(high) * 0.001, 0.01)
        span_low, span_high = low - pad, high + pad
    span = max(span_high - span_low, 1e-9)

    def to_y(value: float) -> int:
        scaled = math.log10(max(value, 0.01)) if log_scale else value
        return int(plot_top + (span_high - scaled) / span * plot_h)

    def to_x(index: int) -> int:
        return int(plot_left + index / max(n_points - 1, 1) * plot_w)

    _panel_frame(draw, origin, title, subtitle, fonts)

    for step in range(5):
        scaled = span_high - span / 4 * step
        value = (10 ** scaled) if log_scale else scaled
        y = to_y(value)
        draw.line((plot_left, y, plot_right, y), fill=GRID, width=1)
        draw.text((x0 + 8, y - 7), value_fmt.format(value), fill=FAINT, font=fonts["tiny"])

    for index in dividers:
        x = to_x(index)
        draw.line((x, plot_top, x, plot_bottom), fill="#1d2b3d", width=1)

    if bars:
        baseline = to_y(max(min(real), 0.0) if min(real) >= 0 else 0.0)
        slot = max(plot_w / max(n_points, 1), 1.0)
        for index, value in enumerate(bars):
            if value is None:
                continue
            x = to_x(index)
            color = (bar_colors[index] if bar_colors and index < len(bar_colors) else BLUE) or BLUE
            top, bottom = sorted((baseline, to_y(value)))
            draw.rectangle((x - slot / 2 + 0.5, top, x + slot / 2 - 0.5, bottom), fill=color)

    for line in hlines:
        y = to_y(line.value)
        for x in range(plot_left, plot_right, 10):
            draw.line((x, y, min(x + 5, plot_right), y), fill=line.color, width=1)
        if line.label:
            draw.text((plot_right - 52, y - 14), line.label, fill=line.color, font=fonts["tiny"])

    for item in series:
        segmenter = item.segmenter or _segments
        for run in segmenter(item.values):
            points = _decimate(run, plot_w)
            if len(points) < 2:
                continue
            draw.line([(to_x(i), to_y(v)) for i, v in points], fill=item.color, width=item.width, joint="curve")

    for index, label in x_labels:
        if 0 <= index < n_points:
            draw.text((to_x(index) - 22, plot_bottom + 6), label, fill=FAINT, font=fonts["tiny"])

    legend_x = plot_left
    for item in series:
        if not item.label:
            continue
        draw.line((legend_x, plot_bottom + 32, legend_x + 16, plot_bottom + 32), fill=item.color, width=3)
        draw.text((legend_x + 21, plot_bottom + 25), item.label, fill=MUTED, font=fonts["tiny"])
        legend_x += 26 + int(len(item.label) * 6.1)


def _fonts() -> dict[str, Any]:
    from PIL import ImageFont

    return {
        "title": ImageFont.load_default(size=28),
        "subtitle": ImageFont.load_default(size=19),
        "panel_title": ImageFont.load_default(size=19),
        "normal": ImageFont.load_default(size=18),
        "small": ImageFont.load_default(size=15),
        "tiny": ImageFont.load_default(size=13),
    }


def _canvas(title: str, subtitle: str) -> tuple[Any, Any, dict[str, Any]]:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    fonts = _fonts()
    draw.text((45, 24), title, fill=TEXT, font=fonts["title"])
    draw.text((45, 62), subtitle, fill=MUTED, font=fonts["subtitle"])
    return image, draw, fonts


def _finish(image: Any, draw: Any, fonts: dict[str, Any], footer: str, output: Path) -> Path:
    draw.text((45, HEIGHT - 62), footer, fill=MUTED, font=fonts["small"])
    draw.text((45, HEIGHT - 34), DISCLAIMER, fill=FAINT, font=fonts["tiny"])
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return output


def _spaced_labels(rows: Sequence[dict[str, Any]], count: int, *, intraday: bool, year_only: bool = False) -> list[tuple[int, str]]:
    if not rows:
        return []
    step = max(len(rows) // max(count, 1), 1)
    labels = []
    for index in range(0, len(rows), step):
        bar_time = rows[index].get("bar_time", "")
        labels.append((index, _display_time(bar_time) if intraday else _display_date(bar_time, year_only=year_only)))
    return labels


def _macd_bar_colors(rows: Sequence[dict[str, Any]]) -> list[str]:
    """Colour the MACD histogram by the STORED macd_color, not a fresh
    recomputation - the point of this view is to show what the store
    actually tracked."""
    mapping = {
        "BRIGHT_GREEN": GREEN, "DARK_GREEN": "#15803d",
        "BRIGHT_RED": RED, "DARK_RED": "#991b1b",
    }
    return [mapping.get(str(row.get("macd_color") or ""), FAINT) for row in rows]


# ---------------------------------------------------------------------------
# The five boards
# ---------------------------------------------------------------------------

def render_intraday(rows_5m: Sequence[dict[str, Any]], output: Path) -> Path | None:
    if len(rows_5m) < 2:
        return None
    session = str(rows_5m[-1].get("bar_time", ""))[:10]
    today = [row for row in rows_5m if str(row.get("bar_time", ""))[:10] == session]
    five_day = list(rows_5m[-390:])

    image, draw, fonts = _canvas(
        "SPY TECHNICALS - INTRADAY (5-MINUTE)",
        f"Last COMPLETED session {session} - market memory collects after the close, so this is never a live price.",
    )

    _draw_panel(
        draw, PANEL_ORIGINS[0], f"Session {session}", "close - EMA9 - EMA20 - VWAP", fonts,
        [
            Series("close", PRICE, _column(today, "close"), 3),
            Series("EMA9", BLUE, _column(today, "ema_9")),
            Series("EMA20", VIOLET, _column(today, "ema_20")),
            Series("VWAP", AMBER, _column(today, "vwap"), 3, lambda v: _session_segments(today, v)),
        ],
        n_points=len(today), x_labels=_spaced_labels(today, 6, intraday=True),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[1], "Last 5 sessions", "VWAP re-anchors each morning (dividers = session opens)", fonts,
        [
            Series("close", PRICE, _column(five_day, "close"), 2),
            Series("VWAP", AMBER, _column(five_day, "vwap"), 2, lambda v: _session_segments(five_day, v)),
        ],
        n_points=len(five_day), dividers=_session_boundaries(five_day),
        x_labels=[(i, _display_date(five_day[i]["bar_time"])) for i in _session_boundaries(five_day)],
    )
    _draw_panel(
        draw, PANEL_ORIGINS[2], "Momentum - 5 sessions", "RSI(14) with 30/70 guides", fonts,
        [Series("RSI14", VIOLET, _column(five_day, "rsi_14"), 2)],
        n_points=len(five_day), value_fmt="{:,.0f}",
        hlines=[HLine(70, RED, "70"), HLine(30, GREEN, "30")],
    )
    _draw_panel(
        draw, PANEL_ORIGINS[3], "Trend strength - 5 sessions", "ADX(14) with +DI / -DI", fonts,
        [
            Series("ADX", AMBER, _column(five_day, "adx_14"), 3),
            Series("+DI", GREEN, _column(five_day, "plus_di_14")),
            Series("-DI", RED, _column(five_day, "minus_di_14")),
        ],
        n_points=len(five_day), value_fmt="{:,.0f}",
        hlines=[HLine(25, MUTED, "25"), HLine(20, FAINT, "20")],
    )
    return _finish(image, draw, fonts, f"{len(today)} bars this session - {len(five_day)} bars across 5 sessions.", output)


def render_short(rows_daily: Sequence[dict[str, Any]], output: Path) -> Path | None:
    if len(rows_daily) < 2:
        return None
    d30, d90 = list(rows_daily[-30:]), list(rows_daily[-90:])
    image, draw, fonts = _canvas(
        "SPY TECHNICALS - SHORT (30 / 90 DAILY BARS)",
        "Swing context: fast moving averages, Bollinger envelope, MACD and momentum.",
    )
    _draw_panel(
        draw, PANEL_ORIGINS[0], "Last 30 sessions", "close - EMA9 - EMA20 - SMA20", fonts,
        [
            Series("close", PRICE, _column(d30, "close"), 3),
            Series("EMA9", BLUE, _column(d30, "ema_9")),
            Series("EMA20", VIOLET, _column(d30, "ema_20")),
            Series("SMA20", AMBER, _column(d30, "sma_20")),
        ],
        n_points=len(d30), x_labels=_spaced_labels(d30, 5, intraday=False),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[1], "Last 90 sessions", "close with Bollinger(20,2) and SMA50", fonts,
        [
            Series("BB upper", "#334d6e", _column(d90, "bb_upper")),
            Series("BB lower", "#334d6e", _column(d90, "bb_lower")),
            Series("close", PRICE, _column(d90, "close"), 3),
            Series("SMA50", AMBER, _column(d90, "sma_50")),
        ],
        n_points=len(d90), x_labels=_spaced_labels(d90, 5, intraday=False),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[2], "MACD - 90 sessions", "histogram coloured by the stored macd_color", fonts,
        [
            Series("MACD", BLUE, _column(d90, "macd_line")),
            Series("signal", AMBER, _column(d90, "macd_signal")),
        ],
        n_points=len(d90), value_fmt="{:,.2f}",
        bars=_column(d90, "macd_histogram"), bar_colors=_macd_bar_colors(d90),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[3], "Momentum and strength - 90 sessions", "RSI(14) and ADX(14)", fonts,
        [
            Series("RSI14", VIOLET, _column(d90, "rsi_14")),
            Series("ADX14", AMBER, _column(d90, "adx_14")),
        ],
        n_points=len(d90), value_fmt="{:,.0f}",
        hlines=[HLine(70, RED, "70"), HLine(30, GREEN, "30"), HLine(25, MUTED, "ADX25")],
    )
    return _finish(image, draw, fonts, f"{len(d90)} daily bars through {_display_date(d90[-1]['bar_time'])}.", output)


def render_medium(rows_daily: Sequence[dict[str, Any]], output: Path) -> Path | None:
    if len(rows_daily) < 2:
        return None
    year = list(rows_daily[-252:])
    image, draw, fonts = _canvas(
        "SPY TECHNICALS - MEDIUM (1 YEAR OF DAILY BARS)",
        "Full-cycle context: the 200-day, volatility relative to itself, and how long structure has persisted.",
    )
    _draw_panel(
        draw, PANEL_ORIGINS[0], "One year", "close - SMA20 - SMA50 - SMA200", fonts,
        [
            Series("close", PRICE, _column(year, "close"), 3),
            Series("SMA20", BLUE, _column(year, "sma_20")),
            Series("SMA50", AMBER, _column(year, "sma_50")),
            Series("SMA200", RED, _column(year, "sma_200")),
        ],
        n_points=len(year), x_labels=_spaced_labels(year, 6, intraday=False),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[1], "Volatility", "ATR percentile - where volatility sits against its own history", fonts,
        [Series("ATR %ile", AMBER, _column(year, "atr_percentile"), 3)],
        n_points=len(year), value_fmt="{:,.0f}",
        hlines=[HLine(80, RED, "80"), HLine(50, MUTED, "50"), HLine(20, GREEN, "20")],
    )
    _draw_panel(
        draw, PANEL_ORIGINS[2], "Bollinger width and volume", "squeeze / expansion with relative volume", fonts,
        [
            Series("BB width %", BLUE, _column(year, "bb_width_pct"), 2),
            Series("rel volume", VIOLET, _column(year, "relative_volume"), 2),
        ],
        n_points=len(year), value_fmt="{:,.1f}",
        hlines=[HLine(2.0, RED, "2x vol")],
    )
    run = _column(year, "trend_run_length")
    _draw_panel(
        draw, PANEL_ORIGINS[3], "Structure run length", "consecutive higher-high+higher-low (+) or lower-low (-) bars", fonts,
        [], n_points=len(year), value_fmt="{:,.0f}",
        bars=run,
        bar_colors=[GREEN if (v or 0) > 0 else (RED if (v or 0) < 0 else FAINT) for v in run],
        hlines=[HLine(0, MUTED, "")],
    )
    return _finish(image, draw, fonts, f"{len(year)} daily bars through {_display_date(year[-1]['bar_time'])}.", output)


def render_long(rows_daily: Sequence[dict[str, Any]], output: Path) -> Path | None:
    if len(rows_daily) < 2:
        return None
    five_year = list(rows_daily[-1260:])
    full = list(rows_daily)

    image, draw, fonts = _canvas(
        "SPY TECHNICALS - LONG (5 YEAR AND FULL HISTORY)",
        f"Full stored history {_display_date(full[0]['bar_time'])} to {_display_date(full[-1]['bar_time'])} - {len(full):,} daily bars.",
    )
    _draw_panel(
        draw, PANEL_ORIGINS[0], "Five years", "close - SMA50 - SMA200", fonts,
        [
            Series("close", PRICE, _column(five_year, "close"), 2),
            Series("SMA50", AMBER, _column(five_year, "sma_50")),
            Series("SMA200", RED, _column(five_year, "sma_200")),
        ],
        n_points=len(five_year), x_labels=_spaced_labels(five_year, 6, intraday=False),
    )
    _draw_panel(
        draw, PANEL_ORIGINS[1], "Full history (log scale)", "a linear axis would flatten the first 15 years into a line", fonts,
        [
            Series("close", PRICE, _column(full, "close"), 2),
            Series("SMA200", RED, _column(full, "sma_200")),
        ],
        n_points=len(full), log_scale=True,
        x_labels=_spaced_labels(full, 6, intraday=False, year_only=True),
    )
    above = _column(full, "price_above_sma_200")
    window, regime = 252, []
    for index in range(len(above)):
        chunk = [v for v in above[max(0, index - window + 1):index + 1] if v is not None]
        regime.append(sum(chunk) / len(chunk) * 100 if chunk else None)
    _draw_panel(
        draw, PANEL_ORIGINS[2], "Regime oscillator (full history)", "share of the trailing 252 bars closing above the 200-day", fonts,
        [Series("% above SMA200", GREEN, regime, 2)],
        n_points=len(full), value_fmt="{:,.0f}",
        hlines=[HLine(50, MUTED, "50%")],
        x_labels=_spaced_labels(full, 6, intraday=False, year_only=True),
    )
    golden = [i for i, row in enumerate(full) if row.get("golden_cross")]
    death = [i for i, row in enumerate(full) if row.get("death_cross")]
    _draw_panel(
        draw, PANEL_ORIGINS[3], "Cross events (full history)",
        f"{len(golden)} golden - {len(death)} death, plotted at the closing price", fonts,
        [Series("close", "#334d6e", _column(full, "close"), 1)],
        n_points=len(full), log_scale=True,
        x_labels=_spaced_labels(full, 6, intraday=False, year_only=True),
    )
    _mark_events(draw, PANEL_ORIGINS[3], full, golden, death)
    return _finish(image, draw, fonts, f"{len(full):,} daily bars - {len(five_year):,} in the 5-year panel.", output)


def _mark_events(
    draw: Any, origin: tuple[int, int], rows: Sequence[dict[str, Any]], golden: Sequence[int], death: Sequence[int]
) -> None:
    """Overlay cross markers on the already-drawn log-scale panel."""
    closes = [row.get("close") for row in rows]
    real = [float(c) for c in closes if isinstance(c, (int, float))]
    if len(real) < 2:
        return
    x0, y0 = origin
    plot_left, plot_right = x0 + 74, x0 + PANEL_W - 18
    plot_top, plot_bottom = y0 + 62, y0 + PANEL_H - 34
    low, high = max(min(real), 0.01), max(real)
    span_low, span_high = math.log10(low), math.log10(max(high, low * 1.0001))
    span = max(span_high - span_low, 1e-9)
    for indices, color in ((golden, GREEN), (death, RED)):
        for index in indices:
            value = closes[index]
            if not isinstance(value, (int, float)):
                continue
            x = int(plot_left + index / max(len(rows) - 1, 1) * (plot_right - plot_left))
            y = int(plot_top + (span_high - math.log10(max(float(value), 0.01))) / span * (plot_bottom - plot_top))
            draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=color)


COVERAGE_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Trend", ("sma_20", "sma_50", "sma_200", "ema_9", "ema_20", "ema_50", "ema_200")),
    ("Momentum", ("rsi_14", "macd_line", "macd_signal", "macd_histogram", "macd_color")),
    ("Strength", ("adx_14", "plus_di_14", "minus_di_14", "trend_strength", "trend_direction_di")),
    ("Volatility", ("atr_14", "atr_percentile", "bb_upper", "bb_mid", "bb_lower", "bb_width_pct")),
    ("Session", ("vwap", "relative_volume", "gap_pct", "trend_run_length")),
    ("Structure", ("inside_bar", "outside_bar", "nr7", "higher_high", "higher_low", "lower_high", "lower_low")),
    ("Regime", ("golden_cross", "death_cross", "price_above_sma_200", "price_above_ema_200",
                "short_term_trend", "medium_term_trend", "long_term_trend", "trend_label", "market_condition")),
)


def render_coverage(
    conn: sqlite3.Connection, ticker: str, rows_daily: Sequence[dict[str, Any]],
    rows_5m: Sequence[dict[str, Any]], output: Path
) -> Path | None:
    """A tile per tracked feature: what it reads right now, a sparkline,
    and how many bars actually carry it. Unpopulated columns render
    greyed and say so rather than being quietly omitted - market_condition
    is genuinely never written by the collection cycle, and hiding that
    would misrepresent what is tracked."""
    if not rows_daily:
        return None
    image, draw, fonts = _canvas(
        "SPY TECHNICALS - WHAT THE STORE ACTUALLY TRACKS",
        "Every feature column, its latest value, a 120-bar sparkline, and real coverage. Greyed = never populated.",
    )
    counts = {}
    for timeframe in ("daily", "5min"):
        row = conn.execute(
            f"SELECT COUNT(*) AS n, {', '.join(f'COUNT({name}) AS c_{name}' for _, names in COVERAGE_GROUPS for name in names)} "
            "FROM features WHERE ticker = ? AND timeframe = ?",
            (ticker, timeframe),
        ).fetchone()
        counts[timeframe] = dict(row) if row else {}

    latest = rows_daily[-1]
    latest_intraday = rows_5m[-1] if rows_5m else {}
    spark_rows = list(rows_daily[-120:])
    spark_intraday = list(rows_5m[-120:])
    tile_w, tile_h = 300, 74
    x, y = 45, 110
    column_top = y

    def new_column(header: str) -> None:
        nonlocal x, y
        x += tile_w + 14
        y = column_top
        draw.text((x, y), header, fill=AMBER, font=fonts["small"])
        y += 22

    for group, names in COVERAGE_GROUPS:
        # Never strand a group header at the foot of a column with no
        # room for even one tile beneath it.
        if y + 22 + tile_h > HEIGHT - 90:
            new_column(group.upper())
        else:
            draw.text((x, y), group.upper(), fill=AMBER, font=fonts["small"])
            y += 22
        for name in names:
            if y + tile_h > HEIGHT - 90:
                new_column(f"{group.upper()} (cont.)")
            _coverage_tile(
                draw, (x, y), name, latest, latest_intraday,
                spark_rows, spark_intraday, counts, fonts,
            )
            y += tile_h + 6
        y += 8

    total_daily = counts.get("daily", {}).get("n", 0)
    total_5m = counts.get("5min", {}).get("n", 0)
    return _finish(
        image, draw, fonts,
        f"Coverage measured over {total_daily:,} daily and {total_5m:,} 5-minute feature rows.",
        output,
    )


def _coverage_tile(
    draw: Any, origin: tuple[int, int], name: str, latest: dict[str, Any],
    latest_intraday: dict[str, Any], spark_rows: Sequence[dict[str, Any]],
    spark_intraday: Sequence[dict[str, Any]], counts: dict[str, dict[str, Any]],
    fonts: dict[str, Any]
) -> None:
    x, y = origin
    daily = counts.get("daily", {})
    intraday = counts.get("5min", {})
    populated_daily = daily.get(f"c_{name}", 0) or 0
    populated_5m = intraday.get(f"c_{name}", 0) or 0
    dead = populated_daily == 0 and populated_5m == 0

    # An intraday-only feature (vwap) has no daily value by design -
    # read it from the 5-minute side instead of rendering a bare "-"
    # that looks like missing data.
    intraday_only = populated_daily == 0 and populated_5m > 0
    if intraday_only:
        latest = latest_intraday
        spark_rows = spark_intraday

    draw.rounded_rectangle(
        (x, y, x + 292, y + 68), radius=8,
        fill="#111c2b" if not dead else "#141821",
        outline="#233247" if not dead else "#20242c", width=1,
    )
    draw.text((x + 10, y + 7), name, fill=MUTED if not dead else "#4b5563", font=fonts["small"])

    value = latest.get(name)
    if dead:
        shown = "never populated"
    elif isinstance(value, (int, float)):
        shown = f"{value:,.2f}" if abs(float(value)) < 10000 else f"{value:,.0f}"
    elif value:
        shown = str(value)[:26]
    else:
        shown = "-"
    draw.text((x + 10, y + 28), shown, fill=TEXT if not dead else "#4b5563", font=fonts["normal"])

    coverage = f"daily {populated_daily:,} - 5m {populated_5m:,}"
    if intraday_only:
        coverage += "  (5-min only)"
    draw.text((x + 10, y + 50), coverage, fill=FAINT if not dead else "#3f4753", font=fonts["tiny"])

    values = [v for v in _column(spark_rows, name)]
    real = [v for v in values if v is not None]
    if len(real) >= 2 and not dead:
        low, high = min(real), max(real)
        span = max(high - low, 1e-9)
        sx, sy, sw, sh = x + 196, y + 26, 86, 34
        for run in _segments(values):
            if len(run) < 2:
                continue
            draw.line(
                [(sx + int(i / max(len(values) - 1, 1) * sw), sy + sh - int((v - low) / span * sh)) for i, v in run],
                fill=BLUE, width=1,
            )


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def render_all(
    conn: sqlite3.Connection, ticker: str = "SPY", out_dir: Path | None = None
) -> list[tuple[str, Path, str]]:
    """Render readable, one-purpose technical charts.

    The original boards deliberately collected many indicators, but each
    image contained four panels and was impractical on a phone.  We still
    calculate from the same read-only stored bars; this publisher simply
    promotes the useful individual panels into their own Discord images.
    The coverage matrix is intentionally left in the summary card rather
    than posted as a tiny, unreadable table image.
    """
    out_dir = out_dir or CHART_DIR
    rows_daily = load_joined(conn, ticker, "daily")
    rows_5m = load_joined(conn, ticker, "5min")
    out_dir.mkdir(parents=True, exist_ok=True)
    source_paths = {
        "intraday": out_dir / ".spy-technicals-intraday-board.png",
        "short": out_dir / ".spy-technicals-short-board.png",
        "medium": out_dir / ".spy-technicals-medium-board.png",
        "long": out_dir / ".spy-technicals-long-board.png",
    }
    rendered = {
        "intraday": render_intraday(rows_5m, source_paths["intraday"]),
        "short": render_short(rows_daily, source_paths["short"]),
        "medium": render_medium(rows_daily, source_paths["medium"]),
        "long": render_long(rows_daily, source_paths["long"]),
    }
    requests = (
        ("session-price", "intraday", 0, "📈 **SPY session price & VWAP** — last completed 5-minute session; not live."),
        ("intraday-momentum", "intraday", 2, "📉 **SPY intraday momentum** — RSI(14) over the last five completed sessions."),
        ("short-trend", "short", 0, "📊 **SPY short trend** — 30 sessions: close, EMA9, EMA20, and SMA20."),
        ("macd", "short", 2, "〽️ **SPY MACD** — 90 daily sessions; stored MACD and signal only."),
        ("year-trend", "medium", 0, "🗓️ **SPY one-year trend** — close versus SMA20, SMA50, and SMA200."),
        ("volatility", "medium", 1, "🌡️ **SPY volatility** — one-year ATR percentile from stored daily bars."),
        ("five-year-trend", "long", 0, "🏔️ **SPY five-year trend** — close versus SMA50 and SMA200."),
        ("full-history", "long", 1, "🧭 **SPY full history** — log-scale close and SMA200 from the research store."),
    )
    boards: list[tuple[str, Path, str]] = []
    for key, source_key, panel_index, caption in requests:
        source = rendered[source_key]
        if source is None:
            continue
        output = out_dir / f"spy-technicals-{key}.png"
        _extract_panel(source, panel_index, output)
        boards.append((key, output, caption))
    for source in source_paths.values():
        try:
            source.unlink()
        except FileNotFoundError:
            pass
    return boards


def _extract_panel(source: Path, panel_index: int, output: Path) -> Path:
    """Turn one board quadrant into a large, phone-readable chart image."""
    from PIL import Image

    if not 0 <= panel_index < len(PANEL_ORIGINS):
        raise ValueError(f"unknown panel index {panel_index}")
    x, y = PANEL_ORIGINS[panel_index]
    with Image.open(source) as image:
        panel = image.crop((x, y, x + PANEL_W, y + PANEL_H))
        enlarged = panel.resize((PANEL_W * 2, PANEL_H * 2), Image.Resampling.LANCZOS)
        output.parent.mkdir(parents=True, exist_ok=True)
        enlarged.save(output, format="PNG", optimize=True)
    return output


FORWARD_HORIZONS = (5, 10, 20)


def _base_rate(closes: Sequence[float], horizon: int) -> dict[str, float] | None:
    returns = [
        (closes[i + horizon] - closes[i]) / closes[i] * 100
        for i in range(len(closes) - horizon)
        if closes[i]
    ]
    if not returns:
        return None
    return {
        "n": len(returns),
        "avg": sum(returns) / len(returns),
        "win": sum(1 for value in returns if value > 0) / len(returns) * 100,
    }


def _pattern_edges(
    conn: sqlite3.Connection, ticker: str, closes: Sequence[float], horizon: int = 20, min_n: int = 100
) -> list[dict[str, Any]]:
    """Every daily pattern's forward performance expressed as edge over
    the unconditional base rate. Reimplemented in SQL here rather than
    calling market_memory.pattern_stats, because that opens the database
    read-write and this module is deliberately a pure reader."""
    base = _base_rate(closes, horizon)
    if not base:
        return []
    rows = conn.execute(
        """
        SELECT p.pattern_name AS name, p.category AS category,
               COUNT(*) AS n,
               AVG(po.forward_return_pct) AS avg_return,
               AVG(CASE WHEN po.forward_return_pct > 0 THEN 1.0 ELSE 0.0 END) * 100 AS win_rate
        FROM patterns p JOIN pattern_outcomes po ON po.pattern_id = p.id
        WHERE p.ticker = ? AND p.timeframe = 'daily' AND po.bars_forward = ?
        GROUP BY p.pattern_name, p.category
        """,
        (ticker, horizon),
    ).fetchall()
    edges = []
    for row in rows:
        if row["n"] < min_n:
            continue
        edges.append({
            "name": row["name"],
            "category": row["category"],
            "n": row["n"],
            "edge_avg": row["avg_return"] - base["avg"],
            "edge_win": row["win_rate"] - base["win"],
        })
    edges.sort(key=lambda item: item["edge_avg"], reverse=True)
    return edges


def summarize(conn: sqlite3.Connection, ticker: str = "SPY") -> dict[str, Any]:
    """Every number the summary card needs, in one read."""
    rows_daily = load_joined(conn, ticker, "daily")
    rows_5m = load_joined(conn, ticker, "5min")
    if not rows_daily:
        return {"empty": True}

    latest = rows_daily[-1]
    closes = [float(r["close"]) for r in rows_daily if isinstance(r.get("close"), (int, float))]

    windows = {}
    for label, size in (("5d", 5), ("20d", 20), ("60d", 60), ("252d", 252), ("all", len(rows_daily))):
        chunk = rows_daily[-size:]
        if len(chunk) < 2:
            continue
        first_close, last_close = chunk[0].get("close"), chunk[-1].get("close")
        adx_values = [v for v in _column(chunk, "adx_14") if v is not None]
        above = [v for v in _column(chunk, "price_above_sma_200") if v is not None]
        windows[label] = {
            "bars": len(chunk),
            "change_pct": ((last_close - first_close) / first_close * 100) if first_close else None,
            "avg_adx": (sum(adx_values) / len(adx_values)) if adx_values else None,
            "pct_above_sma200": (sum(above) / len(above) * 100) if above else None,
        }

    session_rows: list[dict[str, Any]] = []
    if rows_5m:
        session = str(rows_5m[-1]["bar_time"])[:10]
        session_rows = [r for r in rows_5m if str(r["bar_time"])[:10] == session]

    session_info = None
    if session_rows:
        vwaps = [v for v in _column(session_rows, "vwap") if v is not None]
        session_closes = [float(r["close"]) for r in session_rows if isinstance(r.get("close"), (int, float))]
        above_vwap = sum(
            1 for r in session_rows
            if isinstance(r.get("close"), (int, float)) and isinstance(r.get("vwap"), (int, float))
            and r["close"] > r["vwap"]
        )
        session_info = {
            "date": str(session_rows[-1]["bar_time"])[:10],
            "bars": len(session_rows),
            "vwap": vwaps[-1] if vwaps else None,
            "close": session_closes[-1] if session_closes else None,
            "high": max(session_closes) if session_closes else None,
            "low": min(session_closes) if session_closes else None,
            "above_vwap": above_vwap,
        }

    coverage = {}
    for timeframe in ("daily", "5min"):
        row = conn.execute(
            "SELECT COUNT(*) AS n, MIN(bar_time) AS first, MAX(bar_time) AS last "
            "FROM bars WHERE ticker = ? AND timeframe = ?",
            (ticker, timeframe),
        ).fetchone()
        coverage[timeframe] = dict(row) if row else {}
    sessions = conn.execute(
        "SELECT COUNT(DISTINCT substr(bar_time, 1, 10)) AS n FROM bars WHERE ticker = ? AND timeframe = '5min'",
        (ticker,),
    ).fetchone()["n"]

    pattern_totals = conn.execute(
        "SELECT COUNT(*) AS patterns FROM patterns WHERE ticker = ?", (ticker,)
    ).fetchone()["patterns"]
    outcome_totals = conn.execute(
        "SELECT COUNT(*) AS outcomes FROM pattern_outcomes po "
        "JOIN patterns p ON p.id = po.pattern_id WHERE p.ticker = ?",
        (ticker,),
    ).fetchone()["outcomes"]
    on_latest = [
        row["pattern_name"]
        for row in conn.execute(
            "SELECT pattern_name FROM patterns WHERE ticker = ? AND timeframe = 'daily' AND bar_time = ? "
            "ORDER BY pattern_name",
            (ticker, latest["bar_time"]),
        ).fetchall()
    ]

    return {
        "empty": False,
        "ticker": ticker,
        "latest": latest,
        "windows": windows,
        "session": session_info,
        "coverage": coverage,
        "sessions": sessions,
        "base_rate": {h: _base_rate(closes, h) for h in FORWARD_HORIZONS},
        "edges": _pattern_edges(conn, ticker, closes),
        "patterns_total": pattern_totals,
        "outcomes_total": outcome_totals,
        "patterns_on_latest": on_latest,
    }


def _fmt(value: Any, spec: str = "{:,.2f}", dash: str = "-") -> str:
    return spec.format(value) if isinstance(value, (int, float)) else dash


def technicals_card_text(summary: dict[str, Any]) -> str:
    """Markdown in the '## title / ### section' shape that
    spy_scanner.discord_card parses into an embed."""
    if summary.get("empty"):
        return "## SPY Technicals - Market Memory\nNo stored history yet."

    latest = summary["latest"]
    daily_cov = summary["coverage"].get("daily", {})
    intraday_cov = summary["coverage"].get("5min", {})
    base20 = summary["base_rate"].get(20)

    lines = [
        f"## {summary['ticker']} Technicals - Market Memory",
        (
            f"**Daily:** {daily_cov.get('n', 0):,} bars "
            f"{_display_date(daily_cov.get('first', ''))} to {_display_date(daily_cov.get('last', ''))} - "
            f"**5-min:** {intraday_cov.get('n', 0):,} bars across {summary['sessions']} sessions"
        ),
        "Read-only view of the standalone market-memory store. No strategy consumes this yet.",
        "### Trend right now",
        (
            f"**Stack:** {latest.get('trend_label') or 'UNKNOWN'}\n"
            f"**Directional:** {latest.get('trend_direction_di') or 'UNKNOWN'} "
            f"(+DI {_fmt(latest.get('plus_di_14'), '{:.1f}')} vs -DI {_fmt(latest.get('minus_di_14'), '{:.1f}')})\n"
            f"**Strength:** {latest.get('trend_strength') or 'UNKNOWN'} "
            f"(ADX {_fmt(latest.get('adx_14'), '{:.1f}')})\n"
            f"**Close:** ${_fmt(latest.get('close'))} - SMA200 ${_fmt(latest.get('sma_200'))} "
            f"({'above' if latest.get('price_above_sma_200') else 'below'}) - "
            f"RSI {_fmt(latest.get('rsi_14'), '{:.1f}')}"
        ),
    ]

    window_lines = []
    for label, data in summary["windows"].items():
        window_lines.append(
            f"**{label}** ({data['bars']:,} bars) {_fmt(data['change_pct'], '{:+.2f}')}% - "
            f"avg ADX {_fmt(data['avg_adx'], '{:.1f}')} - "
            f"{_fmt(data['pct_above_sma200'], '{:.0f}')}% of bars above SMA200"
        )
    if window_lines:
        lines += ["### Trend across horizons", "\n".join(window_lines)]

    lines += [
        "### Volatility",
        (
            f"**ATR(14):** ${_fmt(latest.get('atr_14'))} - "
            f"**percentile:** {_fmt(latest.get('atr_percentile'), '{:.0f}')} of its own 100-bar history\n"
            f"**Bollinger width:** {_fmt(latest.get('bb_width_pct'), '{:.2f}')}% - "
            f"**relative volume:** {_fmt(latest.get('relative_volume'), '{:.2f}')}x"
        ),
    ]

    session = summary.get("session")
    if session:
        distance = None
        if isinstance(session.get("close"), (int, float)) and isinstance(session.get("vwap"), (int, float)) and session["vwap"]:
            distance = (session["close"] - session["vwap"]) / session["vwap"] * 100
        lines += [
            "### Intraday session (completed, not live)",
            (
                f"**{session['date']}** - {session['bars']} five-minute bars\n"
                f"**Session VWAP:** ${_fmt(session.get('vwap'))} - "
                f"close {_fmt(distance, '{:+.2f}')}% vs VWAP\n"
                f"**Bars closing above VWAP:** {session['above_vwap']}/{session['bars']}"
            ),
        ]

    edge_lines = []
    if base20:
        edge_lines.append(
            f"Base rate - simply holding {summary['ticker']} 20 bars: "
            f"{base20['avg']:+.2f}% avg, {base20['win']:.1f}% win (n={base20['n']:,})"
        )
    for edge in summary["edges"][:3] + summary["edges"][-2:]:
        marker = "🟢" if edge["edge_avg"] > 0.05 else ("🔴" if edge["edge_avg"] < -0.05 else "⚪")
        edge_lines.append(
            f"{marker} `{edge['name']}` {edge['edge_avg']:+.2f}% avg edge, "
            f"{edge['edge_win']:+.1f}pp win edge (n={edge['n']:,})"
        )
    edge_lines.append(
        "Shown as edge OVER the base rate on purpose - a raw win rate here is misleading, "
        "since SPY rises most 20-bar windows regardless of any pattern."
    )
    lines += ["### Pattern edge vs base rate", "\n".join(edge_lines)]

    if summary["patterns_on_latest"]:
        lines += ["### On the latest daily bar", ", ".join(f"`{p}`" for p in summary["patterns_on_latest"])]

    lines += [
        "### Coverage",
        (
            f"{summary['patterns_total']:,} patterns detected - {summary['outcomes_total']:,} tracked outcomes\n"
            "**VWAP:** 5-minute only; NULL on daily by design - a session VWAP is meaningless when one bar is the session.\n"
            "**market_condition:** never written by the collection cycle - empty on every row."
        ),
    ]
    return "\n".join(lines)


def data_fingerprint(conn: sqlite3.Connection, ticker: str = "SPY") -> str:
    """Cheap identity of the rendered output. Includes RENDER_VERSION so
    a drawing change forces a re-render immediately instead of waiting
    for the next trading day's bar."""
    parts = [RENDER_VERSION, ticker]
    for timeframe in ("daily", "5min"):
        row = conn.execute(
            "SELECT COUNT(*) AS n, MAX(bar_time) AS latest FROM bars WHERE ticker = ? AND timeframe = ?",
            (ticker, timeframe),
        ).fetchone()
        parts.append(f"{timeframe}:{row['n']}:{row['latest']}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]
