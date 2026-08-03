from __future__ import annotations
from ..core.enums import CandidateStatus

class CandidateSelector:
    """Applies selection modes after every evaluation is durably recorded."""
    def select(self, decisions):
        by_strategy = {}
        for decision in decisions:
            by_strategy.setdefault(decision.strategy_id, []).append(decision)
        selected = []
        for group in by_strategy.values():
            eligible = [d for d in group if d.status == CandidateStatus.ELIGIBLE]
            if not eligible:
                continue
            eligible.sort(key=lambda d: (-d.ranking_score, d.maximum_risk, d.candidate_id))
            mode = eligible[0].configuration_snapshot['entry']['selection_mode']
            maximum = int(eligible[0].configuration_snapshot['entry']['maximum_selections_per_scan'])
            if mode in {'record-only', 'owner-confirmed paper entry', 'shadow-only'}:
                continue
            if mode in {'automatically open qualified paper trades', 'ranked top-N paper entries'}:
                for decision in eligible[:maximum]:
                    decision.status = CandidateStatus.SELECTED
                    selected.append(decision)
        return selected
