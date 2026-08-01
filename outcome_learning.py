"""Offline, review-first learning from completed tracked trades.

This module never changes scanner rules or places trades. It exports sanitized
outcomes, evidence summaries, and trade-specific review cause tags to a
OneDrive-backed folder for human review.
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
import trade_intelligence

ROOT = Path(__file__).resolve().parent
DEFAULT_ARCHIVE = Path(os.environ.get("OneDrive", str(ROOT.parent))) / "Tradysquid-Learning"
ARCHIVE_DIR = Path(os.environ.get("LEARNING_ARCHIVE_DIR", str(DEFAULT_ARCHIVE)))
MIN_SAMPLE = int(os.environ.get("LEARNING_MIN_SAMPLE", "20"))
REVIEW_RECORD_PATH = ROOT / "state" / "trade-learning-records.json"

EXPORT_FIELDS = [
    "trade_id", "ticker", "play_type", "call_or_put", "timestamp", "closed_at",
    "expiration", "entry_price", "exit_price", "delta_at_entry", "theta_at_entry",
    "iv_at_entry", "pop_estimate", "max_profit", "max_risk", "breakeven",
    "open_interest_at_entry", "bid_ask_width_at_entry", "option_volume_at_entry",
    "setup_score", "market_regime", "outcome", "pct_gain_loss",
    "realized_pl_dollars", "max_favorable_pct", "max_adverse_pct", "last_signal",
    "thesis", "entry_confirmation", "invalidation", "risk_plan", "learning_plan",
    "evidence_limitations", "learning_version", "data_confidence",
    "review_primary_cause", "review_cause_tags", "review_alignment",
    "review_aligned_count", "review_opposing_count", "review_neutral_count",
    "review_missing_evidence_count", "review_version",
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


def review_records() -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(REVIEW_RECORD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    records = payload.get("records") if isinstance(payload, dict) else {}
    return records if isinstance(records, dict) else {}


def review_alignment(record: dict[str, Any]) -> str:
    aligned = len(record.get("aligned_evidence") or [])
    opposing = len(record.get("opposing_evidence") or [])
    neutral = len(record.get("neutral_evidence") or [])
    if opposing or neutral:
        return "MIXED"
    if aligned:
        return "ALIGNED"
    return "UNRECORDED"


def sanitized_rows() -> list[dict[str, Any]]:
    rows = ford_scan.closed_rows(ford_scan.read_log())
    reviews = review_records()
    exports: list[dict[str, Any]] = []
    for row in rows:
        item = {field: row.get(field, "") for field in EXPORT_FIELDS}
        item["dte_at_entry"] = days_to_expiration(row)
        review = reviews.get(str(row.get("trade_id") or ""), {})
        tags = [str(tag) for tag in review.get("cause_tags") or []]
        item.update({
            "review_primary_cause": tags[0] if tags else "UNREVIEWED",
            "review_cause_tags": ",".join(tags),
            "review_alignment": review_alignment(review),
            "review_aligned_count": len(review.get("aligned_evidence") or []),
            "review_opposing_count": len(review.get("opposing_evidence") or []),
            "review_neutral_count": len(review.get("neutral_evidence") or []),
            "review_missing_evidence_count": len(review.get("missing_evidence") or []),
            "review_version": review.get("review_version") or "",
        })
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
    play_type = str(row.get("play_type") or "UNKNOWN").upper()
    direction = str(row.get("call_or_put") or "UNKNOWN").upper()
    return {
        "ticker": str(row.get("ticker") or "F").upper(),
        "strategy": str(row.get("play_type") or "UNKNOWN").upper(),
        "direction": str(row.get("call_or_put") or "UNKNOWN").upper(),
        "play_style": f"{play_type}-{direction}",
        "regime": str(row.get("market_regime") or "UNKNOWN").upper(),
        "review_primary_cause": str(row.get("review_primary_cause") or "UNREVIEWED"),
        "review_alignment": str(row.get("review_alignment") or "UNRECORDED"),
        "delta_band": bucket(ford_scan.as_float(row.get("delta_at_entry")), (0.15, 0.25, 0.40, 0.60, 0.75)),
        "iv_band": bucket(ford_scan.as_float(row.get("iv_at_entry")), (0.25, 0.40, 0.60, 0.90)),
        "dte_band": bucket(ford_scan.as_float(row.get("dte_at_entry")), (7, 14, 21, 30, 45, 61)),
        "score_band": bucket(ford_scan.as_float(row.get("setup_score")), (40, 55, 70, 85)),
        "open_interest_band": bucket(ford_scan.as_float(row.get("open_interest_at_entry")), (100, 500, 1000, 2500, 5000)),
    }


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    cause_counts: dict[str, int] = defaultdict(int)
    for row in rows:
        for feature, value in feature_groups(row).items():
            groups[(feature, value)].append(row)
        for cause in str(row.get("review_cause_tags") or "").split(","):
            if cause:
                cause_counts[cause] += 1

    summaries = []
    for (feature, value), members in sorted(groups.items()):
        pnl = [ford_scan.as_float(row.get("realized_pl_dollars"), 0.0) or 0.0 for row in members]
        wins = sum(str(row.get("outcome") or "").upper() == "WIN" for row in members)
        gross_profit = sum(value for value in pnl if value > 0)
        gross_loss = abs(sum(value for value in pnl if value < 0))
        mfe = [ford_scan.as_float(row.get("max_favorable_pct")) for row in members]
        mae = [ford_scan.as_float(row.get("max_adverse_pct")) for row in members]
        mfe = [value for value in mfe if value is not None]
        mae = [value for value in mae if value is not None]
        summaries.append({
            "feature": feature,
            "value": value,
            "samples": len(members),
            "wins": wins,
            "win_rate_pct": round(wins / len(members) * 100, 1),
            "total_pl_dollars": round(sum(pnl), 2),
            "average_pl_dollars": round(statistics.mean(pnl), 2),
            "median_pl_dollars": round(statistics.median(pnl), 2),
            "expectancy_dollars": round(statistics.mean(pnl), 2),
            "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else None,
            "average_mfe_pct": round(statistics.mean(mfe), 1) if mfe else None,
            "average_mae_pct": round(statistics.mean(mae), 1) if mae else None,
            "evidence_ready": len(members) >= MIN_SAMPLE,
        })

    evidence = [item for item in summaries if item["evidence_ready"]]
    evidence.sort(key=lambda item: (item["feature"], -item["average_pl_dollars"]))
    reviewed = sum(str(row.get("review_primary_cause")) != "UNREVIEWED" for row in rows)
    return {
        "generated_at": datetime.now().astimezone().isoformat(),
        "learning_version": trade_intelligence.learning_version(),
        "minimum_sample": MIN_SAMPLE,
        "closed_trades": len(rows),
        "reviewed_trades": reviewed,
        "review_coverage_pct": round(reviewed / len(rows) * 100, 1) if rows else 0.0,
        "cause_counts": dict(sorted(cause_counts.items())),
        "groups": summaries,
        "evidence_ready_groups": evidence,
        "play_style_suggestions": build_suggestions(summaries),
        "guardrails": [
            "No scanner filters are changed automatically.",
            "No brokerage orders are placed.",
            "Root-cause tags remain hypotheses until supported by enough completed trades.",
            "Groups below the minimum sample are descriptive only.",
            "Any strategy change requires owner review, testing, and approval.",
        ],
    }


def build_suggestions(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    for item in groups:
        if item["feature"] != "play_style":
            continue
        samples = int(item["samples"])
        ready = bool(item["evidence_ready"])
        profitable = float(item["average_pl_dollars"]) > 0
        suggestions.append({
            "play_style": item["value"],
            "samples": samples,
            "confidence": "EVIDENCE-READY" if ready else "COLLECTING",
            "observation": (
                "Positive average P/L; preserve entry filters and compare exit timing against MFE."
                if profitable else
                "Negative average P/L; review confirmation quality, adverse excursion, and exit timing before proposing rule changes."
            ),
            "expected_tradeoff": "Tighter filters may improve quality while reducing trade frequency.",
            "automatic_change": False,
        })
    return suggestions


def render_report(summary: dict[str, Any]) -> str:
    lines = [
        "# Tradysquid Outcome Learning Report",
        "",
        f"Generated: {summary['generated_at']}",
        f"Closed tracked trades: {summary['closed_trades']}",
        f"Trade-specific reviews: {summary['reviewed_trades']} ({summary['review_coverage_pct']:.1f}%)",
        f"Minimum evidence sample: {summary['minimum_sample']}",
        f"Learning Center version: {summary['learning_version']}",
        "",
        "This is offline historical analysis, not professional financial advice.",
        "The learning system does not modify scanner rules or place trades.",
        "",
        "## Recorded review causes",
        "",
    ]
    if not summary["cause_counts"]:
        lines.append("No trade-specific cause tags have been recorded yet.")
    else:
        for cause, count in summary["cause_counts"].items():
            lines.append(f"- {cause}: {count}")

    lines.extend(["", "## Evidence-ready groups", ""])
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
    lines.extend(["", "## Play-style improvement queue", ""])
    for item in summary["play_style_suggestions"]:
        lines.append(
            f"- **{item['play_style']}** ({item['samples']} trades; {item['confidence']}): "
            f"{item['observation']} Tradeoff: {item['expected_tradeoff']}"
        )
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
        "Trade-specific cause tags are hypotheses for human-reviewed improvements.\n"
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
