"""CLOSING_SIGNALS is the single source of truth every close-triggering
call site checks against - and it has already drifted from what the exit-
signal functions actually return twice: once for FLOOR STOP/RATCHET EOD
CLOSE (fixed, see test_spy_ratchet.py), and again for spy_0dte_exit_signal's
own bare "EOD CLOSE" (confirmed live: not in the set, meaning any SPY_0DTE_
1M/5M position that reaches the 15-minutes-to-close window without hitting
a real stop/target/floor would show "EOD CLOSE" on its live card but never
actually get closed by any of the three call sites).

Rather than add another hand-maintained assertion per string (the pattern
that already produced two gaps), this generates the expected set directly
from source - every literal "return "<STRING>", ...` inside a function
whose name ends in _exit_signal - and diffs it against CLOSING_SIGNALS, so
a future new exit signal string gets caught automatically instead of
depending on someone remembering to add a matching assertion.
"""

from __future__ import annotations
import ast
import inspect

import spy_scanner


def _signal_strings_returned_by_exit_functions() -> set[str]:
    source = inspect.getsource(spy_scanner)
    tree = ast.parse(source)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.FunctionDef) and node.name.endswith("_exit_signal")):
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Return):
                continue
            value = inner.value
            # Every exit_signal function returns a (signal, note) tuple -
            # only the first element is a closing-signal candidate.
            target = value.elts[0] if isinstance(value, ast.Tuple) and value.elts else value
            if isinstance(target, ast.Constant) and isinstance(target.value, str):
                found.add(target.value)
    return found


def test_every_non_hold_string_an_exit_signal_function_can_return_is_in_closing_signals():
    returned = _signal_strings_returned_by_exit_functions()
    non_hold = {signal for signal in returned if signal != "HOLD"}
    missing = non_hold - spy_scanner.CLOSING_SIGNALS
    assert not missing, (
        f"{missing} can be returned by a *_exit_signal function but "
        "is not in CLOSING_SIGNALS - a real close signal would show on "
        "the live card but never actually close the position"
    )


def test_eod_close_is_in_closing_signals():
    assert "EOD CLOSE" in spy_scanner.CLOSING_SIGNALS
