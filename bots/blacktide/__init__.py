"""BLACKTIDE_SPY private trader (Codex-owned)."""

from .env_bootstrap import bootstrap

# Package __init__ runs before any `bots.blacktide.*` submodule.  Bootstrap
# here so shared modules imported by runtime bind the real environment.
bootstrap()

from .engine import BLACKTIDE, Decision
from .runtime import BlacktideRuntime
from .scheduler import build_scheduler

__all__ = ["BLACKTIDE", "BlacktideRuntime", "Decision", "build_scheduler"]
