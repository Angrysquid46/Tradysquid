"""Phase 13 v2: AXIOM's public entry-decision entry point. Thin wrapper
delegating to evolution.select_hypothesis - the actual entry logic lives
in hypotheses.py (the three competing theses) and evolution.py (fitness-
based selection and deterministic tightening/retirement). Kept as its
own module so callers (backtest_runner.py, runtime.py) have one stable
name to call regardless of how the pool of hypotheses evolves.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from bots.claude import evolution
from bots.claude.decision import EntryDecision
from bots.claude.evolution import SelectedHypothesis

__all__ = ["EntryDecision", "SelectedHypothesis", "entry_decision"]


def entry_decision(
    connection: sqlite3.Connection, current_price: float, features: dict[str, Any]
) -> SelectedHypothesis | None:
    return evolution.select_hypothesis(connection, current_price, features)
