from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from ..learning.metrics import calculate


def _parsed(value: str) -> datetime:
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def group_period(rows: list[dict], period: str) -> dict[str, dict]:
    grouped = defaultdict(list)
    for row in rows:
        observed = _parsed(row['closed_at'])
        if period == 'daily':
            key = observed.date().isoformat()
        elif period == 'weekly':
            year, week, _ = observed.isocalendar()
            key = f'{year}-W{week:02d}'
        elif period == 'monthly':
            key = observed.strftime('%Y-%m')
        else:
            raise ValueError('period must be daily, weekly, or monthly')
        grouped[key].append(row)
    return {key: calculate(values) for key, values in sorted(grouped.items())}
