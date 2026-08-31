"""GROK market adapter — uses only shared neutral MarketView.

No private strategy imports. Builds the feature dict and option chain
shape expected by GROK's independent engine/contract_selection layers.
"""

from __future__ import annotations

from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

CENTRAL = ZoneInfo("America/Chicago")
MARKET_CLOSE = time(15, 0)


def _bars_to_features(bars: list[dict[str, Any]]) -> dict[str, Any]:
    """Lightweight causal features from completed bars only."""
    if not bars or len(bars) < 5:
        return {}

    closes = []
    volumes = []
    for b in bars:
        c = b.get("close") or b.get("c")
        v = b.get("volume") or b.get("v") or 0
        if c is not None:
            closes.append(float(c))
            volumes.append(float(v))

    if len(closes) < 5:
        return {}

    def ret(n: int) -> float | None:
        if len(closes) <= n:
            return None
        prev = closes[-(n + 1)]
        if prev == 0:
            return None
        return (closes[-1] - prev) / prev

    # Simple RSI-14 approximation
    gains, losses = [], []
    for i in range(1, min(15, len(closes))):
        d = closes[-i] - closes[-i - 1] if len(closes) > i else 0
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 0
    rs = avg_gain / avg_loss if avg_loss > 0 else 100.0
    rsi = 100 - (100 / (1 + rs))

    # Bollinger width (20 if available else available window)
    window = closes[-20:] if len(closes) >= 20 else closes
    mean = sum(window) / len(window)
    var = sum((x - mean) ** 2 for x in window) / len(window)
    std = var ** 0.5
    bb_width = (2 * std) / mean if mean else None

    # VWAP distance (session approx using volume-weighted closes)
    total_pv = sum(c * max(v, 1) for c, v in zip(closes, volumes))
    total_v = sum(max(v, 1) for v in volumes)
    vwap = total_pv / total_v if total_v else closes[-1]
    vwap_distance_pct = (closes[-1] - vwap) / vwap if vwap else None

    avg_vol = sum(volumes[-10:]) / max(len(volumes[-10:]), 1)
    rel_vol = volumes[-1] / avg_vol if avg_vol > 0 else None

    # Crude ADX proxy: average absolute return magnitude
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
    }


def _normalize_chain(options_payload: dict[str, Any] | list) -> list[dict[str, Any]]:
    if isinstance(options_payload, list):
        contracts = options_payload
    else:
        contracts = options_payload.get("contracts") or options_payload.get("options") or []
    out = []
    for c in contracts:
        if not isinstance(c, dict):
            continue
        symbol = c.get("option_symbol") or c.get("symbol")
        if not symbol:
            continue
        out.append({
            "symbol": symbol,
            "option_symbol": symbol,
            "option_type": str(c.get("option_type") or c.get("type") or "").upper(),
            "strike": float(c.get("strike") or 0),
            "bid": float(c.get("bid") or 0),
            "ask": float(c.get("ask") or 0),
            "volume": int(c.get("volume") or 0),
            "open_interest": int(c.get("open_interest") or c.get("openInterest") or 0),
            "delta": c.get("delta"),
            "expiration": c.get("expiration") or c.get("expiration_date"),
        })
    return out


class GrokMarketAdapter:
    """Thin wrapper around shared backtest_lab.MarketView for live/paper cycles."""

    def __init__(self, market_view: Any | None = None):
        if market_view is None:
            import backtest_lab
            market_view = backtest_lab.MarketView("SPY")
        self.mv = market_view

    def features(self, as_of: datetime | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(CENTRAL)
        bars = self.mv.bars_as_of(as_of, lookback_minutes=60) or []
        if isinstance(bars, dict):
            bars = bars.get("bars") or bars.get("data") or []
        return _bars_to_features(list(bars))

    def chain(self, as_of: datetime | None = None) -> list[dict[str, Any]]:
        as_of = as_of or datetime.now(CENTRAL)
        options = self.mv.options_as_of(as_of) or {}
        return _normalize_chain(options)

    def underlying(self, as_of: datetime | None = None) -> dict[str, Any]:
        as_of = as_of or datetime.now(CENTRAL)
        return self.mv.market_as_of(as_of) or {}

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
            self.underlying()
            return True
        except Exception:
            return False
