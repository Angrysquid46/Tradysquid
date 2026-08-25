"""Phase 13 v2: the shared EntryDecision shape, split into its own module
with zero dependencies so hypotheses.py/evolution.py/signal.py can each
import it without a circular import (signal.py delegates to evolution.py,
which selects among hypotheses.py's evaluators, which return this type)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class EntryDecision:
    should_enter: bool
    side: str | None
    rationale: str
    contributing_signals: dict[str, Any] = field(default_factory=dict)
