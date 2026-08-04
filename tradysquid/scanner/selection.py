from __future__ import annotations

from ..core.enums import CandidateStatus


MANUAL_SELECTION_MODES = {
    "record-only",
    "owner-confirmed paper entry",
}
AUTOMATIC_SELECTION_MODES = {
    "automatically open qualified paper trades",
    "ranked top-N paper entries",
}


class CandidateSelector:
    """Apply configured paper-entry selection after every evaluation is recorded."""

    def select(self, decisions):
        by_strategy = {}
        for decision in decisions:
            by_strategy.setdefault(decision.strategy_id, []).append(decision)

        selected = []
        for group in by_strategy.values():
            eligible = [
                decision
                for decision in group
                if decision.status == CandidateStatus.ELIGIBLE
            ]
            if not eligible:
                continue

            eligible.sort(
                key=lambda decision: (
                    -decision.ranking_score,
                    decision.maximum_risk,
                    decision.candidate_id,
                )
            )
            mode = str(
                eligible[0].configuration_snapshot["entry"]["selection_mode"]
            )
            maximum = int(
                eligible[0].configuration_snapshot["entry"]
                ["maximum_selections_per_scan"]
            )
            if mode in MANUAL_SELECTION_MODES:
                continue
            if mode not in AUTOMATIC_SELECTION_MODES:
                raise ValueError(f"Unsupported selection mode: {mode}")

            for decision in eligible[:maximum]:
                decision.status = CandidateStatus.SELECTED
                selected.append(decision)
        return selected
