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

import inspect
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import spy_scanner  # noqa: E402 - path must be set up first
import performance_reconciliation  # noqa: E402

# Anything that looks like a credential, so a failure receipt is safe to print.
_SECRET = re.compile(
    r"(?i)(token|secret|api[_-]?key|password|authorization)\s*[=:]\s*\S+"
)

EXPECTED_STRATEGY_COUNT = 15


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
        scanner_path = Path(spy_scanner.__file__ or "").resolve()
        _require(
            checks,
            "scanner-import",
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

        risk_cap = float(spy_scanner.configured("max_risk_per_trade", 500.0))
        _require(
            checks,
            "risk-cap",
            0 < risk_cap <= 500.0,
            {"max_risk_per_trade": risk_cap},
        )

        live = sorted(performance_reconciliation.live_play_types())
        _require(
            checks,
            "strategy-roster",
            len(live) == EXPECTED_STRATEGY_COUNT,
            {"strategy_count": len(live), "strategies": live},
        )

        # Every live strategy must resolve a held-position channel, or its
        # card silently goes nowhere.
        unrouted = [p for p in live if not spy_scanner.held_channel_key(p)]
        _require(
            checks,
            "strategy-channel-routing",
            not unrouted,
            {"unrouted": unrouted},
        )

        log_path = Path(spy_scanner.LOG_PATH).resolve()
        _require(
            checks,
            "trade-log-path",
            log_path.parent.is_dir(),
            {"trade_log": str(log_path), "exists": log_path.is_file()},
        )

        # Paper trading only: the scanner must expose no order-placing surface.
        forbidden_terms = ("place_order", "submit_order", "cancel_order",
                           "preview_order", "replace_order", "modify_order")
        forbidden = sorted(
            name
            for name, _ in inspect.getmembers(spy_scanner, callable)
            if not name.startswith("_")
            and any(term in name.lower() for term in forbidden_terms)
        )
        _require(
            checks,
            "read-only-scanner",
            not forbidden,
            {"forbidden_methods": forbidden},
        )

        result.update(
            {
                "status": "PASS",
                "python_executable": str(running_python),
                "virtual_environment": str(running_prefix),
                "scanner_path": str(scanner_path),
                "trade_log": str(log_path),
                "strategy_count": len(live),
            }
        )
        state_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
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

    state_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
