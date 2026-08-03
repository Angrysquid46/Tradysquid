from __future__ import annotations

from collections import defaultdict

from .metrics import calculate


class LearningAnalysisService:
    def __init__(self, database):
        self.db = database

    def strategy_metrics(self) -> dict[str, dict]:
        rows = self.db.query(
            "SELECT o.*,p.strategy_id,p.strategy_version,p.config_json "
            "FROM closed_outcomes o JOIN paper_positions p ON p.id=o.position_id "
            "ORDER BY o.closed_at"
        )
        grouped = defaultdict(list)
        for row in rows:
            grouped[(row["strategy_id"], row["strategy_version"])].append(row)
        return {
            f"{strategy}@{version}": calculate(values)
            for (strategy, version), values in grouped.items()
        }

    def rejection_tradeoffs(self) -> list[dict]:
        """Summarize why candidates were rejected without simulating trades."""

        return self.db.query(
            "SELECT r.reason,COUNT(*) AS rejected "
            "FROM candidate_rejections r "
            "GROUP BY r.reason ORDER BY rejected DESC,r.reason"
        )

    def recommendation_inputs(self, strategy_id: str) -> dict:
        rows = self.db.query(
            "SELECT o.*,p.strategy_version,p.config_json "
            "FROM closed_outcomes o JOIN paper_positions p ON p.id=o.position_id "
            "WHERE p.strategy_id=? ORDER BY o.closed_at",
            (strategy_id,),
        )
        metrics = calculate(rows)
        return {
            "strategy_id": strategy_id,
            "metrics": metrics,
            "review_allowed": metrics["sample_size"] >= 30,
            "warning": (
                None
                if metrics["sample_size"] >= 30
                else "More closed paper trades are required before a setting review."
            ),
        }
