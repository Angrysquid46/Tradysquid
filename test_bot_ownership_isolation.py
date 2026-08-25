"""Phase 11 (Master Spec Section 11): bots/blacktide and bots/claude are
write-guarded by governance/OWNERSHIP.json (see
tests/unit/test_governance_phase4.py for that enforcement), but the
write-guard only checks what an actor *declares* it changed at finish()
time - it can't catch a stray import written inside the other bot's own
directory. This is the same static-source-scan pattern already used for
rivalry.py (Phase 9) and learning_center_index.py (Phase 10): a real,
automated regression guard, not just a policy statement.

Trivially passes today - neither directory has any .py file yet (Phase 12/
13's job). Its value is catching an accidental cross-import the moment one
is ever added.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BLACKTIDE_DIR = ROOT / "bots" / "blacktide"
CLAUDE_DIR = ROOT / "bots" / "claude"

_CROSS_REFERENCE_RE = re.compile(r"bots[./\\]blacktide|bots[./\\]claude")


def _python_files(directory: Path) -> list[Path]:
    if not directory.is_dir():
        return []
    return sorted(directory.rglob("*.py"))


def test_bot_directories_exist():
    assert BLACKTIDE_DIR.is_dir()
    assert CLAUDE_DIR.is_dir()


def test_claude_directory_never_references_blacktide():
    for path in _python_files(CLAUDE_DIR):
        text = path.read_text(encoding="utf-8")
        assert "blacktide" not in text.casefold(), (
            f"{path.relative_to(ROOT)} must never reference bots/blacktide"
        )


def test_blacktide_directory_never_references_claude():
    for path in _python_files(BLACKTIDE_DIR):
        text = path.read_text(encoding="utf-8")
        assert "claude" not in text.casefold(), (
            f"{path.relative_to(ROOT)} must never reference bots/claude"
        )


def test_no_trading_relevant_module_imports_either_private_bot_package():
    """Same isolation statement Phase 9/10 already enforce for
    rivalry.py/learning_center_index.py, extended to the two bot
    packages: shared infrastructure must never import a competitor's
    private code."""
    import backtest_lab
    import market_data_collector
    import rivalry
    import scoreboard

    for module in (backtest_lab, market_data_collector, rivalry, scoreboard):
        import inspect

        source = inspect.getsource(module)
        assert not _CROSS_REFERENCE_RE.search(source), (
            f"{module.__name__} must never reference bots/blacktide or bots/claude"
        )
