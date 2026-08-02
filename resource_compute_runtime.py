"""Offload review-only outcome statistics to the optional resource worker.

Production submits sanitized closed-trade features, never credentials or order
capabilities. The worker calculates grouped expectancy, profit factor,
drawdown, excursion statistics, and bootstrap confidence intervals. Results are
stored for learning/review and never change scanner or risk rules automatically.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import resource_mesh

ROOT = Path(__file__).resolve().parent
RESULT_PATH = ROOT / "state" / "worker-outcome-analysis.json"
BOOTSTRAP_SAMPLES = max(
    200, min(5000, int(os.environ.get("OUTCOME_BOOTSTRAP_SAMPLES", "1000")))
)
MIN_GROUP_SAMPLES = max(
    2, int(os.environ.get("OUTCOME_MIN_GROUP_SAMPLES", "5"))
)
_INSTALLED = False


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _percentile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * max(0.0, min(probability, 1.0))
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _bootstrap(values: list[float], seed: str) -> dict[str, Any]:
    if not values:
        return {"samples": 0, "mean_95_low": None, "mean_95_high": None}
    randomizer = random.Random(seed)
    means: list[float] = []
    size = len(values)
    for _ in range(BOOTSTRAP_SAMPLES):
        sample = [values[randomizer.randrange(size)] for _ in range(size)]
        means.append(statistics.fmean(sample))
    return {
        "samples": BOOTSTRAP_SAMPLES,
        "mean_95_low": _percentile(means, 0.025),
        "mean_95_high": _percentile(means, 0.975),
    }


def _max_drawdown(values: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = min(drawdown, equity - peak)
    return drawdown


def _group_metrics(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    pnl = [_number(row.get("pnl")) for row in rows]
    wins = [value for value in pnl if value > 0]
    losses = [value for value in pnl if value <= 0]
    mfe = [_number(row.get("mfe")) for row in rows if row.get("mfe") not in (None, "")]
    mae = [_number(row.get("mae")) for row in rows if row.get("mae") not in (None, "")]
    win_flags = [1.0 if value > 0 else 0.0 for value in pnl]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    bootstrap = _bootstrap(pnl, f"pnl:{label}:{len(rows)}")
    win_bootstrap = _bootstrap(win_flags, f"win:{label}:{len(rows)}")
    return {
        "label": label,
        "count": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": (sum(win_flags) / len(win_flags) * 100) if win_flags else None,
        "total_pnl": sum(pnl),
        "average_pnl": statistics.fmean(pnl) if pnl else None,
        "median_pnl": statistics.median(pnl) if pnl else None,
        "profit_factor": (
            gross_profit / gross_loss if gross_loss > 0 else None
        ),
        "average_win": statistics.fmean(wins) if wins else None,
        "average_loss": statistics.fmean(losses) if losses else None,
        "max_drawdown": _max_drawdown(pnl),
        "average_mfe_pct": statistics.fmean(mfe) if mfe else None,
        "average_mae_pct": statistics.fmean(mae) if mae else None,
        "pnl_mean_95_low": bootstrap["mean_95_low"],
        "pnl_mean_95_high": bootstrap["mean_95_high"],
        "win_rate_95_low_pct": (
            None
            if win_bootstrap["mean_95_low"] is None
            else win_bootstrap["mean_95_low"] * 100
        ),
        "win_rate_95_high_pct": (
            None
            if win_bootstrap["mean_95_high"] is None
            else win_bootstrap["mean_95_high"] * 100
        ),
        "evidence_ready": len(rows) >= MIN_GROUP_SAMPLES,
    }


def analyze(payload: dict[str, Any]) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in payload.get("trades") or []
        if isinstance(row, dict)
    ]
    groups: dict[str, dict[str, list[dict[str, Any]]]] = {
        "strategy": defaultdict(list),
        "ticker": defaultdict(list),
        "regime": defaultdict(list),
        "direction": defaultdict(list),
        "strategy_ticker": defaultdict(list),
    }
    for row in rows:
        strategy = str(
            row.get("strategy") or row.get("play_type") or "UNKNOWN"
        )
        ticker = str(row.get("ticker") or "UNKNOWN")
        regime = str(row.get("regime") or "UNKNOWN")
        direction = str(row.get("direction") or "UNKNOWN")
        groups["strategy"][strategy].append(row)
        groups["ticker"][ticker].append(row)
        groups["regime"][regime].append(row)
        groups["direction"][direction].append(row)
        groups["strategy_ticker"][f"{strategy}|{ticker}"].append(row)

    output_groups: dict[str, list[dict[str, Any]]] = {}
    for group_name, buckets in groups.items():
        metrics = [
            _group_metrics(bucket, f"{group_name}:{label}")
            for label, bucket in buckets.items()
        ]
        metrics.sort(
            key=lambda item: (
                bool(item["evidence_ready"]),
                item["count"],
                item["total_pnl"],
            ),
            reverse=True,
        )
        output_groups[group_name] = metrics

    return {
        "generated_at": now_iso(),
        "source_digest": payload.get("source_digest"),
        "trade_count": len(rows),
        "bootstrap_samples": BOOTSTRAP_SAMPLES,
        "minimum_group_samples": MIN_GROUP_SAMPLES,
        "overall": _group_metrics(rows, "overall"),
        "groups": output_groups,
        "contract": (
            "historical review only; no scanner, strategy, target, stop, "
            "risk, or deployment setting is modified"
        ),
    }


def _sanitize_rows(ford_scan: Any, rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in ford_scan.closed_rows(rows):
        output.append(
            {
                "trade_id": str(row.get("trade_id") or ""),
                "closed_at": str(row.get("closed_at") or ""),
                "ticker": str(row.get("ticker") or "").upper(),
                "strategy": str(
                    row.get("strategy_profile")
                    or ford_scan.play_style_key(row)
                ),
                "play_type": str(row.get("play_type") or ""),
                "direction": str(row.get("call_or_put") or ""),
                "regime": str(row.get("market_regime") or ""),
                "outcome": str(row.get("outcome") or ""),
                "pnl": ford_scan.realized_pl_dollars(row),
                "return_pct": _number(row.get("pct_gain_loss")),
                "mfe": _number(row.get("max_favorable_pct")),
                "mae": _number(row.get("max_adverse_pct")),
                "delta": _number(row.get("delta_at_entry")),
                "theta": _number(row.get("theta_at_entry")),
                "iv": _number(row.get("iv_at_entry")),
                "iv_rank": _number(row.get("iv_rank_at_entry")),
                "iv_percentile": _number(
                    row.get("iv_percentile_at_entry")
                ),
                "setup_score": _number(row.get("setup_score")),
            }
        )
    return output


def install(
    engine: Any,
    ford_scan: Any,
    resource_mesh_runtime: Any,
    worker: Any,
) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    resource_mesh.ALLOWED_KINDS.add("outcome-analysis")
    worker.HANDLERS["outcome-analysis"] = analyze

    original_process = resource_mesh_runtime._process_result

    def process_result(
        current_engine: Any,
        trade_intelligence: Any,
        item: dict[str, Any],
    ) -> dict[str, Any]:
        if str(item.get("kind") or "") == "outcome-analysis":
            result = dict(item.get("result") or {})
            _atomic_json(RESULT_PATH, item)
            return {
                "kind": "outcome-analysis",
                "trade_count": result.get("trade_count", 0),
                "evidence_ready": bool(
                    (result.get("overall") or {}).get("evidence_ready")
                ),
            }
        return original_process(current_engine, trade_intelligence, item)

    resource_mesh_runtime._process_result = process_result

    def dispatch_job(connection: Any) -> str:
        with engine.POSITION_FILE_LOCK:
            rows = ford_scan.read_log()
        sanitized = _sanitize_rows(ford_scan, rows)
        digest = hashlib.sha256(
            json.dumps(
                sanitized,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        submitted = resource_mesh.submit_task(
            "outcome-analysis",
            {
                "generated_at": now_iso(),
                "source_digest": digest,
                "trades": sanitized,
            },
            priority=40,
            dedupe_key=f"outcome-analysis:{digest}",
            dedupe_seconds=6 * 3600,
            expires_seconds=24 * 3600,
        )
        engine.store_observation(
            connection,
            "resource-outcome-dispatch",
            {
                "trades": len(sanitized),
                "digest": digest,
                "submitted": submitted,
                "at": now_iso(),
            },
        )
        return (
            f"{len(sanitized)} closed trades; "
            f"{'queued' if submitted.get('created') else 'unchanged'}"
        )

    if not any(
        job.name == "resource-outcome-analysis" for job in engine.JOBS
    ):
        engine.JOBS.append(
            engine.Job(
                "resource-outcome-analysis",
                timedelta(hours=6),
                dispatch_job,
                background=True,
                retry_interval=timedelta(minutes=15),
            )
        )

    engine.RESOURCE_COMPUTE_RUNTIME = "worker-outcome-analysis-v1"
    _INSTALLED = True


__all__ = ["analyze", "install"]
