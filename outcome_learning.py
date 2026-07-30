"""Offline, review-first learning from completed tracked trades.

This module never changes scanner rules or places trades. It exports sanitized
outcomes and evidence summaries to a OneDrive-backed folder for human review.
"""

from __future__ import annotations

import csv
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import ford_scan

ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = Path(os.environ.get("OneDrive", str(ROOT.parent))) / "Tradysquid-Learning"
ARCHIVE_DIR = Path(os.environ.get("LEARNING_ARCHIVE_DIR", str(DEFAULT_ARCHIVE)))
MIN_SAMPLE = int(os.environ.get("LEARNING_MIN_SAMPLE", "20"))

EXPORT_FIELDS = [
    "trade_id", "ticker", "play_type", "call_or_put", "timestamp", "closed_at",
    "expiration", "entry_price", "exit_price", "delta_at_entry", "theta_at_entry",
    "iv_at_entry", "pop_estimate", "max_profit", "max_risk", "breakeven",
    "open_interest_at_entry", "bid_ask_width_at_entry", "option_volume_at_entry",
    "setup_score", "market_regime", "outcome", "pct_gain_loss",
    "realized_pl_dollars", "max_favorable_pct", "max_adverse_pct", "last_signal",
]


def number(row: dict[str, str], key: str) -> float | None:
    return ford_scan.as_float(row.get(key))


def days_to_expiration(row: dict[str, str]) -> int | None:
    try:
        opened = datetime.fromisoformat(str(row.get("timestamp") or "")).date()
        expiry = datetime.fromisoformat(str(row.get("expiration") or "")).date()
    except ValueError:
        return None
    return (expiry - opened).days


def sanitized_rows() -> list[dict[str, Any]]:
    rows = ford_scan.closed_rows(ford_scan.read_log())
    exports: list[dict[str, Any]] = []
    for row in rows:
        item = {field: row.get(field, "") for field in EXPORT_FIELDS}
        item["dte_at_entry"] = days_to_expiration(row)
        exports.append(item)
    return exports


def bucket(value: float | None, cuts: tuple[float, ...]) -> str:
    if value is None:
        return "missing"
    lower = float("-inf")
    for upper in cuts:
        if value < upper:
            return f"{lower:g} to {upper:g}" if lower != float("-inf") else f"under {upper:g}"
        lower = upper
    return f"{lower:g} and over"


def feature_groups(row: dict[str, Any]) -> dict[str, str]:
    return {
        "ticker": str(row.get("ticker") or "F").upper(),
        "strategy": str(row.get("play_type") or "UNKNOWN").upper(),
        "direction": str(row.get("call_or_put") or "UNKNOWN").upper(),
        "regime": str(row.get("market_regime") or "UNKNOWN").upper(),
        "delta_band": bucket(ford_scan.as_float(row.get("delta_at_entry")), (0.15, 0.25, 0.40, 0.60, 0.75)),
        "iv_band": bucket(ford_scan.as_float(row.get("iv_at_entry")), (0.25, 0.40, 0.60, 0.90)),
        "dte_band": bucket(ford_scan.as_float(row.get("dte_at_entry")), (7, 14, 21, 30, 45, 61)),
        "score_band": bucket(ford_scan.as_float(row.get("setup_score")), (40, 55, 70, 85)),
        "open_interest_band": bucket(ford_scan.as_float(row.get("open_interest_at_entry")), (100, 500, 1000, 2500, 5000)),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        for feature, value in feature_groups(row).items():
            groups[(feature, value)].append(row)
    summaries = []
    for (feature, value), members in sorted(groups.items()):
        pnl = [ford_scan.as_float(row.get("realized_pl_dollars"), 0.0) or 0.0 for row in members]
        wins = sum(str(row.get("outcome") or "").upper() == "WIN" for row in members)
        summaries.append({
            "feature": feature,
            "value": value,
            "samples": len(members),
            "wins": wins,
            "win_rate_pct": round(wins / len(members) * 100, 1),
            "total_pl_dollars": round(sum(pnl), 2),
            "average_pl_dollars": round(statistics.mean(pnl), 2),
            "median_pl_dollars": round(statistics.median(pnl), 2),
            "evidence_ready": len(members) >= MIN_SAMPLE,
        })
    evidence = [item for item in summaries if item["evidence_ready"]]
    evidence.sort(key=lambda item: (item["feature"], -item["average_pl_dollars"]))
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "minimum_sample": MIN_SAMPLE,
        "closed_trades": len(rows),
        "groups": summaries,
        "evidence_ready_groups": evidence,
        "guardrails": [
            "No scanner filters are changed automatically.",
            "No brokerage orders are placed.",
            "Groups below the minimum sample are descriptive only.",
            "Results are historical observations, not profit guarantees.",
            "Any strategy change requires owner review, testing, and approval.",
        ],
    }


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Tradysquid Outcome Learning Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Closed tracked trades: {summary['closed_trades']}",
        f"Minimum evidence sample: {summary['minimum_sample']}",
        "",
        "This is offline historical analysis, not professional financial advice.",
        "The learning system does not modify scanner rules or place trades.",
        "",
        "## Evidence-ready groups",
        "",
    ]
    evidence = summary["evidence_ready_groups"]
    if not evidence:
        lines.append("No group has enough completed trades yet. Data collection continues.")
    else:
        lines.extend([
            "| Feature | Value | Samples | Win rate | Average P/L | Total P/L |",
            "|---|---:|---:|---:|---:|---:|",
        ])
        for item in evidence:
            lines.append(
                f"| {item['feature']} | {item['value']} | {item['samples']} | "
                f"{item['win_rate_pct']:.1f}% | ${item['average_pl_dollars']:.2f} | "
                f"${item['total_pl_dollars']:.2f} |"
            )
    lines.extend(["", "## Guardrails", ""])
    lines.extend(f"- {guardrail}" for guardrail in summary["guardrails"])
    return "\n".join(lines) + "\n"


def export_learning_archive() -> dict[str, Any]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    rows = sanitized_rows()
    summary = summarize(rows)
    csv_path = ARCHIVE_DIR / "trade_outcomes.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = EXPORT_FIELDS + ["dte_at_entry"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (ARCHIVE_DIR / "learning_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    (ARCHIVE_DIR / "learning_report.md").write_text(
        render_report(summary), encoding="utf-8"
    )
    (ARCHIVE_DIR / "README.txt").write_text(
        "Tradysquid offline learning archive.\n"
        "No API keys, Discord tokens, account numbers, or private messages are exported.\n"
        "Files are regenerated locally and synchronized by OneDrive.\n",
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    result = export_learning_archive()
    print(
        f"Exported {result['closed_trades']} completed trades to {ARCHIVE_DIR}"
    )
