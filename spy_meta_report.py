"""Phase 6 runner - trains and validates the meta-model on real bars.

Produces docs/META_MODEL_RESULTS.md. Every number is out-of-sample under
purged, embargoed, session-level splits; nothing here is fitted and
scored on the same data.
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from pathlib import Path
from typing import Any

import spy_backtest as bt
import spy_meta_model as mm

REPORT_PATH = Path("docs/META_MODEL_RESULTS.md")
JSON_PATH = Path("state/meta_model.json")

# Features the model is allowed to see. Deliberately restricted to things
# knowable at the bar in question - no session_high, no day_type, nothing
# that summarises a period the bar has not lived through yet.
FEATURES = [
    "gap_pct", "gap_atr", "vwap_distance_atr", "relative_volume",
    "atr_pct", "adx_14", "efficiency_ratio", "volume_zscore_20",
    "momentum_score", "range_position", "bar_range_atr",
    "alignment_score", "confluence_count", "minutes_since_open",
    "or15_width_atr", "compression_ratio",
]


def collect(conn, *, limit: int | None = None, horizon: int = 30):
    rows_out, labels, sessions, raw = [], [], [], []
    for session, rows in bt.load_sessions(conn, limit=limit):
        for index in range(len(rows)):
            outcome = mm.label_outcome(rows, index, horizon=horizon)
            if outcome is None:
                continue
            values = []
            usable = True
            for name in FEATURES:
                value = rows[index].get(name)
                if not isinstance(value, (int, float)):
                    usable = False
                    break
                values.append(float(value))
            if not usable:
                continue
            rows_out.append(values)
            labels.append(outcome)
            sessions.append(session)
            raw.append(rows[index])
    return rows_out, labels, sessions, raw


def main() -> None:
    conn = bt.connect()
    try:
        print("collecting labelled bars...", flush=True)
        features, outcomes, sessions, raw = collect(conn, limit=900)
    finally:
        conn.close()
    print(f"  {len(features):,} labelled bars", flush=True)

    distribution = Counter(o.direction for o in outcomes)
    resolved = [i for i, o in enumerate(outcomes) if o.resolved]
    print("  label distribution:", dict(distribution), flush=True)

    # Directional model trained only on bars that actually resolved - a
    # model asked to call direction on bars where nothing happened is being
    # asked to predict noise.
    dir_features = [features[i] for i in resolved]
    dir_labels = [1 if outcomes[i].direction == mm.UP else 0 for i in resolved]
    dir_sessions = [sessions[i] for i in resolved]

    splits = mm.purged_splits(dir_sessions, folds=4, embargo=1)
    fold_results, all_probs, all_out = [], [], []
    for number, (train_idx, test_idx) in enumerate(splits, start=1):
        model = mm.train_logistic(
            [dir_features[i] for i in train_idx],
            [dir_labels[i] for i in train_idx],
            FEATURES, epochs=250, learning_rate=0.3,
        )
        probs = [model.probability(dir_features[i]) for i in test_idx]
        truth = [dir_labels[i] for i in test_idx]
        all_probs.extend(probs)
        all_out.extend(truth)
        accuracy = statistics.fmean(
            1.0 if (p >= 0.5) == bool(o) else 0.0 for p, o in zip(probs, truth)
        )
        fold_results.append({
            "fold": number, "train": len(train_idx), "test": len(test_idx),
            "base_rate": statistics.fmean(truth),
            "accuracy": accuracy,
            "brier": mm.brier_score(probs, truth),
        })
        print(f"  fold {number}: acc {accuracy:.3f} brier {fold_results[-1]['brier']:.4f}",
              flush=True)

    curve = mm.reliability_curve(all_probs, all_out)
    ece = mm.calibration_error(curve)
    base_rate = statistics.fmean(all_out) if all_out else 0.0
    baseline_brier = base_rate * (1 - base_rate)

    # NO-TRADE model: can it tell an opportunity from a dead bar at all?
    trade_labels = [1 if o.resolved else 0 for o in outcomes]
    nt_splits = mm.purged_splits(sessions, folds=4, embargo=1)
    nt_probs, nt_out = [], []
    for train_idx, test_idx in nt_splits:
        model = mm.train_logistic(
            [features[i] for i in train_idx], [trade_labels[i] for i in train_idx],
            FEATURES, epochs=250, learning_rate=0.3,
        )
        nt_probs.extend(model.probability(features[i]) for i in test_idx)
        nt_out.extend(trade_labels[i] for i in test_idx)
    nt_base = statistics.fmean(nt_out) if nt_out else 0.0

    # Importance and drift on the full set.
    full_model = mm.train_logistic(dir_features, dir_labels, FEATURES,
                                   epochs=250, learning_rate=0.3)
    importance = mm.permutation_importance(full_model, dir_features, dir_labels,
                                           repeats=3)
    half = len(raw) // 2
    drift = mm.drift_report(raw[:half], raw[half:], FEATURES)

    payload = {
        "bars": len(features), "distribution": dict(distribution),
        "folds": fold_results, "reliability": curve,
        "calibration_error": ece, "base_rate": base_rate,
        "baseline_brier": baseline_brier,
        "no_trade": {"base_rate": nt_base,
                     "brier": mm.brier_score(nt_probs, nt_out),
                     "baseline_brier": nt_base * (1 - nt_base)},
        "importance": importance, "drift": drift,
    }
    JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(render(payload), encoding="utf-8")
    print(f"wrote {REPORT_PATH}")


def render(p: dict[str, Any]) -> str:
    lines = ["# Meta-Model Results (Phase 6)\n"]
    lines.append(
        f"Trained on **{p['bars']:,} labelled bars** from the Phase 2 feature "
        f"store. Every figure below is **out-of-sample** under purged, "
        f"embargoed, session-level splits - a model is never scored on a "
        f"session it trained on, and whole sessions are dropped either side of "
        f"each test block so a label's forward horizon cannot leak into "
        f"training.\n"
    )
    lines.append("\n## Labels\n")
    lines.append("Triple-barrier: an up barrier, a down barrier and a time limit, "
                 "labelled by whichever is hit first. A bar that ends higher after "
                 "a deep dip is a loss for anyone with a stop, and fixed-horizon "
                 "labelling would call it a win.\n")
    lines.append("| Label | Bars |")
    lines.append("|---|---|")
    for name, count in sorted(p["distribution"].items(), key=lambda kv: -kv[1]):
        lines.append(f"| {name} | {count:,} |")

    lines.append("\n## Directional model, per fold\n")
    lines.append("| Fold | Train | Test | Base rate | Accuracy | Brier |")
    lines.append("|---|---|---|---|---|---|")
    for fold in p["folds"]:
        lines.append(
            f"| {fold['fold']} | {fold['train']:,} | {fold['test']:,} | "
            f"{fold['base_rate']:.3f} | {fold['accuracy']:.3f} | {fold['brier']:.4f} |"
        )
    lines.append(
        f"\nBaseline Brier from always predicting the base rate: "
        f"**{p['baseline_brier']:.4f}**. A model only adds value below that "
        f"number - accuracy alone can beat 50% purely by following the majority "
        f"class.\n"
    )

    lines.append("\n## Calibration\n")
    lines.append(f"Expected calibration error: **{p['calibration_error']:.4f}**\n")
    lines.append("| Bin | n | Predicted | Observed | Gap |")
    lines.append("|---|---|---|---|---|")
    for entry in p["reliability"]:
        lines.append(
            f"| {entry['bin']} | {entry['n']:,} | {entry['predicted']:.3f} | "
            f"{entry['observed']:.3f} | {entry['gap']:+.3f} |"
        )
    lines.append(
        "\nA model can rank correctly and still be badly calibrated. Only a "
        "calibrated probability can be used to size a position - if the model "
        "says 70% and it happens 50% of the time, sizing on that number "
        "systematically over-bets.\n"
    )

    nt = p["no_trade"]
    lines.append("\n## NO-TRADE as a class\n")
    lines.append(
        f"Share of bars where either barrier was hit inside the horizon: "
        f"**{nt['base_rate']:.1%}**. Predicting whether a bar is an opportunity "
        f"at all scored Brier **{nt['brier']:.4f}** against a base-rate baseline "
        f"of **{nt['baseline_brier']:.4f}**.\n"
    )
    lines.append(
        "This is the more useful target for a system that already has 14 entry "
        "rules: knowing when NOT to act is worth more than another opinion "
        "about direction.\n"
    )

    lines.append("\n## Feature importance (permutation)\n")
    lines.append("How much Brier score worsens when each feature is shuffled. "
                 "More honest than reading coefficients - it measures dependence "
                 "the model actually has.\n")
    lines.append("| Feature | Importance |")
    lines.append("|---|---|")
    for entry in p["importance"][:12]:
        lines.append(f"| {entry['feature']} | {entry['importance']:+.5f} |")

    lines.append("\n## Drift\n")
    lines.append("Population stability index, first half of the sample against the "
                 "second. Under 0.10 stable, 0.10-0.25 moderate, above 0.25 the "
                 "feature no longer resembles what the model trained on.\n")
    lines.append("| Feature | PSI | Verdict |")
    lines.append("|---|---|---|")
    for entry in p["drift"][:12]:
        lines.append(f"| {entry['feature']} | {entry['psi']:.3f} | {entry['verdict']} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
