"""Phase 6: shadow mode.

Every scan cycle, the current trained model scores whatever real
candidate the real opening-range signal finds - logged to its own file,
entirely separate from both the live paper-trading log (tradelog.py) and
the historical backtest log (backtest.py). Nothing here ever places a
real (paper) trade or touches bankroll.py; shadow rows exist purely to
build an honest track record of "what would this model have called"
against real, live market data before Phase 7 ever lets a model
influence a real decision.

Reuses engine.find_candidate and engine.evaluate_exit_for_row - the exact
same real entry-detection and exit-evaluation logic the live bot runs -
rather than maintaining a second copy that could silently drift from it.
"""

from __future__ import annotations

import csv
import json
import tempfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import lightgbm as lgb
import numpy as np

import engine
import features
import market_features
import train
from engine import s  # the same spy_scanner import engine.py already set up

PLAY_TYPE = "SPY_EVOLVE_SHADOW"
ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
SHADOW_LOG_PATH = STATE_DIR / "shadow_trades.csv"

HEADER = [
    "shadow_id", "timestamp", "option_symbol", "call_or_put", "strike", "expiration",
    "entry_price", "spot_price_at_entry", "delta_at_entry", "iv_at_entry",
    "market_regime", "market_condition_at_entry",
    "vix_at_entry", "sentiment_at_entry", "put_call_ratio_at_entry",
    "model_score", "thesis",
    "outcome", "exit_price", "closed_at", "last_signal", "pl_pct",
    "max_favorable_pct", "max_adverse_pct", "last_evaluated_at",
]


def blank_row() -> dict[str, str]:
    return {field: "" for field in HEADER}


def read_log(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def write_log(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", newline="", encoding="utf-8", dir=path.parent,
            prefix=f"{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        temp_path.replace(path)
    except BaseException:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise


def open_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("outcome") == "OPEN"]


def next_shadow_id(rows: list[dict[str, str]], timestamp) -> str:
    date_str = timestamp.strftime("%Y%m%d")
    prefix = f"SHADOW-{date_str}-"
    existing = [row.get("shadow_id", "") for row in rows if row.get("shadow_id", "").startswith(prefix)]
    return f"{prefix}{len(existing) + 1:03d}"


def score_candidate(
    candidate: dict[str, Any], context: dict[str, Any], market_condition: str,
    vix: float | None, sentiment: float | None, put_call_ratio: float | None,
) -> float | None:
    """Loads the current trained model fresh every call - Phase 5's
    retrain loop may have produced a newer one since the last score, and
    a LightGBM text-format model is cheap enough to reload that caching
    isn't worth the staleness risk. Returns None (never a fabricated
    score) when no model has been trained yet.

    variant_label/price_source_at_entry are backtest-only concepts this
    live candidate genuinely doesn't have a value for - left as
    placeholders the model's own vocabulary maps to its UNKNOWN category
    code, which is the honest outcome, not a workaround. stop_pct/
    target_pct/floor_pct/floor_trigger_pct use the live SPY_0DTE
    constants directly, since shadow mode's hypothetical exit is
    evaluated with the exact same real exit signal the live bot uses."""
    if not train.MODEL_PATH.exists() or not train.METADATA_PATH.exists():
        return None
    try:
        metadata = json.loads(train.METADATA_PATH.read_text(encoding="utf-8"))
        model = lgb.Booster(model_file=str(train.MODEL_PATH))
    except (OSError, ValueError, lgb.basic.LightGBMError):
        return None
    vocabulary = metadata.get("vocabulary", {})
    row = {
        "delta_at_entry": str(candidate.get("delta", "")),
        "iv_at_entry": str(candidate.get("iv", "")),
        "vix_at_entry": "" if vix is None else str(vix),
        "sentiment_at_entry": "" if sentiment is None else str(sentiment),
        "put_call_ratio_at_entry": "" if put_call_ratio is None else str(put_call_ratio),
        "stop_pct": str(s.SPY_0DTE_STOP_PCT),
        "target_pct": str(s.SPY_0DTE_TARGET_PCT),
        "floor_pct": str(s.SPY_0DTE_FLOOR_PCT),
        "floor_trigger_pct": str(s.SPY_0DTE_FLOOR_TRIGGER_PCT),
        "call_or_put": candidate.get("call_or_put", ""),
        "market_condition": market_condition or "",
        "regime": context.get("regime", ""),
        "variant_label": "live",
        "price_source_at_entry": "real",
    }
    vector = features.row_to_feature_vector(row, vocabulary)
    prediction = model.predict(np.array([vector], dtype=float))
    return round(float(prediction[0]), 4)


def _close_open_shadow_rows(rows: list[dict[str, str]], timestamp) -> int:
    open_shadow_rows = open_rows(rows)
    if not open_shadow_rows:
        return 0
    quote_map = s.get_quotes(
        [row["option_symbol"] for row in open_shadow_rows if row.get("option_symbol")],
        include_greeks=True,
    )
    closed_count = 0
    for row in open_shadow_rows:
        quote = quote_map.get(row.get("option_symbol", ""))
        result = engine.evaluate_exit_for_row(row, quote, timestamp)
        if result is None or not result["should_close"]:
            continue
        row["outcome"] = "WIN" if result["pnl_pct"] > 0 else ("LOSS" if result["pnl_pct"] < 0 else "SCRATCH")
        row["exit_price"] = str(round(result["mark"], 2))
        row["closed_at"] = timestamp.isoformat()
        row["last_signal"] = result["signal"]
        row["pl_pct"] = str(round(result["pnl_pct"]))
        closed_count += 1
    return closed_count


def _try_open_shadow_position(rows: list[dict[str, str]], timestamp, spot_price: float) -> dict[str, str] | None:
    # One shadow position at a time, mirroring the live bot's own phase-1
    # simplification - the opening-range signal only fires once per
    # session anyway, so this isn't a real constraint in practice.
    if open_rows(rows):
        return None
    found = engine.find_candidate(timestamp, spot_price, play_type=PLAY_TYPE)
    if not found["qualified"]:
        return None
    best = found["candidate"]
    context = found["context"]
    market_condition = found["market_condition"]
    chain = found["chain"]
    today_str = found["today_str"]

    put_call_ratio = market_features.put_call_ratio_from_chain(chain)
    vix_series = market_features.fetch_vix_series(
        (timestamp.date() - timedelta(days=10)).isoformat(), today_str
    )
    vix = market_features.vix_on_or_before(today_str, vix_series)
    sentiment = market_features.market_sentiment_for_date(today_str)
    model_score = score_candidate(best, context, market_condition, vix, sentiment, put_call_ratio)

    row = blank_row()
    row.update(
        {
            "shadow_id": next_shadow_id(rows, timestamp),
            "timestamp": timestamp.isoformat(),
            "option_symbol": best["option_symbol"],
            "call_or_put": best["call_or_put"],
            "strike": str(best["strike"]),
            "expiration": best["expiration"],
            "entry_price": str(best["entry_price"]),
            "spot_price_at_entry": str(round(spot_price, 2)),
            "delta_at_entry": str(best["delta"]),
            "iv_at_entry": str(best["iv"]),
            "market_regime": context["regime"],
            "market_condition_at_entry": market_condition,
            "vix_at_entry": "" if vix is None else str(vix),
            "sentiment_at_entry": "" if sentiment is None else str(sentiment),
            "put_call_ratio_at_entry": "" if put_call_ratio is None else str(put_call_ratio),
            "model_score": "" if model_score is None else str(model_score),
            "thesis": engine.build_thesis(best, context, market_condition),
            "outcome": "OPEN",
            "max_favorable_pct": "0",
            "max_adverse_pct": "0",
            "last_evaluated_at": timestamp.isoformat(),
        }
    )
    rows.append(row)
    return row


def run_shadow_cycle() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    rows = read_log(SHADOW_LOG_PATH)

    is_open, timestamp = s.market_is_open_now()
    if not is_open:
        return {"status": "market closed"}

    spot = s.get_quote(s.TICKER)
    if not spot or s.as_float(spot.get("last")) is None:
        return {"status": "spot quote unavailable"}
    spot_price = float(spot["last"])

    closed_count = _close_open_shadow_rows(rows, timestamp)
    opened_row = _try_open_shadow_position(rows, timestamp, spot_price)

    write_log(SHADOW_LOG_PATH, rows)
    return {
        "status": "ok",
        "closed": closed_count,
        "opened": bool(opened_row),
        "model_score": (opened_row.get("model_score") or None) if opened_row else None,
    }


if __name__ == "__main__":
    print(run_shadow_cycle())
