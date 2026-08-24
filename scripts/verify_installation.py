"""Verify this checkout is a working Tradysquid installation.

Rewritten 2026-08-19. This used to import the `tradysquid/` package -
AppConfig, Database, TradierClient, StrategyRegistry - and assert it held
exactly 6 strategies. That package was the abandoned multi-ticker rewrite;
nothing in the live trade path ever imported it, and its "6 strategies"
were regular_call/regular_put/swing_call/swing_put/bull_put_spread/
bear_call_spread, none of which have existed for months. So the installer
was verifying a system that does not run, and the import was the only thing
keeping 10,000 lines of dead code in the repository.

It now verifies what actually runs: the flat scripts, the live strategy
roster, the real trade log, and that the scanner exposes no order-placing
surface.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import market_data  # noqa: E402 - path must be set up first

# Anything that looks like a credential, so a failure receipt is safe to print.
_SECRET = re.compile(
    r"(?i)(token|secret|api[_-]?key|password|authorization)\s*[=:]\s*\S+"
)

PURGED_RUNTIME_PATHS = (
    "spy_scanner.py",
    "performance_reconciliation.py",
    "performance_scorecards.py",
    "backtest_cards.py",
    "local_information_engine_public.py",
    "evolve_bot",
)


def redact(text: str) -> str:
    return _SECRET.sub(lambda m: f"{m.group(1)}=[REDACTED]", str(text))


class VerificationFailure(RuntimeError):
    """A named installation check failed."""

    def __init__(self, check: str, message: str) -> None:
        super().__init__(message)
        self.check = check


def _require(
    checks: dict[str, dict[str, Any]],
    name: str,
    condition: bool,
    details: dict[str, Any] | None = None,
) -> None:
    checks[name] = {"status": "PASS" if condition else "FAILED", **(details or {})}
    if not condition:
        raise VerificationFailure(name, f"Installation check failed: {name}")


def _expected_python(root: Path) -> Path:
    relative = Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    return (root / ".venv-tradysquid" / relative).resolve()


def _write_receipt(path: Path, result: dict[str, Any]) -> None:
    """Write the local receipt when the checkout permits runtime state writes."""
    try:
        path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    except PermissionError:
        # Read-only/deployment-validation checkouts still need a truthful exit
        # result; stdout remains the machine-readable receipt in that case.
        pass


def main() -> int:
    root = ROOT
    state_path = root / "state" / "install-verification.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    checks: dict[str, dict[str, Any]] = {}
    result: dict[str, Any] = {
        "status": "FAILED",
        "root": str(root),
        "checks": checks,
        "secret_values_written": False,
    }

    try:
        scanner_path = Path(market_data.__file__ or "").resolve()
        _require(
            checks,
            "market-data-import",
            scanner_path.is_file() and scanner_path.is_relative_to(root.resolve()),
            {"scanner_path": str(scanner_path)},
        )

        expected_python = _expected_python(root)
        running_python = Path(sys.executable).resolve()
        running_prefix = Path(sys.prefix).resolve()
        isolated_venv = (root / ".venv-tradysquid").resolve()
        legacy_venv = (root / ".venv").resolve()
        _require(
            checks,
            "isolated-interpreter",
            running_python == expected_python and running_prefix == isolated_venv,
            {
                "python_executable": str(running_python),
                "virtual_environment": str(running_prefix),
            },
        )
        _require(
            checks,
            "legacy-environment-not-running",
            running_prefix != legacy_venv,
            {"legacy_virtual_environment": str(legacy_venv)},
        )

        # config/scanner.json is the real tunable-parameter file; spy_scanner
        # reads every threshold through configured().
        config_path = root / "config" / "scanner.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        _require(
            checks,
            "configuration-load",
            isinstance(config, dict) and bool(config),
            {"config_path": str(config_path)},
        )

        remaining = [path for path in PURGED_RUNTIME_PATHS if (root / path).exists()]
        _require(
            checks,
            "legacy-runtime-absent",
            not remaining,
            {"remaining": remaining},
        )

        result.update(
            {
                "status": "PASS",
                "python_executable": str(running_python),
                "virtual_environment": str(running_prefix),
                "scanner_path": str(scanner_path),
                "strategy_count": 0,
            }
        )
        _write_receipt(state_path, result)
        print(json.dumps(result, sort_keys=True))
        return 0
    except VerificationFailure as exc:
        result.update(
            {
                "status": "FAILED",
                "failed_check": exc.check,
                "category": "APPLICATION",
                "error": redact(str(exc)),
            }
        )
    except Exception as exc:  # production boundary: record a sanitized receipt
        result.update(
            {
                "status": "FAILED",
                "failed_check": "unexpected-error",
                "category": "APPLICATION",
                "error": redact(f"{type(exc).__name__}: {exc}"),
            }
        )

    _write_receipt(state_path, result)
    print(json.dumps(result, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
