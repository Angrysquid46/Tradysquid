"""validate_reconciliation() (in both performance_reconciliation.py, the
base, and performance_scorecards.py, the installed override) is a
self-test meant to catch reconciliation bugs before they reach production.
It used to only exercise 2 of the system's 14 live play_types
(SPY_0DTE_1M/5M) - or, in performance_reconciliation.py's own base
version, the fully retired REGULAR/SWING/SPREAD play types and ticker "F"
(Ford), left over from before the SPY-only pivot. Either way, a real
reconciliation bug in any of the other 12 strategies (Key-Levels,
completely undetected. These tests lock in that every currently-live
play_type actually gets exercised.
"""

from __future__ import annotations

import ast
import inspect

import performance_reconciliation
import performance_scorecards
import spy_scanner


def _defined_source(module, function_name: str) -> str:
    """The function's source as actually written in the module's file, via
    ast rather than the live attribute - performance_scorecards.install()
    reassigns performance_reconciliation.validate_reconciliation outright
    (no __wrapped__ chain), and some other test file in the full suite
    installs it eagerly enough that even a module-level capture of the
    live callable, taken at this file's own import time, can already be
    pointing at the override. Reading the file's own AST is unaffected by
    whatever any other test wired the live attribute to."""
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return ast.get_source_segment(inspect.getsource(module), node)
    raise AssertionError(f"{function_name} not found in {module.__name__}")


def test_installed_validate_reconciliation_exercises_every_live_play_type():
    performance_scorecards.install()
    result = performance_scorecards.validate_reconciliation()
    assert result["strategy_scorecards"] == len(performance_reconciliation.STRATEGY_VARIANTS)
    assert result["strategy_scorecards"] == 14


def test_no_validate_reconciliation_variant_references_retired_play_types_or_ford():
    base_source = _defined_source(performance_reconciliation, "validate_reconciliation")
    override_source = _defined_source(performance_scorecards, "validate_reconciliation")
    for source in (base_source, override_source):
        assert '"REGULAR"' not in source
        assert '"SWING"' not in source
        assert '"ticker": "F"' not in source
        # Data-driven off the full live variant table, not a hardcoded
        # subset - the exact gap that let 12 of 14 strategies go untested.
        assert "STRATEGY_VARIANTS" in source
