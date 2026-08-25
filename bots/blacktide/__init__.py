"""BLACKTIDE_SPY private trader (Codex-owned)."""

from .engine import BLACKTIDE, Decision
from .runtime import BlacktideRuntime

__all__ = ["BLACKTIDE", "BlacktideRuntime", "Decision"]
