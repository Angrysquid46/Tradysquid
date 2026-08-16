
"""Runtime implementation for owner-approved Discord upgrade batch #44.

The module keeps all changes local-first and read-only. It improves active-universe
market intelligence, rotates weak symbols, cleans Discord cards, expands the
Learning Center, and publishes evidence summaries. It never places brokerage
orders or changes production filters automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import dynamic_universe
import spy_scanner
import outcome_learning
import trade_intelligence

ROOT = Path(__file__).resolve().parent
SUPPLEMENT_PATH = ROOT / "learning_center" / "APPLIED_DECISION_SUPPLEMENT.md"
CHART_DIR = ROOT / "docs" / "tickers"
BATCH_VERSION = "upgrade-batch-44-v1"
JOURNAL_FORMAT_VERSION = "16"

MARKET_BATCH_SIZE = max(4, min(12, int(os.environ.get("ACTIVE_MARKET_BATCH_SIZE", "8"))))
CHART_BATCH_SIZE = max(3, min(12, int(os.environ.get("INTRADAY_CHART_BATCH_SIZE", "6"))))

_ENGINE: Any | None = None
_PUBLIC: Any | None = None
_OPERATIONS: Any | None = None
_ORIGINAL_LEARNING_VERSION = trade_intelligence.learning_version
_ORIGINAL_TRADE_LEARNING_ANALYSIS: Any | None = None
_ORIGINAL_LIBRARY_SECTIONS: Any | None = None
_ORIGINAL_LOAD_LESSONS: Any | None = None
_UNIVERSE_POLICY_INSTALLED = False
_LEARNING_INSTALLED = False
_ENGINE_INSTALLED = False
_STRUCTURE_INSTALLED = False


def _now() -> datetime:
    return datetime.now().astimezone()


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat(timespec="seconds")


def _json_file(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    temporary.replace(path)


def _parse_time(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value or ""))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_now().tzinfo)
    return parsed


def install_universe_policy() -> None:
    """No-op, kept for the frozen updater's call site (run_with_env.py calls
    this directly). Used to patch dynamic_universe.universe_config with
    automated ticker-rotation exclusions - removed along with the rest of
    the ticker-rotation/universe-expansion capability, since this system
    trades SPY exclusively and dynamic_universe.py no longer has a
    universe_config to patch."""
    global _UNIVERSE_POLICY_INSTALLED
    _UNIVERSE_POLICY_INSTALLED = True


def _supplement_lessons() -> dict[str, str]:
    if not SUPPLEMENT_PATH.exists():
        return {}
    pattern = re.compile(
        r"<!-- CHANNEL:(?P<channel>[a-z0-9-]+) -->\s*"
        r"(?P<body>.*?)\s*"
        r"<!-- END:(?P=channel) -->",
        re.DOTALL,
    )
    text = SUPPLEMENT_PATH.read_text(encoding="utf-8")
    return {
        match.group("channel"): match.group("body").strip()
        for match in pattern.finditer(text)
    }


def _combined_learning_version() -> str:
    digest = hashlib.sha256()
    for path in (trade_intelligence.LIBRARY_PATH, SUPPLEMENT_PATH):
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"unavailable")
    return digest.hexdigest()[:12]


def _evidence_value(row: dict[str, Any], key: str, label: str) -> str:
    raw = str(row.get(key) or "").strip()
    return f"{label}: {raw}" if raw else f"{label}: unavailable"


def _applied_checklist(row: dict[str, Any], *, closed: bool) -> str:
    missing = [
        label
        for key, label in (
            ("market_regime", "market regime"),
            ("setup_reason", "setup confirmation"),
            ("delta_at_entry", "delta"),
            ("iv_at_entry", "IV"),
            ("theta_at_entry", "theta"),
            ("open_interest_at_entry", "open interest"),
            ("bid_ask_width_at_entry", "bid/ask width"),
            ("invalidation", "invalidation"),
            ("risk_plan", "risk plan"),
        )
        if not str(row.get(key) or "").strip()
    ]
    lines = [
        "### Applied Decision Checklist",
        (
            "**Context:** "
            + _evidence_value(row, "market_regime", "regime")
            + " · "
            + _evidence_value(row, "setup_reason", "confirmation")
        ),
        (
            "**Contract and volatility:** "
            + " · ".join(
                [
                    _evidence_value(row, "delta_at_entry", "delta"),
                    _evidence_value(row, "theta_at_entry", "theta"),
                    _evidence_value(row, "iv_at_entry", "IV"),
                ]
            )
        ),
        (
            "**Execution quality:** "
            + " · ".join(
                [
                    _evidence_value(row, "open_interest_at_entry", "OI"),
                    _evidence_value(row, "option_volume_at_entry", "volume"),
                    _evidence_value(row, "bid_ask_width_at_entry", "width"),
                ]
            )
        ),
        (
            "**Risk contract:** "
            + _evidence_value(row, "max_risk", "maximum risk")
            + " · "
            + _evidence_value(row, "invalidation", "invalidation")
            + " · "
            + _evidence_value(row, "risk_plan", "plan")
        ),
        (
            "**Evidence gaps:** " + (", ".join(missing) if missing else "none in the required checklist")
        ),
        (
            "**Use:** compare recorded evidence with the Learning Center decision frameworks; "
            "do not rewrite missing entry facts after the outcome is known."
        ),
    ]
    if closed:
        lines.append(
            "**Outcome review:** "
            + _evidence_value(row, "max_favorable_pct", "MFE")
            + " · "
            + _evidence_value(row, "max_adverse_pct", "MAE")
            + " · "
            + _evidence_value(row, "last_signal", "exit signal")
        )
    return "\n".join(lines)


def install_learning_extensions() -> None:
    """Merge the applied supplement into Discord lessons, search, and journals."""
    global _LEARNING_INSTALLED
    global _ORIGINAL_LIBRARY_SECTIONS, _ORIGINAL_LOAD_LESSONS
    global _ORIGINAL_TRADE_LEARNING_ANALYSIS
    if _LEARNING_INSTALLED:
        return

    import journal_contract
    import learning_center_content as learning
    import sync_learning_center

    supplements = _supplement_lessons()
    _ORIGINAL_LIBRARY_SECTIONS = learning.library_sections
    _ORIGINAL_LOAD_LESSONS = sync_learning_center.load_lessons
    _ORIGINAL_TRADE_LEARNING_ANALYSIS = spy_scanner.trade_learning_analysis

    @lru_cache(maxsize=1)
    def merged_library_sections():
        sections = list(_ORIGINAL_LIBRARY_SECTIONS())
        for channel, body in supplements.items():
            if channel in learning.LESSON_BY_CHANNEL:
                sections.extend(learning._parse_sections(channel, body))
        return tuple(sections)

    def merged_load_lessons(path=sync_learning_center.CURRICULUM_PATH):
        lessons = dict(_ORIGINAL_LOAD_LESSONS(path))
        for channel, body in supplements.items():
            if channel in lessons:
                lessons[channel] = f"{lessons[channel]}\n\n{body}".strip()
        return lessons

    def enhanced_trade_learning_analysis(row: dict[str, Any], *, closed: bool = False) -> str:
        base = _ORIGINAL_TRADE_LEARNING_ANALYSIS(row, closed=closed)
        marker = "### Applied Decision Checklist"
        if marker in base:
            return base
        return f"{base}\n{_applied_checklist(row, closed=closed)}"

    learning.library_sections = merged_library_sections
    sync_learning_center.load_lessons = merged_load_lessons
    trade_intelligence.learning_version = _combined_learning_version
    spy_scanner.trade_learning_analysis = enhanced_trade_learning_analysis
    journal_contract.JOURNAL_FORMAT_VERSION = JOURNAL_FORMAT_VERSION
    # NOT added to REQUIRED_ENTRY_MARKERS: create_trade_thread/refresh_trade_thread
    # post entry_alert_text(row, summary_only=True) (the "1 card" trim - Position/
    # Entry Plan/Risk only), which returns before ever calling
    # trade_learning_analysis, so an open trade's journal thread can never contain
    # "### Applied Decision Checklist". Requiring it here made journal-contract
    # verification fail permanently for every open trade that needed a refresh,
    # which was erroring the live options scanner every cycle. Closed trades still
    # get this section via close_alert_text(row, closed=True) and are unaffected -
    # only REQUIRED_ENTRY_MARKERS (open trades) had this stale requirement.
    spy_scanner.DISCORD_FORMAT_VERSION = JOURNAL_FORMAT_VERSION
    _LEARNING_INSTALLED = True


def _engine() -> Any:
    if _ENGINE is None:
        raise RuntimeError("Upgrade batch engine hooks are not installed")
    return _ENGINE


def _tracker() -> Any | None:
    return _engine().discord_tracker()


def _state_json(connection: Any, key: str) -> dict[str, Any]:
    raw = _engine().get_state(connection, key, "{}")
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    return payload if isinstance(payload, dict) else {}


def _set_state_json(connection: Any, key: str, payload: dict[str, Any]) -> None:
    _engine().set_state(connection, key, json.dumps(payload, separators=(",", ":"), default=str))


def _quote_change(quote: dict[str, Any]) -> float | None:
    for key in ("change_percentage", "change_pct", "percent_change"):
        value = spy_scanner.as_float(quote.get(key))
        if value is not None:
            return value
    last = spy_scanner.as_float(quote.get("last"))
    previous = spy_scanner.as_float(quote.get("prevclose") or quote.get("previous_close"))
    if last is not None and previous:
        return (last / previous - 1) * 100
    return None


def _latest_payload(kind: str) -> dict[str, Any]:
    observation = _engine().latest_observation(kind) or {}
    payload = observation.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _universe_rows() -> dict[str, dict[str, Any]]:
    connection = dynamic_universe.connect()
    try:
        rows = connection.execute(
            "SELECT symbol,status,source,score,last_price,average_volume,"
            "options_available,reason,updated_at,expires_at FROM universe"
        ).fetchall()
        return {str(row["symbol"]): dict(row) for row in rows}
    finally:
        connection.close()


def _rotation_batch(
    connection: Any,
    key: str,
    symbols: Iterable[str],
    size: int,
) -> list[str]:
    values = list(dict.fromkeys(str(item).upper() for item in symbols if item))
    if not values:
        return []
    state_key = f"upgrade44:rotation:{key}"
    try:
        cursor = int(_engine().get_state(connection, state_key, "0"))
    except (TypeError, ValueError):
        cursor = 0
    amount = max(1, min(int(size), len(values)))
    batch = [values[(cursor + index) % len(values)] for index in range(amount)]
    _engine().set_state(connection, state_key, str((cursor + amount) % len(values)))
    return batch


def _cleanup_dashboard_cards(
    connection: Any,
    logical_channel: str,
    prefixes: tuple[str, ...],
    keep: set[str],
) -> int:
    tracker = _tracker()
    if not tracker:
        return 0
    channel_id = str(tracker.channels.get(logical_channel) or "")
    if not channel_id:
        return 0
    state = _state_json(connection, "discord_dashboard_state")
    messages = state.setdefault("messages", {})
    hashes = state.setdefault("message_hashes", {})
    removed = 0
    for state_key in list(messages):
        if not any(str(state_key).startswith(prefix) for prefix in prefixes):
            continue
        if state_key in keep:
            continue
        message_id = str(messages.get(state_key) or "")
        if message_id:
            try:
                tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            except spy_scanner.DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        messages.pop(state_key, None)
        hashes.pop(state_key, None)
        removed += 1
    _set_state_json(connection, "discord_dashboard_state", state)
    return removed


def _require_dashboard(
    connection: Any,
    logical_channel: str,
    key: str,
    content: str,
) -> None:
    if not _engine().upsert_dashboard(connection, logical_channel, key, content[:5900]):
        raise RuntimeError(f"Discord did not acknowledge {logical_channel}:{key}")


def _fmt_price(value: Any) -> str:
    number = spy_scanner.as_float(value)
    return "unavailable" if number is None else f"${number:.2f}"


def _fmt_change(value: Any) -> str:
    number = spy_scanner.as_float(value)
    return "change unavailable" if number is None else f"{number:+.2f}%"


def _fmt_number(value: Any, digits: int = 1, suffix: str = "") -> str:
    number = spy_scanner.as_float(value)
    return "unavailable" if number is None else f"{number:.{digits}f}{suffix}"


def active_premarket_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    quotes = spy_scanner.get_quotes(symbols, include_greeks=False) if symbols else {}
    rows = _universe_rows()
    session = _PUBLIC._session_label(spy_scanner.now_ct(), bool(spy_scanner.market_is_open_now()[0]))
    ranked = sorted(
        symbols,
        key=lambda symbol: abs(_quote_change(quotes.get(symbol) or {}) or 0.0),
        reverse=True,
    )
    overview = [
        "## Active-Universe Session Scanner",
        f"**Session:** {session} · **Ticker:** {', '.join(symbols) or spy_scanner.TICKER}",
        "Cards below are generated only for the current universe and disappear when a ticker rotates out.",
        "### Largest current moves",
    ]
    for symbol in ranked[:10]:
        quote = quotes.get(symbol) or {}
        overview.append(
            f"• **{symbol}** · {_fmt_price(quote.get('last'))} · "
            f"{_fmt_change(_quote_change(quote))} · volume "
            f"{int(spy_scanner.as_float(quote.get('volume'), 0) or 0):,}"
        )
    overview.append(f"Updated **{_engine().iso_now()}**. Last/closed quotes may be stale outside market hours.")
    _require_dashboard(connection, "premarket", "premarket-active-overview", "\n".join(overview))

    keep = {"local-engine:premarket-active-overview"}
    failures: list[str] = []
    for symbol in symbols:
        try:
            quote = quotes.get(symbol) or {}
            snapshot = _latest_payload(f"ticker-market:{symbol}")
            news = _latest_payload(f"ticker-news:{symbol}")
            metadata = rows.get(symbol) or {}
            items = news.get("items") if isinstance(news.get("items"), list) else []
            headline = str((items[0] if items else {}).get("title") or "No recent headline recorded.")
            volume = int(spy_scanner.as_float(quote.get("volume"), 0) or 0)
            average_volume = spy_scanner.as_float(metadata.get("average_volume"))
            relative_volume = (
                volume / average_volume
                if average_volume and average_volume > 0
                else spy_scanner.as_float(snapshot.get("relative_volume"))
            )
            content = "\n".join(
                [
                    f"## {symbol} Session Card",
                    f"**Price:** {_fmt_price(quote.get('last') or snapshot.get('price'))} · "
                    f"**Move:** {_fmt_change(_quote_change(quote) if quote else snapshot.get('change_pct'))}",
                    f"**Volume:** {volume:,} · **Relative volume:** {_fmt_number(relative_volume, 2, 'x')}",
                    f"**Direction/regime:** {snapshot.get('regime') or 'awaiting technical refresh'} · "
                    f"**RSI14:** {_fmt_number(snapshot.get('rsi14'), 1)}",
                    f"**Support:** {_fmt_price(snapshot.get('support20'))} · "
                    f"**Resistance:** {_fmt_price(snapshot.get('resistance20'))}",
                    f"**Universe source:** {metadata.get('source') or 'active universe'} · "
                    f"**Rank score:** {_fmt_number(metadata.get('score'), 1)}",
                    f"**Why tracked:** {metadata.get('reason') or 'current active-universe rules'}",
                    f"**Latest event context:** {headline[:500]}",
                    f"Updated **{_engine().iso_now()}**. Informational paper-trading research only.",
                ]
            )
            key = f"premarket:{symbol}"
            _require_dashboard(connection, "premarket", key, content)
            keep.add(f"local-engine:{key}")
        except Exception as exc:
            failures.append(f"{symbol}:{type(exc).__name__}")
    removed = _cleanup_dashboard_cards(
        connection,
        "premarket",
        ("local-engine:premarket:", "local-engine:premarket-live-status"),
        keep,
    )
    _engine().store_observation(
        connection,
        "active-premarket",
        {"symbols": symbols, "failures": failures, "removed": removed, "at": _engine().iso_now()},
    )
    if failures and len(failures) == len(symbols):
        raise RuntimeError("All active premarket cards failed: " + ", ".join(failures))
    return f"{len(symbols) - len(failures)}/{len(symbols)} ticker cards; {removed} stale removed"


def _headline_digest(items: list[dict[str, Any]]) -> str:
    normalized = [
        {
            "title": " ".join(str(item.get("title") or "").split()),
            "url": str(item.get("url") or ""),
            "date": str(item.get("date") or ""),
        }
        for item in items
    ]
    return hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def active_news_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    hashes = _state_json(connection, "upgrade44:headline-hashes")
    keep_news: set[str] = set()
    keep_breaking: set[str] = set()
    completed: list[str] = []
    changed: list[str] = []
    failures: list[str] = []

    for symbol in symbols:
        try:
            items = _engine().fetch_ticker_news(symbol, limit=6)
            _engine().store_observation(
                connection,
                f"ticker-news:{symbol}",
                {"items": items, "checked_at": _engine().iso_now()},
            )
            lines = [
                f"## {symbol} News & Events",
                "Current active-universe headlines. Verify the original publisher before acting.",
            ]
            if items:
                lines.extend(
                    f"• [{item['title']}]({item['url']}) · {item.get('date') or 'time unavailable'}"
                    for item in items
                )
            else:
                lines.append("No matching headline was returned in this check.")
            lines.append(f"Checked **{_engine().iso_now()}**. This is not an automatic trade signal.")
            news_key = f"news:{symbol}"
            _require_dashboard(connection, "news_events", news_key, "\n".join(lines))
            keep_news.add(f"local-engine:{news_key}")

            digest = _headline_digest(items)
            previous = str(hashes.get(symbol) or "")
            if items and digest != previous:
                alert_lines = [
                    f"## {symbol} Event Watch",
                    f"**Newest tracked event:** [{items[0]['title']}]({items[0]['url']})",
                    f"Published: **{items[0].get('date') or 'timestamp unavailable'}**",
                    "### Additional current event context",
                ]
                alert_lines.extend(
                    f"• [{item['title']}]({item['url']})"
                    for item in items[1:4]
                )
                alert_lines.extend(
                    [
                        "This stable ticker card updates only when its event set changes; duplicate headlines do not create duplicate posts.",
                        f"Detected **{_engine().iso_now()}**.",
                    ]
                )
                breaking_key = f"breaking-news:{symbol}"
                _require_dashboard(
                    connection, "breaking_alerts", breaking_key, "\n".join(alert_lines)
                )
                hashes[symbol] = digest
                changed.append(symbol)
            keep_breaking.add(f"local-engine:breaking-news:{symbol}")
            completed.append(symbol)
        except Exception as exc:
            failures.append(f"{symbol}:{type(exc).__name__}:{str(exc)[:100]}")
        time.sleep(0.15)

    for symbol in list(hashes):
        if symbol not in symbols:
            hashes.pop(symbol, None)
    _set_state_json(connection, "upgrade44:headline-hashes", hashes)
    removed_news = _cleanup_dashboard_cards(
        connection, "news_events", ("local-engine:news:",), keep_news
    )
    removed_breaking = _cleanup_dashboard_cards(
        connection, "breaking_alerts", ("local-engine:breaking-news:",), keep_breaking
    )
    _engine().store_observation(
        connection,
        "active-news-sweep",
        {
            "active": symbols,
            "completed": completed,
            "changed": changed,
            "failed": failures,
            "removed": removed_news + removed_breaking,
            "at": _engine().iso_now(),
        },
    )
    if failures and not completed:
        raise RuntimeError("Active ticker news failed: " + ", ".join(failures))
    return (
        f"{len(completed)}/{len(symbols)} active ticker news cards; "
        f"{len(changed)} event cards changed; {removed_news + removed_breaking} stale removed"
    )


def _snapshot_direction(snapshot: dict[str, Any], change: float | None) -> str:
    regime = str(snapshot.get("regime") or "").upper()
    if "BULL" in regime:
        return "BULLISH"
    if "BEAR" in regime:
        return "BEARISH"
    if "RANGE" in regime or "NEUTRAL" in regime:
        return "RANGE"
    if change is None:
        return "UNKNOWN"
    if change >= 0.5:
        return "UP"
    if change <= -0.5:
        return "DOWN"
    return "FLAT"


def market_regime_summary_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    quotes = spy_scanner.get_quotes(symbols, include_greeks=False) if symbols else {}
    groups: dict[str, list[str]] = {"BULLISH": [], "BEARISH": [], "RANGE": [], "OTHER": []}
    records: list[dict[str, Any]] = []

    for symbol in symbols:
        quote = quotes.get(symbol) or {}
        snapshot = _latest_payload(f"ticker-market:{symbol}")
        change = _quote_change(quote)
        direction = _snapshot_direction(snapshot, change)
        bucket = direction if direction in groups else "OTHER"
        groups[bucket].append(symbol)
        records.append(
            {
                "symbol": symbol,
                "price": spy_scanner.as_float(quote.get("last") or snapshot.get("price")),
                "change": change if change is not None else spy_scanner.as_float(snapshot.get("change_pct")),
                "direction": direction,
                "regime": snapshot.get("regime") or "awaiting refresh",
                "rsi": snapshot.get("rsi14"),
                "relative_volume": snapshot.get("relative_volume"),
                "support": snapshot.get("support20"),
                "resistance": snapshot.get("resistance20"),
            }
        )

    records.sort(key=lambda item: abs(float(item.get("change") or 0)), reverse=True)
    lines = [
        "## Active-Universe Market Regime",
        f"**Bullish {len(groups['BULLISH'])}** · **Bearish {len(groups['BEARISH'])}** · "
        f"**Range {len(groups['RANGE'])}** · **Other {len(groups['OTHER'])}**",
        "One card covers every active ticker; removed tickers disappear automatically.",
        "### Direction and decision context",
    ]
    for item in records:
        lines.append(
            f"• **{item['symbol']}** · {_fmt_price(item['price'])} · "
            f"{_fmt_change(item['change'])} · **{item['direction']}** · "
            f"{item['regime']} · RSI {_fmt_number(item['rsi'], 1)} · "
            f"RVOL {_fmt_number(item['relative_volume'], 2, 'x')} · "
            f"S/R {_fmt_price(item['support'])}/{_fmt_price(item['resistance'])}"
        )
    lines.extend(
        [
            "### Interpretation",
            "Direction combines the latest recorded regime with current price movement. "
            "Missing history remains labeled instead of being guessed.",
            f"Updated **{_engine().iso_now()}**. Context only, not a trade instruction.",
        ]
    )
    _require_dashboard(connection, "intelligence", "active-market-regime", "\n".join(lines))
    _cleanup_dashboard_cards(
        connection,
        "intelligence",
        ("local-engine:market:", "local-engine:market-pulse", "local-engine:material-market"),
        {"local-engine:active-market-regime"},
    )
    _engine().store_observation(
        connection,
        "active-market-regime",
        {"groups": groups, "records": records, "at": _engine().iso_now()},
    )
    return f"{len(records)} active ticker directions summarized"


def active_market_information_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    batch = _rotation_batch(connection, "market-information", symbols, MARKET_BATCH_SIZE)
    completed: list[str] = []
    failures: list[str] = []
    for symbol in batch:
        try:
            snapshot = _engine().market_snapshot(symbol)
            _engine().store_observation(
                connection,
                f"ticker-market:{symbol}",
                {key: value for key, value in snapshot.items() if key != "history"},
            )
            completed.append(symbol)
        except Exception as exc:
            failures.append(f"{symbol}:{type(exc).__name__}:{str(exc)[:120]}")
        time.sleep(0.25)
    summary = market_regime_summary_job(connection)
    if failures and not completed:
        raise RuntimeError("Market intelligence batch failed: " + ", ".join(failures))
    return (
        f"refreshed {len(completed)}/{len(batch)} ticker snapshots; "
        f"{len(failures)} failures; {summary}"
    )


def _render_intraday_chart(symbol: str, bars: list[dict[str, Any]], output: Path) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont

    points: list[tuple[str, float]] = []
    for bar in bars:
        value = spy_scanner.as_float(bar.get("close") or bar.get("price"))
        if value is None:
            continue
        label = str(bar.get("time") or bar.get("timestamp") or bar.get("date") or "")
        points.append((label, float(value)))
    if len(points) < 2:
        raise ValueError(f"{symbol} returned fewer than two usable chart bars")

    values = [item[1] for item in points]
    width, height = 1200, 650
    left, right, top, bottom = 90, 40, 90, 100
    plot_width = width - left - right
    plot_height = height - top - bottom
    low, high = min(values), max(values)
    padding = max((high - low) * 0.12, 0.05)
    low -= padding
    high += padding
    image = Image.new("RGB", (width, height), "#0b1420")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=15)
    normal = ImageFont.load_default(size=18)
    title_font = ImageFont.load_default(size=26)

    def xy(index: int, value: float) -> tuple[int, int]:
        x = left + int(index / max(len(values) - 1, 1) * plot_width)
        y = top + int((high - value) / max(high - low, 0.01) * plot_height)
        return x, y

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#26364a", width=1)
        draw.text((12, y - 8), f"${value:.2f}", fill="#9fb0c3", font=small)
    draw.line([xy(index, value) for index, value in enumerate(values)], fill="#e5edf7", width=4)
    support = min(values[-min(20, len(values)):])
    resistance = max(values[-min(20, len(values)):])
    for level, label, color in (
        (support, "support", "#22c55e"),
        (resistance, "resistance", "#ef4444"),
    ):
        y = xy(0, level)[1]
        draw.line((left, y, width - right, y), fill=color, width=2)
        draw.text((width - 190, y - 20), f"{label} ${level:.2f}", fill=color, font=small)
    first, last = values[0], values[-1]
    change = (last / first - 1) * 100 if first else 0.0
    draw.text((left, 25), f"{symbol} ACTIVE SESSION PRICE MOVEMENT", fill="#f8fafc", font=title_font)
    draw.text(
        (left, 58),
        f"{len(values)} bars · ${first:.2f} to ${last:.2f} · {change:+.2f}%",
        fill="#b8c7d9",
        font=normal,
    )
    draw.text(
        (left, height - 66),
        f"Range ${min(values):.2f}-${max(values):.2f} · support ${support:.2f} · resistance ${resistance:.2f}",
        fill="#dbe7f3",
        font=normal,
    )
    draw.text(
        (left, height - 36),
        f"Last source {points[-1][0] or 'unavailable'} · generated {_iso()} · paper research only",
        fill="#91a4b8",
        font=small,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format="PNG", optimize=True)
    return {
        "first": first,
        "last": last,
        "change_pct": change,
        "low": min(values),
        "high": max(values),
        "support": support,
        "resistance": resistance,
        "bars": len(values),
        "source_timestamp": points[-1][0],
    }


def _replace_chart_message(
    connection: Any,
    symbol: str,
    path: Path,
    caption: str,
    *,
    channel: str = "charts",
    state_key: str = "upgrade44:chart-messages",
) -> bool:
    """Post a chart image and delete the one it supersedes. Discord
    cannot edit an attachment in place, so an "updating chart" is really
    post-new-then-delete-old. channel/state_key are defaulted so the
    original #charts-and-levels call sites are unchanged, and the
    market-memory boards can reuse the exact same tested path."""
    tracker = _tracker()
    if not tracker:
        return False
    state = _state_json(connection, state_key)
    old_id = str(state.get(symbol) or "")
    response = tracker.send_channel_file(channel, path, content=caption[:1900])
    new_id = str((response or {}).get("id") or "")
    if not new_id:
        return False
    channel_id = str(tracker.channels.get(channel) or "")
    if old_id and old_id != new_id and channel_id:
        try:
            tracker._request("DELETE", f"/channels/{channel_id}/messages/{old_id}")
        except spy_scanner.DiscordError as exc:
            if "HTTP 404" not in str(exc):
                raise
    state[symbol] = new_id
    _set_state_json(connection, state_key, state)
    return True


SPY_TECHNICALS_STATE_KEY = "upgrade44:spy-technicals"


def spy_technicals_job(connection: Any) -> str:
    """Publishes the market-memory research store as charts plus one
    summary card in #spy-technicals.

    Cadence note, because it is not obvious: the store is refreshed by a
    separate once-daily scheduled task at 3:35pm CT (after the close),
    so the underlying data changes at most once per trading day. This
    job therefore runs on a short interval only so it notices that
    refresh promptly and so the engine's own overdue-job health check
    keeps a tight window - but it fingerprints the data first and
    returns without touching Discord when nothing has changed. Real
    work happens roughly once a day; the other ticks cost one cheap
    query.

    Reads through market_memory_charts, which opens the database
    read-only and never imports market_memory, so the research store's
    isolation from live trading is preserved."""
    import market_memory_charts as charts

    try:
        conn = charts.open_readonly()
    except sqlite3.OperationalError as exc:
        # A missing or locked research database must never mark the live
        # engine unhealthy - it has nothing to do with trading.
        return f"market memory database unavailable: {exc}"

    try:
        fingerprint = charts.data_fingerprint(conn)
        state = _state_json(connection, SPY_TECHNICALS_STATE_KEY)
        if state.get("fingerprint") == fingerprint:
            return f"unchanged since {state.get('rendered_at', 'last run')}; no repost"

        summary = charts.summarize(conn)
        _require_dashboard(
            connection, "spy_technicals", "spy-technicals", charts.technicals_card_text(summary)
        )
        boards = charts.render_all(conn)
    finally:
        conn.close()

    posted = 0
    for key, path, caption in boards:
        if _replace_chart_message(
            connection, key, path, caption,
            channel="spy_technicals", state_key=f"{SPY_TECHNICALS_STATE_KEY}:messages",
        ):
            posted += 1
    if posted != len(boards):
        raise RuntimeError(f"Discord acknowledged only {posted}/{len(boards)} technical charts")

    # Recorded only after every upload succeeded, so a partial failure
    # retries on the next tick instead of being marked done.
    _set_state_json(
        connection,
        SPY_TECHNICALS_STATE_KEY,
        {"fingerprint": fingerprint, "rendered_at": _iso(), "boards": posted},
    )
    _engine().store_observation(
        connection, "spy-technicals-charts", {"boards": posted, "fingerprint": fingerprint}
    )
    return f"{posted} technical chart(s) and 1 summary card refreshed"


def _cleanup_chart_messages(connection: Any, active: set[str]) -> int:
    tracker = _tracker()
    if not tracker:
        return 0
    state = _state_json(connection, "upgrade44:chart-messages")
    channel_id = str(tracker.channels.get("charts") or "")
    removed = 0
    for symbol in list(state):
        if symbol in active:
            continue
        message_id = str(state.get(symbol) or "")
        if message_id and channel_id:
            try:
                tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            except spy_scanner.DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        state.pop(symbol, None)
        removed += 1
    _set_state_json(connection, "upgrade44:chart-messages", state)
    return removed


def intraday_chart_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    batch = _rotation_batch(connection, "intraday-charts", symbols, CHART_BATCH_SIZE)
    completed: list[str] = []
    failures: list[str] = []
    keep = {f"local-engine:intraday-levels:{symbol}" for symbol in symbols}
    for symbol in batch:
        try:
            bars = spy_scanner.get_intraday_history(symbol)
            timeframe = "5-minute session"
            if len(bars) < 2:
                bars = spy_scanner.get_daily_history(symbol, days=45)[-30:]
                timeframe = "30-session fallback"
            output = CHART_DIR / f"{symbol.lower()}-active-session.png"
            metrics = _render_intraday_chart(symbol, bars, output)
            snapshot = _latest_payload(f"ticker-market:{symbol}")
            content = "\n".join(
                [
                    f"## {symbol} Chart & Levels",
                    f"**Timeframe:** {timeframe} · **Bars:** {metrics['bars']}",
                    f"**Move:** {_fmt_price(metrics['first'])} → {_fmt_price(metrics['last'])} "
                    f"({_fmt_change(metrics['change_pct'])})",
                    f"**Session range:** {_fmt_price(metrics['low'])}–{_fmt_price(metrics['high'])}",
                    f"**Near-term support:** {_fmt_price(metrics['support'])} · "
                    f"**Near-term resistance:** {_fmt_price(metrics['resistance'])}",
                    f"**Recorded broader regime:** {snapshot.get('regime') or 'awaiting refresh'} · "
                    f"RSI14 {_fmt_number(snapshot.get('rsi14'), 1)}",
                    f"Source **{metrics['source_timestamp'] or 'timestamp unavailable'}** · "
                    f"updated **{_engine().iso_now()}**.",
                ]
            )
            _require_dashboard(connection, "charts", f"intraday-levels:{symbol}", content)
            if not _replace_chart_message(
                connection,
                symbol,
                output,
                f"📈 **{symbol} {timeframe}** · {_fmt_change(metrics['change_pct'])} · "
                f"support {_fmt_price(metrics['support'])} · "
                f"resistance {_fmt_price(metrics['resistance'])}",
            ):
                raise RuntimeError("Discord did not acknowledge chart upload")
            completed.append(symbol)
        except Exception as exc:
            failures.append(f"{symbol}:{type(exc).__name__}:{str(exc)[:120]}")
        time.sleep(0.2)
    removed_cards = _cleanup_dashboard_cards(
        connection,
        "charts",
        ("local-engine:intraday-levels:", "local-engine:technicals:"),
        keep,
    )
    removed_files = _cleanup_chart_messages(connection, set(symbols))
    _engine().store_observation(
        connection,
        "intraday-chart-refresh",
        {
            "batch": batch,
            "completed": completed,
            "failed": failures,
            "removed": removed_cards + removed_files,
            "at": _engine().iso_now(),
        },
    )
    if failures and not completed:
        raise RuntimeError("Intraday chart batch failed: " + ", ".join(failures))
    return (
        f"{len(completed)}/{len(batch)} active charts refreshed; "
        f"{removed_cards + removed_files} stale removed"
    )



def enhanced_activity_card(connection: Any, rows: list[dict[str, Any]]) -> str:
    active = dynamic_universe.active_symbols()
    latest = connection.execute(
        """
        SELECT job_name, status, finished_at, detail
        FROM job_runs
        WHERE status != 'RUNNING'
        ORDER BY id DESC
        LIMIT 16
        """
    ).fetchall()
    latest_scan = _engine().latest_observation("full-scan") or {}
    latest_market = _engine().latest_observation("active-market-regime") or {}
    latest_news = _engine().latest_observation("active-news-sweep") or {}
    latest_charts = _engine().latest_observation("intraday-chart-refresh") or {}
    attention = [
        row for row in rows
        if row.get("status") not in {"OK", "RUNNING", "PAUSED", "STARTING"}
    ]
    lines = [
        "## Live Tradysquids System Activity",
        f"**Market:** {'OPEN' if spy_scanner.market_is_open_now()[0] else 'CLOSED'} · "
        f"**Ticker:** {', '.join(active) or spy_scanner.TICKER}",
        f"**Needs attention:** {len(attention)} scheduled job(s)",
        "### What actually happened",
    ]
    if latest:
        for item in latest:
            detail = " ".join(str(item["detail"] or "").split())[:180]
            lines.append(
                f"• **{item['job_name']}** · {item['status']} · "
                f"{item['finished_at'] or 'unfinished'} · {detail or 'no detail recorded'}"
            )
    else:
        lines.append("No completed job receipt has been written yet.")
    lines.extend(
        [
            "### Freshness of visible work",
            f"• Options scan: {_engine().data_age_text(latest_scan.get('observed_at'))} ago",
            f"• Market regime: {_engine().data_age_text(latest_market.get('observed_at'))} ago",
            f"• News sweep: {_engine().data_age_text(latest_news.get('observed_at'))} ago",
            f"• Intraday charts: {_engine().data_age_text(latest_charts.get('observed_at'))} ago",
            "### Current universe",
            ", ".join(active) or "No active tickers.",
        ]
    )
    if attention:
        lines.append("### Attention")
        lines.extend(
            f"• **{row['name']}** · {row['status']} · {str(row.get('reason') or '')[:180]}"
            for row in attention[:8]
        )
    lines.append(
        f"Updated **{_engine().iso_now()}**. This page is built from job receipts, not decorative promises."
    )
    return "\n".join(lines)[:5900]


def _style_group(summary: dict[str, Any], style: str) -> dict[str, Any]:
    target = style.upper()
    for item in summary.get("groups") or []:
        if item.get("feature") == "play_style" and str(item.get("value") or "").upper() == target:
            return item
    return {
        "feature": "play_style",
        "value": target,
        "samples": 0,
        "wins": 0,
        "win_rate_pct": 0.0,
        "average_pl_dollars": 0.0,
        "total_pl_dollars": 0.0,
        "profit_factor": None,
        "average_mfe_pct": None,
        "average_mae_pct": None,
        "evidence_ready": False,
    }


def _suggestion(summary: dict[str, Any], style: str) -> dict[str, Any]:
    target = style.upper()
    for item in summary.get("play_style_suggestions") or []:
        if str(item.get("play_style") or "").upper() == target:
            return item
    return {
        "samples": 0,
        "confidence": "COLLECTING",
        "observation": "No completed trades of this exact play style are available yet.",
        "expected_tradeoff": "Collect consistent evidence before proposing a filter change.",
    }


def learning_results_text(summary: dict[str, Any]) -> str:
    evidence = list(summary.get("evidence_ready_groups") or [])
    positive = sorted(
        (item for item in evidence if float(item.get("average_pl_dollars") or 0) > 0),
        key=lambda item: float(item.get("average_pl_dollars") or 0),
        reverse=True,
    )
    negative = sorted(
        (item for item in evidence if float(item.get("average_pl_dollars") or 0) < 0),
        key=lambda item: float(item.get("average_pl_dollars") or 0),
    )
    lines = [
        "## Learning Results · Evidence Dashboard",
        f"**Closed trades:** {summary.get('closed_trades', 0)} · "
        f"**Reviewed:** {summary.get('reviewed_trades', 0)} "
        f"({float(summary.get('review_coverage_pct') or 0):.1f}%) · "
        f"**Minimum evidence sample:** {summary.get('minimum_sample', 0)}",
        f"**Learning Center version:** `{summary.get('learning_version') or 'unavailable'}`",
        "### What is currently working",
    ]
    if positive:
        lines.extend(
            f"• **{item['feature']} = {item['value']}** · {item['samples']} trades · "
            f"{item['win_rate_pct']:.0f}% wins · avg "
            f"{spy_scanner.fmt_money(item['average_pl_dollars'])} · total "
            f"{spy_scanner.fmt_money(item['total_pl_dollars'])}"
            for item in positive[:6]
        )
    else:
        lines.append("No positive group has reached the evidence threshold yet.")
    lines.append("### What currently needs review")
    if negative:
        lines.extend(
            f"• **{item['feature']} = {item['value']}** · {item['samples']} trades · "
            f"{item['win_rate_pct']:.0f}% wins · avg "
            f"{spy_scanner.fmt_money(item['average_pl_dollars'])} · "
            f"MAE {_fmt_number(item.get('average_mae_pct'), 1, '%')}"
            for item in negative[:6]
        )
    else:
        lines.append("No negative group has reached the evidence threshold yet.")
    lines.append("### Suggested next reviews")
    suggestions = list(summary.get("play_style_suggestions") or [])
    if suggestions:
        for item in suggestions[:8]:
            lines.append(
                f"• **{str(item['play_style']).replace('-', ' ').title()}** · "
                f"{item['samples']} trades · {item['confidence']} · "
                f"{item['observation']} **Tradeoff:** {item['expected_tradeoff']}"
            )
    else:
        lines.append("No play-style suggestion is available yet.")
    lines.extend(
        [
            "### Guardrail",
            "Evidence is descriptive. No scanner filter changes automatically; promotion requires owner review and controlled testing.",
            f"Updated **{_engine().iso_now() if _ENGINE else _iso()}**.",
        ]
    )
    return "\n".join(lines)[:5900]


def style_evidence_text(
    title: str,
    group: dict[str, Any],
    suggestion: dict[str, Any],
    minimum_sample: int,
) -> str:
    samples = int(group.get("samples") or 0)
    remaining = max(0, int(minimum_sample) - samples)
    confidence = "EVIDENCE-READY" if group.get("evidence_ready") else "COLLECTING"
    lines = [
        f"## {title} Evidence & Improvement",
        f"**Sample:** {samples}/{minimum_sample} · **Confidence:** {confidence}",
        "### Aggregate evidence",
        f"Win rate **{float(group.get('win_rate_pct') or 0):.1f}%** · "
        f"average P/L **{spy_scanner.fmt_money(group.get('average_pl_dollars'))}** · "
        f"total P/L **{spy_scanner.fmt_money(group.get('total_pl_dollars'))}**",
        f"Profit factor **{group.get('profit_factor') if group.get('profit_factor') is not None else 'unavailable'}** · "
        f"average MFE **{_fmt_number(group.get('average_mfe_pct'), 1, '%')}** · "
        f"average MAE **{_fmt_number(group.get('average_mae_pct'), 1, '%')}**",
        "### Evidence limit",
        (
            "The sample has reached the configured evidence threshold."
            if remaining == 0
            else f"{remaining} more closed trade(s) are required before this group is evidence-ready."
        ),
        "### Suggested improvement review",
        str(suggestion.get("observation") or "Continue collecting consistent evidence."),
        f"**Expected tradeoff:** {suggestion.get('expected_tradeoff') or 'Unknown until tested.'}",
        "### Data location",
        "Individual completed trades remain only in Trade Journal. This card intentionally contains no trade-history list.",
        "**Status:** review-only; scanner and risk rules are unchanged.",
    ]
    return "\n".join(lines)[:5900]


def enhanced_outcome_learning_job(connection: Any) -> str:
    summary = outcome_learning.export_learning_archive()
    _engine().store_observation(
        connection,
        "outcome-learning",
        {
            "closed_trades": summary["closed_trades"],
            "reviewed_trades": summary.get("reviewed_trades", 0),
            "evidence_ready_groups": len(summary["evidence_ready_groups"]),
            "generated_at": summary["generated_at"],
        },
    )
    tracker = _tracker()
    if tracker:
        report_state = spy_scanner.read_report_state()
        tracker.upsert_channel_message(
            "learning_results",
            report_state,
            "learning-results-v2",
            learning_results_text(summary),
            search_token="Learning Results · Evidence Dashboard",
        )
        spy_scanner.write_report_state(report_state)
    return (
        f"{summary['closed_trades']} closed trades; "
        f"{len(summary['evidence_ready_groups'])} evidence-ready groups; "
        f"{len(summary.get('play_style_suggestions') or [])} improvement reviews"
    )


def _find_channel(tracker: Any, names: tuple[str, ...]) -> dict[str, Any] | None:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    for name in names:
        match = next(
            (
                item
                for item in channels
                if str(item.get("name") or "").casefold() == name.casefold()
                and int(item.get("type") or 0) == 0
            ),
            None,
        )
        if match:
            return match
    return None


def upgrade_request_migration_job(connection: Any) -> str:
    tracker = _tracker()
    if not tracker:
        return "waiting for Discord configuration"
    destination = _find_channel(tracker, ("upgrade-requests", "upgrade-review"))
    if not destination:
        return "upgrade destination is missing"
    destination_id = str(destination["id"])
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    moved = 0
    scanned = 0
    for channel in channels:
        channel_id = str(channel.get("id") or "")
        if int(channel.get("type") or -1) != 0 or not channel_id or channel_id == destination_id:
            continue
        try:
            messages = tracker._request("GET", f"/channels/{channel_id}/messages?limit=100")
        except spy_scanner.DiscordError:
            continue
        for message in messages if isinstance(messages, list) else []:
            scanned += 1
            author = message.get("author") or {}
            if not author.get("bot"):
                continue
            text = spy_scanner.message_search_text(message)
            if (
                "Upgrade request" not in text
                or ("uploaded" not in text and "Batch issue" not in text)
            ):
                continue
            payload = {
                "content": str(message.get("content") or "")[:1900],
                "embeds": message.get("embeds") or [],
                "allowed_mentions": {"parse": []},
            }
            tracker._request("POST", f"/channels/{destination_id}/messages", payload)
            tracker._request("DELETE", f"/channels/{channel_id}/messages/{message['id']}")
            moved += 1
    _engine().store_observation(
        connection,
        "upgrade-request-migration",
        {"scanned": scanned, "moved": moved, "at": _engine().iso_now()},
    )
    return f"{scanned} recent messages checked; {moved} upgrade response(s) moved"


def _clone_job(job: Any, callback: Any | None = None, **changes: Any) -> Any:
    engine = _engine()
    return engine.Job(
        changes.get("name", job.name),
        changes.get("interval", job.interval),
        callback or job.callback,
        market_hours_only=changes.get("market_hours_only", job.market_hours_only),
        after_hours_interval=changes.get("after_hours_interval", job.after_hours_interval),
        background=changes.get("background", job.background),
        provider_heavy=changes.get("provider_heavy", job.provider_heavy),
        retry_interval=changes.get("retry_interval", job.retry_interval),
    )


def install_engine() -> None:
    """Replace weak Discord jobs with active-universe implementations."""
    global _ENGINE_INSTALLED, _ENGINE, _PUBLIC, _OPERATIONS
    if _ENGINE_INSTALLED:
        return
    import always_on_operations as operations
    import local_information_engine_public as public

    _PUBLIC = public
    _ENGINE = public.engine
    _OPERATIONS = operations
    operations.activity_card = enhanced_activity_card

    replacements = {
        "premarket-visibility": (
            active_premarket_job,
            {
                "interval": timedelta(minutes=15),
                "after_hours_interval": timedelta(minutes=45),
                "retry_interval": timedelta(minutes=2),
            },
        ),
        "managed-ticker-news": (
            active_news_job,
            {
                "interval": timedelta(minutes=30),
                "after_hours_interval": timedelta(hours=1),
                "retry_interval": timedelta(minutes=5),
            },
        ),
        "managed-ticker-information": (
            active_market_information_job,
            {
                "interval": timedelta(minutes=15),
                "after_hours_interval": timedelta(hours=1),
                "retry_interval": timedelta(minutes=5),
            },
        ),
        "outcome-learning": (
            enhanced_outcome_learning_job,
            {
                "interval": timedelta(hours=3),
                "retry_interval": timedelta(minutes=10),
            },
        ),
        "system-activity": (
            operations.system_activity_job,
            {"interval": timedelta(minutes=5), "retry_interval": timedelta(minutes=2)},
        ),
    }
    jobs: list[Any] = []
    found: set[str] = set()
    for job in _ENGINE.JOBS:
        replacement = replacements.get(job.name)
        if replacement:
            callback, changes = replacement
            jobs.append(_clone_job(job, callback, **changes))
            found.add(job.name)
        else:
            jobs.append(job)
    missing = sorted(set(replacements) - found)
    if missing:
        raise RuntimeError("Upgrade batch could not replace jobs: " + ", ".join(missing))

    additions = [
        _ENGINE.Job(
            "active-market-regime",
            timedelta(minutes=15),
            market_regime_summary_job,
            after_hours_interval=timedelta(hours=1),
            background=True,
            retry_interval=timedelta(minutes=5),
        ),
        _ENGINE.Job(
            "intraday-chart-refresh",
            timedelta(minutes=10),
            intraday_chart_job,
            after_hours_interval=timedelta(hours=2),
            background=True,
            provider_heavy=True,
            retry_interval=timedelta(minutes=5),
        ),
        _ENGINE.Job(
            "upgrade-request-migration",
            timedelta(minutes=10),
            upgrade_request_migration_job,
            background=True,
            retry_interval=timedelta(minutes=5),
        ),
        # Short interval so a once-daily data refresh is picked up
        # promptly and the overdue-job health window stays tight; the
        # job's own fingerprint guard means it only does real work when
        # the store actually changed. Deliberately NOT provider_heavy -
        # it makes zero provider calls and must not contend for the
        # provider lock with the live scanner.
        _ENGINE.Job(
            "spy-technicals-charts",
            timedelta(minutes=20),
            spy_technicals_job,
            background=True,
            retry_interval=timedelta(minutes=5),
        ),
    ]
    existing = {job.name for job in jobs}
    jobs.extend(job for job in additions if job.name not in existing)
    _ENGINE.JOBS = jobs
    _ENGINE_INSTALLED = True


def install_structure(sync: Any) -> None:
    """Add a dedicated owner-only upgrade request channel without disturbing review."""
    global _STRUCTURE_INSTALLED
    if _STRUCTURE_INSTALLED:
        return
    if not any(item.name == "upgrade-requests" for item in sync.CHANNELS):
        rebuilt = []
        inserted = False
        for item in sync.CHANNELS:
            if item.name == "upgrade-review" and not inserted:
                rebuilt.append(
                    sync.ChannelSpec(
                        "OWNER CONTROL",
                        "upgrade-requests",
                        "Owner-submitted upgrade batches mirrored from any Discord channel.",
                    )
                )
                inserted = True
            rebuilt.append(item)
        if not inserted:
            rebuilt.append(
                sync.ChannelSpec(
                    "OWNER CONTROL",
                    "upgrade-requests",
                    "Owner-submitted upgrade batches mirrored from any Discord channel.",
                )
            )
        sync.CHANNELS = rebuilt
    sync.CHANNEL_STARTERS["upgrade-requests"] = (
        "Owner `/upgrade-add` requests are mirrored here, removed from the source channel, "
        "and uploaded to the active GitHub batch."
    )
    sync.GUIDES["upgrade-requests"] = """# Upgrade Requests
Use `/upgrade-add request:` from any channel. TradeBot records the request in the
open GitHub batch, mirrors the confirmation here, and removes the confirmation
from the source channel so working dashboards stay clean.

`/upgrade-list` shows the current batch. `/upgrade-ready` locks it for maintainer
review. No request edits code or deploys anything until a tested pull request is
approved and merged."""
    _STRUCTURE_INSTALLED = True


def validate_batch() -> dict[str, Any]:
    import learning_center_catalog

    supplements = _supplement_lessons()
    missing = [
        channel
        for channel in learning_center_catalog.ORDERED_CHANNELS
        if channel not in supplements
    ]
    if missing:
        raise RuntimeError("Applied Learning Center supplement is missing: " + ", ".join(missing))
    sample_summary = {
        "closed_trades": 20,
        "reviewed_trades": 15,
        "review_coverage_pct": 75.0,
        "minimum_sample": 20,
        "learning_version": "test",
        "evidence_ready_groups": [],
        "play_style_suggestions": [],
    }
    rendered = learning_results_text(sample_summary)
    if "Trade History" in rendered:
        raise RuntimeError("Learning results unexpectedly contains trade history")
    style = style_evidence_text(
        "Regular Call",
        _style_group({"groups": []}, "REGULAR-CALL"),
        _suggestion({"play_style_suggestions": []}, "REGULAR-CALL"),
        20,
    )
    if "Individual completed trades remain only in Trade Journal" not in style:
        raise RuntimeError("Play-style evidence card lost the journal-only contract")
    return {
        "version": BATCH_VERSION,
        "supplement_channels": len(supplements),
        "journal_format": JOURNAL_FORMAT_VERSION,
        "learning_results_trade_history_pages": 0,
        "dedicated_upgrade_channel": True,
    }


if __name__ == "__main__":
    print(json.dumps(validate_batch(), indent=2))
