"""Build local IV Rank/Percentile and realized-volatility context over time.

Tradier supplies current option IV but not a free historical IV series. This
runtime records one representative near-the-money IV observation per ticker per
market date, calculates 252-session IV Rank and percentile as evidence accrues,
and adds an immediate 20-session realized-volatility comparison. It never
invents historical IV before it has been observed.
"""

from __future__ import annotations

import json
import math
import os
import sqlite3
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "iv-history.db"
STATUS_PATH = ROOT / "state" / "iv-history-status.json"
MIN_IV_SAMPLES = max(5, int(os.environ.get("IV_RANK_MIN_SAMPLES", "20")))
LOOKBACK_SESSIONS = max(20, int(os.environ.get("IV_RANK_LOOKBACK_SESSIONS", "252")))
ROW_FIELDS = (
    "iv_rank_at_entry",
    "iv_percentile_at_entry",
    "iv_history_samples",
    "realized_vol_20_at_entry",
    "iv_realized_ratio_at_entry",
)
_INSTALLED = False


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=20000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_iv (
            symbol TEXT NOT NULL,
            session_date TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            representative_iv REAL NOT NULL,
            expiration TEXT NOT NULL DEFAULT '',
            contract_count INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL DEFAULT 'tradier-chain',
            PRIMARY KEY(symbol, session_date)
        );
        CREATE INDEX IF NOT EXISTS daily_iv_symbol_date
            ON daily_iv(symbol, session_date DESC);
        """
    )
    connection.commit()
    return connection


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def record(
    symbol: str,
    representative_iv: float,
    *,
    expiration: str = "",
    contract_count: int = 0,
) -> None:
    if representative_iv <= 0:
        return
    session_date = datetime.now().astimezone().date().isoformat()
    connection = _connect()
    try:
        connection.execute(
            """
            INSERT INTO daily_iv(
                symbol, session_date, observed_at, representative_iv,
                expiration, contract_count
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol, session_date) DO UPDATE SET
                observed_at=excluded.observed_at,
                representative_iv=excluded.representative_iv,
                expiration=excluded.expiration,
                contract_count=excluded.contract_count
            """,
            (
                symbol.upper(),
                session_date,
                now_iso(),
                float(representative_iv),
                str(expiration or ""),
                max(0, int(contract_count)),
            ),
        )
        connection.commit()
    finally:
        connection.close()


def metrics(symbol: str, current_iv: float | None = None) -> dict[str, Any]:
    connection = _connect()
    try:
        rows = connection.execute(
            """
            SELECT session_date, representative_iv, expiration, contract_count
            FROM daily_iv WHERE symbol=?
            ORDER BY session_date DESC LIMIT ?
            """,
            (symbol.upper(), LOOKBACK_SESSIONS),
        ).fetchall()
    finally:
        connection.close()
    values = [float(row["representative_iv"]) for row in reversed(rows)]
    current = float(current_iv) if current_iv is not None else (values[-1] if values else None)
    rank: float | None = None
    percentile: float | None = None
    if current is not None and len(values) >= MIN_IV_SAMPLES:
        low = min(values)
        high = max(values)
        rank = 50.0 if high == low else (current - low) / (high - low) * 100
        percentile = sum(value <= current for value in values) / len(values) * 100
        rank = max(0.0, min(rank, 100.0))
        percentile = max(0.0, min(percentile, 100.0))
    return {
        "symbol": symbol.upper(),
        "current_iv": current,
        "samples": len(values),
        "minimum_samples": MIN_IV_SAMPLES,
        "lookback_sessions": LOOKBACK_SESSIONS,
        "iv_rank": None if rank is None else round(rank, 1),
        "iv_percentile": None if percentile is None else round(percentile, 1),
        "low_iv": None if not values else min(values),
        "high_iv": None if not values else max(values),
        "collecting": len(values) < MIN_IV_SAMPLES,
    }


def realized_volatility(history: list[dict[str, Any]], period: int = 20) -> float | None:
    closes: list[float] = []
    for row in history:
        try:
            close = float(row.get("close"))
        except (TypeError, ValueError):
            continue
        if close > 0:
            closes.append(close)
    if len(closes) <= period:
        return None
    returns = [
        math.log(current / previous)
        for previous, current in zip(closes[-period - 1 : -1], closes[-period:])
        if previous > 0 and current > 0
    ]
    if len(returns) < period:
        return None
    return statistics.pstdev(returns) * math.sqrt(252)


def _representative_iv(
    ford_scan: Any,
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
) -> tuple[float | None, str, int]:
    rows: list[tuple[float, str, float]] = []
    spot = None
    for option in quote_map.values():
        iv = ford_scan.iv_value(option)
        strike = ford_scan.as_float(option.get("strike"))
        underlying = ford_scan.as_float(option.get("underlying_price"))
        if spot is None and underlying is not None:
            spot = underlying
        if iv is None or iv <= 0 or strike is None:
            continue
        rows.append((float(iv), str(option.get("expiration_date") or ""), float(strike)))
    if not rows:
        for candidate in candidates:
            iv = ford_scan.as_float(candidate.get("iv"))
            strike = ford_scan.as_float(candidate.get("strike"))
            if iv is not None and iv > 0:
                rows.append((float(iv), str(candidate.get("expiration") or ""), float(strike or 0)))
    if not rows:
        return None, "", 0
    if spot is not None:
        rows.sort(key=lambda item: abs(item[2] - spot))
        selected = rows[: max(3, min(12, len(rows)))]
    else:
        selected = rows
    value = statistics.median(item[0] for item in selected)
    expiration = next((item[1] for item in selected if item[1]), "")
    return float(value), expiration, len(rows)


def install(ford_scan: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    for field in ROW_FIELDS:
        if field not in ford_scan.LOG_HEADER:
            ford_scan.LOG_HEADER.append(field)

    original_scan_candidates = ford_scan.scan_candidates
    original_candidate_to_row = ford_scan.candidate_to_row

    def scan_candidates(spot_price: float):
        candidates, quote_map, stats = original_scan_candidates(spot_price)
        symbol = str(ford_scan.TICKER).upper()
        representative, expiration, count = _representative_iv(
            ford_scan, candidates, quote_map
        )
        if representative is not None:
            record(
                symbol,
                representative,
                expiration=expiration,
                contract_count=count,
            )
        iv_context = metrics(symbol, representative)
        history = ford_scan.get_daily_history(symbol, days=60)
        rv20 = realized_volatility(history, period=20)
        iv_ratio = (
            representative / rv20
            if representative is not None and rv20 and rv20 > 0
            else None
        )
        for candidate in candidates:
            candidate_iv = ford_scan.as_float(candidate.get("iv"), representative)
            candidate_context = metrics(symbol, candidate_iv)
            candidate["iv_rank"] = candidate_context["iv_rank"]
            candidate["iv_percentile"] = candidate_context["iv_percentile"]
            candidate["iv_history_samples"] = candidate_context["samples"]
            candidate["realized_vol_20"] = rv20
            candidate["iv_realized_ratio"] = iv_ratio
            if candidate_context["collecting"]:
                note = (
                    f"IV history collecting {candidate_context['samples']}/"
                    f"{candidate_context['minimum_samples']} daily samples"
                )
            else:
                note = (
                    f"IV Rank {candidate_context['iv_rank']:.1f}; "
                    f"IV Percentile {candidate_context['iv_percentile']:.1f}"
                )
            if rv20 is not None and candidate_iv is not None:
                note += (
                    f"; IV {candidate_iv * 100:.1f}% vs 20-session "
                    f"realized {rv20 * 100:.1f}%"
                )
            candidate["setup_reason"] = (
                str(candidate.get("setup_reason") or "") + "; " + note
            ).strip("; ")
        stats["iv_context"] = {
            **iv_context,
            "realized_vol_20": rv20,
            "iv_realized_ratio": iv_ratio,
        }
        _atomic_json(
            STATUS_PATH,
            {
                "updated_at": now_iso(),
                "symbol": symbol,
                "iv_context": stats["iv_context"],
                "chain_contracts_with_iv": count,
            },
        )
        return candidates, quote_map, stats

    def candidate_to_row(candidate, rows, timestamp):
        row = original_candidate_to_row(candidate, rows, timestamp)
        row["iv_rank_at_entry"] = (
            "" if candidate.get("iv_rank") is None else str(candidate["iv_rank"])
        )
        row["iv_percentile_at_entry"] = (
            ""
            if candidate.get("iv_percentile") is None
            else str(candidate["iv_percentile"])
        )
        row["iv_history_samples"] = str(candidate.get("iv_history_samples") or 0)
        row["realized_vol_20_at_entry"] = (
            ""
            if candidate.get("realized_vol_20") is None
            else str(round(float(candidate["realized_vol_20"]), 4))
        )
        row["iv_realized_ratio_at_entry"] = (
            ""
            if candidate.get("iv_realized_ratio") is None
            else str(round(float(candidate["iv_realized_ratio"]), 3))
        )
        return row

    ford_scan.scan_candidates = scan_candidates
    ford_scan.candidate_to_row = candidate_to_row
    ford_scan.IV_HISTORY_RUNTIME = "local-iv-rank-percentile-v1"
    _INSTALLED = True


__all__ = ["install", "metrics", "realized_volatility", "record"]
