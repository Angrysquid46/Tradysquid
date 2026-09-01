"""GROK market adapter — shared neutral data only.

Live paper cycles prefer Tradier via market_data (quotes, 1-min timesales,
0DTE chain). Point-in-time parquet MarketView is still tried first when it
has fresh data; empty/stale parquet no longer forces permanent NO_ACTION.
"""

from __future__ import annotations

import logging
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
MARKET_CLOSE = time(15, 0)
logger = logging.getLogger("grok.market_adapter")


def _bars_to_features(bars: list[dict[str, Any]]) -> dict[str, Any]:
    if not bars or len(bars) < 5:
        return {}

    closes: list[float] = []
    volumes: list[float] = []
    for b in bars:
        c = b.get("close") or b.get("c") or b.get("price")
        v = b.get("volume") or b.get("v") or 0
        if c is not None:
            try:
                closes.append(float(c))
                volumes.append(float(v or 0))
            except (TypeError, ValueError):
                continue

    if len(closes) < 5:
        return {}

    def ret(n: int) -> float | None:
        if len(closes) <= n:
            return None
        prev = closes[-(n + 1)]
        if prev == 0:
            return None
        return (closes[-1] - prev) / prev

    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        d = closes[-i] - closes[-i - 1] if len(closes) > i else 0.0
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_gain = sum(gains) / len(gains) if gains else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
    rsi = 100 - (100 / (1 + rs))

    window = closes[-20:] if len(closes) >= 20 else closes
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / len(window)
    std = var ** 0.5
    bb_width = (2 * std) / mean if mean else None

    total_pv = sum(c * max(v, 1) for c, v in zip(closes, volumes))
    total_v = sum(max(v, 1) for v in volumes)
    vwap = total_pv / total_v if total_v else closes[-1]
    vwap_distance_pct = (closes[-1] - vwap) / vwap if vwap else None

    avg_vol = sum(volumes[-10:]) / max(len(volumes[-10:]), 1)
    rel_vol = volumes[-1] / avg_vol if avg_vol > 0 else None

    abs_rets = [abs(ret(i) or 0) for i in range(1, min(15, len(closes)))]
    adx_proxy = (sum(abs_rets) / len(abs_rets) * 1000) if abs_rets else None

    return {
        "ret_3m": ret(3),
        "ret_5m": ret(5),
        "rsi_14": rsi,
        "adx_14": adx_proxy,
        "bb_width": bb_width,
        "vwap_distance_pct": vwap_distance_pct,
        "relative_volume": rel_vol,
        "last_close": closes[-1],
        "bar_count": len(closes),
    }


def _normalize_chain(options_payload: dict[str, Any] | list) -> list[dict[str, Any]]:
    if isinstance(options_payload, list):
        contracts = options_payload
    else:
        contracts = (
            options_payload.get("contracts")
            or options_payload.get("options")
            or []
        )
    out = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        symbol = c.get("option_symbol") or c.get("symbol")
        if not symbol:
            continue
        greeks = c.get("greeks") if isinstance(c.get("greeks"), dict) else {}
        delta = c.get("delta")
        if delta is None and greeks:
            delta = greeks.get("delta")
        out.append({
            "symbol": symbol,
            "option_symbol": symbol,
            "option_type": str(c.get("option_type") or c.get("type") or "").upper(),
            "strike": float(c.get("strike") or 0),
            "bid": float(c.get("bid") or 0),
            "ask": float(c.get("ask") or 0),
            "volume": int(c.get("volume") or 0),
            "open_interest": int(
                c.get("open_interest") or c.get("openInterest") or 0
            ),
            "delta": delta,
            "expiration": c.get("expiration") or c.get("expiration_date"),
        })
    return out


def _live_bars_1m() -> list[dict[str, Any]]:
    import market_data

    # Prefer 1-minute tape for 0DTE decisions; fall back to 5-min if needed.
    try:
        bars = market_data.get_intraday_history("SPY", interval="1min")
    except Exception as exc:
        logger.warning("live 1min bars failed: %s", exc)
        bars = []
    if len(bars) < 5:
        try:
            bars = market_data.get_intraday_history("SPY", interval="5min")
        except Exception as exc:
            logger.warning("live 5min bars failed: %s", exc)
            bars = []
    return list(bars or [])


def _live_0dte_chain() -> list[dict[str, Any]]:
    import market_data

    today = market_data.now_ct().date().isoformat()
    try:
        expirations = market_data.get_expirations("SPY") or []
    except Exception as exc:
        logger.warning("live expirations failed: %s", exc)
        return []
    if today not in expirations:
        # No 0DTE listed (weekend/holiday) — refuse rather than invent
        logger.info("no SPY 0DTE expiration for %s (have %s)", today, expirations[:3])
        return []
    try:
        raw = market_data.get_chain("SPY", today) or []
    except Exception as exc:
        logger.warning("live chain failed: %s", exc)
        return []
    return _normalize_chain(raw)


class GrokMarketAdapter:
    """Live-first adapter for paper competition cycles."""

    def __init__(self, market_view: Any | None = None):
        self._mv = market_view  # lazy optional parquet view

    def _market_view(self) -> Any | None:
        if self._mv is not None:
            return self._mv
        try:
            import backtest_lab

            self._mv = backtest_lab.MarketView("SPY")
        except Exception as exc:
            logger.warning("MarketView unavailable: %s", exc)
            self._mv = None
        return self._mv

    def features(self, as_of: datetime | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(CENTRAL)
        # 1) parquet if present and dense enough
        mv = self._market_view()
        if mv is not None:
            try:
                bars = mv.bars_as_of(as_of, lookback_minutes=60) or []
                if isinstance(bars, dict):
                    bars = bars.get("bars") or bars.get("data") or []
                feat = _bars_to_features(list(bars))
                if feat.get("bar_count", 0) >= 5:
                    return feat
            except Exception as exc:
                logger.warning("parquet features failed: %s", exc)
        # 2) live Tradier
        feat = _bars_to_features(_live_bars_1m())
        if not feat:
            logger.warning("features empty — no parquet bars and live tape thin")
        return feat

    def chain(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        as_of = as_of or datetime.now(CENTRAL)
        mv = self._market_view()
        if mv is not None:
            try:
                options = mv.options_as_of(as_of) or {}
                contracts = _normalize_chain(options)
                # Only trust parquet chain if non-empty and not marked dead
                if contracts and options.get("tier") in (None, "A", "B", "TIER_A", "TIER_B"):
                    # backtest_lab uses "A"/"B"/"C"
                    if options.get("tier") != "C":
                        return contracts
            except Exception as exc:
                logger.warning("parquet chain failed: %s", exc)
        live = _live_0dte_chain()
        if not live:
            logger.warning("chain empty — no usable 0DTE contracts")
        return live

    def underlying(self, as_of: datetime | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(CENTRAL)
        mv = self._market_view()
        if mv is not None:
            try:
                snap = mv.market_as_of(as_of) or {}
                if snap.get("tier") != "C" and snap.get("quote"):
                    return snap
            except Exception:
                pass
        try:
            import market_data

            q = market_data.get_quote("SPY") or {}
            return {"tier": "LIVE", "quote": q}
        except Exception as exc:
            logger.warning("underlying quote failed: %s", exc)
            return {}

    def is_session_open(self, as_of: datetime | None = None) -> bool:
        as_of = as_of or datetime.now(CENTRAL)
        local = as_of.astimezone(CENTRAL) if as_of.tzinfo else as_of.replace(tzinfo=CENTRAL)
        if local.weekday() >= 5:
            return False
        minute = local.hour * 60 + local.minute
        return 8 * 60 + 30 <= minute <= 15 * 60

    def minutes_to_close(self, as_of: datetime | None = None) -> float:
        as_of = as_of or datetime.now(CENTRAL)
        local = as_of.astimezone(CENTRAL) if as_of.tzinfo else as_of.replace(tzinfo=CENTRAL)
        close = local.replace(hour=15, minute=0, second=0, microsecond=0)
        return max(0.0, (close - local).total_seconds() / 60.0)

    def provider_ok(self) -> bool:
        try:
            import market_data

            if not market_data.TRADIER_TOKEN:
                return False
            q = market_data.get_quote("SPY")
            return bool(q)
        except Exception:
            return False
