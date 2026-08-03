from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

@dataclass(frozen=True)
class ManagementDecision:
    action: str
    reason: str
    next_state: str
    active_stop_pct: float
    active_target_pct: float


def evaluate_management(position: dict[str, Any], config: dict[str, Any], *, now: datetime | None = None) -> ManagementDecision:
    """Evaluate configured paper-only management rules without changing state."""
    now = now or datetime.now(timezone.utc)
    management = config['management']
    pnl = float(position.get('pnl_pct', 0))
    mfe = float(position.get('mfe_pct', 0))
    stop = float(management['hard_stop_pct'])
    target = float(management['profit_target_pct'])
    break_even = management.get('break_even_activation_pct')
    trailing = management.get('trailing_activation_pct')
    giveback = management.get('maximum_mfe_giveback_pct')

    if pnl <= -stop:
        return ManagementDecision('EXIT', 'hard stop reached', 'EXIT_PENDING', stop, target)
    if pnl >= target:
        return ManagementDecision('EXIT', 'profit target reached', 'EXIT_PENDING', stop, target)
    if trailing is not None and giveback is not None and mfe >= float(trailing):
        floor = max(0.0, mfe - float(giveback))
        if pnl <= floor:
            return ManagementDecision('EXIT', f'MFE giveback floor reached at {floor:.4f}', 'EXIT_PENDING', -floor, target)
        return ManagementDecision('HOLD', 'trailing profit protection active', 'PROFIT_PROTECTED', -floor, target)
    if break_even is not None and mfe >= float(break_even):
        if pnl <= 0:
            return ManagementDecision('EXIT', 'break-even protection triggered', 'EXIT_PENDING', 0.0, target)
        return ManagementDecision('HOLD', 'break-even protection active', 'PROFIT_PROTECTED', 0.0, target)
    opened_at = position.get('opened_at')
    maximum_minutes = management.get('maximum_holding_minutes')
    if opened_at and maximum_minutes:
        opened = datetime.fromisoformat(str(opened_at).replace('Z', '+00:00'))
        if (now - opened).total_seconds() >= float(maximum_minutes) * 60:
            return ManagementDecision('EXIT', 'configured time stop reached', 'EXIT_PENDING', stop, target)
    return ManagementDecision('HOLD', 'no configured exit condition reached', 'HOLD', stop, target)
