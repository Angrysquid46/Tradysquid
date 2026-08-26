
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
import market_data
import discord_transport
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
_UNIVERSE_POLICY_INSTALLED = False
_LEARNING_INSTALLED = False
_ENGINE_INSTALLED = False


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
    """Set the trade-journal format version and learning-content hash.

    Phase 3 purge, owner-authorized: this used to also patch
    spy_scanner.trade_learning_analysis / spy_scanner.DISCORD_FORMAT_VERSION
    (trade-journal card content) - removed along with spy_scanner.py itself.
    The old Learning Center's library_sections()/load_lessons() monkeypatch
    was removed when that system was retired; the coupling that would
    otherwise crash every launch through run_with_env.py went with it."""
    global _LEARNING_INSTALLED
    if _LEARNING_INSTALLED:
        return

    import journal_contract

    trade_intelligence.learning_version = _combined_learning_version
    journal_contract.JOURNAL_FORMAT_VERSION = JOURNAL_FORMAT_VERSION
    _LEARNING_INSTALLED = True


def _engine() -> Any:
    if _ENGINE is None:
        raise RuntimeError("Upgrade batch engine hooks are not installed")
    return _ENGINE


# Retired 2026-08-25: this used to route through _engine().discord_tracker()
# and _engine().upsert_dashboard(), both leftover calls onto the old
# discover()-based visibility layer install_engine() itself documents as
# deleted in the Phase 3 purge - local_information_engine has neither
# attribute, so every dashboard job using them raised AttributeError the
# moment it actually ran (only ever exercised by tests, never live). Now
# builds a real tracker directly and resolves channel IDs the same way
# rivalry_presentation.py's already-working _channel_id() does, since
# DiscordTracker deliberately doesn't do channel discovery itself.
_CHANNEL_ID_CACHE: dict[str, str] = {}

_LOGICAL_CHANNEL_NAMES = {
    "premarket": "premarket",
    "intelligence": "market-regime",
    "charts": "charts-and-levels",
    "spy_technicals": "spy-technicals",
}


def _tracker() -> discord_transport.DiscordTracker | None:
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    return tracker if tracker.enabled else None


def _channel_id(tracker: discord_transport.DiscordTracker, logical_channel: str) -> str:
    name = _LOGICAL_CHANNEL_NAMES.get(logical_channel, logical_channel)
    cached = _CHANNEL_ID_CACHE.get(name)
    if cached:
        return cached
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    for row in channels if isinstance(channels, list) else []:
        if str(row.get("name") or "").casefold() == name.casefold():
            channel_id = str(row.get("id") or "")
            if channel_id:
                _CHANNEL_ID_CACHE[name] = channel_id
                return channel_id
    return ""


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
        value = market_data.as_float(quote.get(key))
        if value is not None:
            return value
    last = market_data.as_float(quote.get("last"))
    previous = market_data.as_float(quote.get("prevclose") or quote.get("previous_close"))
    if last is not None and previous:
        return (last / previous - 1) * 100
    return None


def _latest_payload(kind: str) -> dict[str, Any]:
    observation = _engine().latest_observation(kind) or {}
    payload = observation.get("payload") or {}
    return payload if isinstance(payload, dict) else {}


def _universe_rows() -> dict[str, dict[str, Any]]:
    # The multi-ticker "universe" table was removed when this system went
    # SPY-only (dynamic_universe.py's connect() no longer creates it) -
    # nothing left to look up. Callers already fall back to per-field
    # defaults ("current active-universe rules", etc.) when a symbol has
    # no metadata here.
    return {}


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
    channel_id = _channel_id(tracker, logical_channel)
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
            except discord_transport.DiscordError as exc:
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
    tracker = _tracker()
    if not tracker:
        raise RuntimeError(f"Discord tracker unavailable for {logical_channel}:{key}")
    channel_id = _channel_id(tracker, logical_channel)
    if not channel_id:
        raise RuntimeError(f"channel for {logical_channel} not found ({logical_channel}:{key})")
    message_id, _ = tracker.upsert_singleton_message(
        channel_id, content[:5900], search_token=f"local-engine:{key}"
    )
    if not message_id:
        raise RuntimeError(f"Discord did not acknowledge {logical_channel}:{key}")


def _fmt_price(value: Any) -> str:
    number = market_data.as_float(value)
    return "unavailable" if number is None else f"${number:.2f}"


def _fmt_change(value: Any) -> str:
    number = market_data.as_float(value)
    return "change unavailable" if number is None else f"{number:+.2f}%"


def _fmt_number(value: Any, digits: int = 1, suffix: str = "") -> str:
    number = market_data.as_float(value)
    return "unavailable" if number is None else f"{number:.{digits}f}{suffix}"


def _session_label(now: datetime, is_open: bool) -> str:
    # _PUBLIC (local_information_engine_public) supplied this before the
    # Phase 3 purge deleted that module; _PUBLIC itself was never
    # reassigned afterward, so this call always raised AttributeError in
    # production. Inlined equivalent: regular hours use the real open
    # flag, everything else is bucketed by clock time (CT).
    if is_open:
        return "regular session"
    minutes = now.hour * 60 + now.minute
    if 4 * 60 <= minutes < 8 * 60 + 30:
        return "premarket"
    if 15 * 60 <= minutes < 20 * 60:
        return "after hours"
    return "closed"


def active_premarket_job(connection: Any) -> str:
    symbols = dynamic_universe.active_symbols()
    quotes = market_data.get_quotes(symbols, include_greeks=False) if symbols else {}
    rows = _universe_rows()
    session = _session_label(market_data.now_ct(), bool(market_data.market_is_open_now()[0]))
    ranked = sorted(
        symbols,
        key=lambda symbol: abs(_quote_change(quotes.get(symbol) or {}) or 0.0),
        reverse=True,
    )
    overview = [
        "## Active-Universe Session Scanner",
        f"**Session:** {session} · **Ticker:** {', '.join(symbols) or market_data.TICKER}",
        "Cards below are generated only for the current universe and disappear when a ticker rotates out.",
        "### Largest current moves",
    ]
    for symbol in ranked[:10]:
        quote = quotes.get(symbol) or {}
        overview.append(
            f"• **{symbol}** · {_fmt_price(quote.get('last'))} · "
            f"{_fmt_change(_quote_change(quote))} · volume "
            f"{int(market_data.as_float(quote.get('volume'), 0) or 0):,}"
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
            volume = int(market_data.as_float(quote.get("volume"), 0) or 0)
            average_volume = market_data.as_float(metadata.get("average_volume"))
            relative_volume = (
                volume / average_volume
                if average_volume and average_volume > 0
                else market_data.as_float(snapshot.get("relative_volume"))
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
    quotes = market_data.get_quotes(symbols, include_greeks=False) if symbols else {}
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
                "price": market_data.as_float(quote.get("last") or snapshot.get("price")),
                "change": change if change is not None else market_data.as_float(snapshot.get("change_pct")),
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


# Three visually distinct layouts on the SAME real bars, rotated by
# calendar day so consecutive posts don't look like a stamped template
# (owner request: "charts...don't always look the same every time they
# post"). Each still draws only real numbers - support/resistance from the
# actual trailing window, a real simple moving average - nothing synthetic.
CHART_VARIANT_COUNT = 3


def _simple_moving_average(values: list[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for index in range(len(values)):
        if index + 1 < period:
            out.append(None)
            continue
        window = values[index + 1 - period : index + 1]
        out.append(sum(window) / len(window))
    return out


def _render_intraday_chart(
    symbol: str, bars: list[dict[str, Any]], output: Path, *, variant: int = 0
) -> dict[str, Any]:
    from PIL import Image, ImageDraw, ImageFont

    points: list[tuple[str, float]] = []
    for bar in bars:
        value = market_data.as_float(bar.get("close") or bar.get("price"))
        if value is None:
            continue
        label = str(bar.get("time") or bar.get("timestamp") or bar.get("date") or "")
        points.append((label, float(value)))
    if len(points) < 2:
        raise ValueError(f"{symbol} returned fewer than two usable chart bars")

    variant = variant % CHART_VARIANT_COUNT
    values = [item[1] for item in points]
    width, height = 1200, 650
    left, right, top, bottom = 90, 40, 90, 100
    plot_width = width - left - right
    plot_height = height - top - bottom
    low, high = min(values), max(values)
    padding = max((high - low) * 0.12, 0.05)
    low -= padding
    high += padding
    background = "#0b1420" if variant != 2 else "#11151f"
    image = Image.new("RGB", (width, height), background)
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

    support = min(values[-min(20, len(values)):])
    resistance = max(values[-min(20, len(values)):])
    line_points = [xy(index, value) for index, value in enumerate(values)]

    if variant == 0:
        # Plain price line + explicit support/resistance rails.
        draw.line(line_points, fill="#e5edf7", width=4)
        for level, label, color in (
            (support, "support", "#22c55e"),
            (resistance, "resistance", "#ef4444"),
        ):
            y = xy(0, level)[1]
            draw.line((left, y, width - right, y), fill=color, width=2)
            draw.text((width - 190, y - 20), f"{label} ${level:.2f}", fill=color, font=small)
        subtitle = "price + support/resistance"
    elif variant == 1:
        # Shaded range band between support and resistance, price on top.
        top_y = xy(0, resistance)[1]
        bottom_y = xy(0, support)[1]
        draw.rectangle((left, top_y, width - right, bottom_y), fill="#16273a")
        draw.line(line_points, fill="#7dd3fc", width=4)
        draw.text((width - 230, top_y - 20), f"resistance ${resistance:.2f}", fill="#ef4444", font=small)
        draw.text((width - 230, bottom_y + 6), f"support ${support:.2f}", fill="#22c55e", font=small)
        subtitle = "price + support/resistance zone"
    else:
        # Price line with a real trailing simple-moving-average overlay.
        period = max(3, min(20, len(values) // 4 or 3))
        sma = _simple_moving_average(values, period)
        draw.line(line_points, fill="#e5edf7", width=3)
        sma_points = [
            xy(index, value) for index, value in enumerate(sma) if value is not None
        ]
        if len(sma_points) >= 2:
            draw.line(sma_points, fill="#fbbf24", width=3)
        draw.text((width - 230, top + 6), f"SMA({period})", fill="#fbbf24", font=small)
        subtitle = f"price + {period}-bar moving average"

    first, last = values[0], values[-1]
    change = (last / first - 1) * 100 if first else 0.0
    draw.text((left, 25), f"{symbol} ACTIVE SESSION PRICE MOVEMENT", fill="#f8fafc", font=title_font)
    draw.text(
        (left, 58),
        f"{len(values)} bars · ${first:.2f} to ${last:.2f} · {change:+.2f}% · {subtitle}",
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
    channel_id = _channel_id(tracker, channel)
    if not channel_id:
        return False
    state = _state_json(connection, state_key)
    old_id = str(state.get(symbol) or "")
    response = tracker.send_channel_file(channel_id, path, content=caption[:1900])
    new_id = str((response or {}).get("id") or "")
    if not new_id:
        return False
    if old_id and old_id != new_id:
        try:
            tracker._request("DELETE", f"/channels/{channel_id}/messages/{old_id}")
        except discord_transport.DiscordError as exc:
            if "HTTP 404" not in str(exc):
                raise
    state[symbol] = new_id
    _set_state_json(connection, state_key, state)
    return True


SPY_TECHNICALS_STATE_KEY = "upgrade44:spy-technicals"
MARKET_MEMORY_COLLECTION_STATE_KEY = "upgrade44:market-memory-collection"


def market_memory_collection_job(connection: Any) -> str:
    """Collect one real completed SPY session after the US cash close.

    The technical renderer is intentionally read-only, so it cannot make
    stale history fresh by itself.  This lightweight scheduler bridge is
    the missing producer: it calls the existing append-only collection
    cycle once per weekday, after 3:45pm New York time, and records its
    receipt.  No values are fabricated when the provider has not supplied
    a completed session yet.
    """
    from zoneinfo import ZoneInfo
    import market_memory

    eastern = _now().astimezone(ZoneInfo("America/New_York"))
    if eastern.weekday() >= 5:
        return "waiting for next trading day"
    if (eastern.hour, eastern.minute) < (15, 45):
        return "waiting for completed US cash session"
    session = eastern.date().isoformat()
    state = _state_json(connection, MARKET_MEMORY_COLLECTION_STATE_KEY)
    if state.get("session") == session:
        return f"already collected {session}"
    result = market_memory.run_collection_cycle("SPY")
    _set_state_json(
        connection,
        MARKET_MEMORY_COLLECTION_STATE_KEY,
        {"session": session, "collected_at": _iso(), "result": result},
    )
    _engine().store_observation(connection, "market-memory-collection", result)
    daily = result.get("daily", {}).get("new_bars", 0)
    intraday = result.get("intraday_5min", {}).get("new_bars", 0)
    return f"real SPY session {session} collected: {daily} daily / {intraday} five-minute new bars"


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
    channel_id = _channel_id(tracker, "charts")
    removed = 0
    for symbol in list(state):
        if symbol in active:
            continue
        message_id = str(state.get(symbol) or "")
        if message_id and channel_id:
            try:
                tracker._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            except discord_transport.DiscordError as exc:
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
            bars = market_data.get_intraday_history(symbol)
            timeframe = "5-minute session"
            if len(bars) < 2:
                bars = market_data.get_daily_history(symbol, days=45)[-30:]
                timeframe = "30-session fallback"
            output = CHART_DIR / f"{symbol.lower()}-active-session.png"
            variant = _now().toordinal() % CHART_VARIANT_COUNT
            metrics = _render_intraday_chart(symbol, bars, output, variant=variant)
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
        f"**Market:** {'OPEN' if market_data.market_is_open_now()[0] else 'CLOSED'} · "
        f"**Ticker:** {', '.join(active) or market_data.TICKER}",
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
            f"{market_data.fmt_money(item['average_pl_dollars'])} · total "
            f"{market_data.fmt_money(item['total_pl_dollars'])}"
            for item in positive[:6]
        )
    else:
        lines.append("No positive group has reached the evidence threshold yet.")
    lines.append("### What currently needs review")
    if negative:
        lines.extend(
            f"• **{item['feature']} = {item['value']}** · {item['samples']} trades · "
            f"{item['win_rate_pct']:.0f}% wins · avg "
            f"{market_data.fmt_money(item['average_pl_dollars'])} · "
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
        f"average P/L **{market_data.fmt_money(group.get('average_pl_dollars'))}** · "
        f"total P/L **{market_data.fmt_money(group.get('total_pl_dollars'))}**",
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
        report_state = market_data.read_report_state()
        tracker.upsert_channel_message(
            "learning_results",
            report_state,
            "learning-results-v2",
            learning_results_text(summary),
            search_token="Learning Results · Evidence Dashboard",
        )
        market_data.write_report_state(report_state)
    return (
        f"{summary['closed_trades']} closed trades; "
        f"{len(summary['evidence_ready_groups'])} evidence-ready groups; "
        f"{len(summary.get('play_style_suggestions') or [])} improvement reviews"
    )


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
    """Point the module's engine handle at the surviving scheduler.

    Phase 3 purge: this used to replace jobs on local_information_engine_public
    / always_on_operations with "active universe" versions and add several new
    background jobs - all of it wired into the old Discord dashboard/
    discover()-based visibility layer, which was deleted along with
    spy_scanner.py. Both modules are gone and the replaced job names no longer
    exist in local_information_engine.JOBS. Reduced to just setting _ENGINE so
    _engine() (used by runtime_contract.dedupe_and_retire_jobs and the report-
    state helpers below) keeps working; owner-authorized, same basis as the
    other spy_scanner-coupling fixes in this file.
    """
    global _ENGINE_INSTALLED, _ENGINE
    if _ENGINE_INSTALLED:
        return
    import local_information_engine

    _ENGINE = local_information_engine
    _ENGINE_INSTALLED = True


def validate_batch() -> dict[str, Any]:
    # The old Learning Center this batch's supplement targeted was retired;
    # the channel-coverage check that used to run here went with it.
    supplements = _supplement_lessons()
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
