from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any

import tradysquid

from tradysquid.core.config import AppConfig, redact
from tradysquid.data.database import Database
from tradysquid.providers.tradier import TradierClient
from tradysquid.strategies.registry import StrategyRegistry


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
    root = Path(__file__).resolve().parents[1]
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
        package_path = Path(tradysquid.__file__ or "").resolve()
        _require(
            checks,
            "package-import",
            package_path.is_file() and package_path.is_relative_to(root.resolve()),
            {"package_path": str(package_path)},
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

        config = AppConfig.load(root)
        _require(checks, "configuration-load", True)
        _require(
            checks,
            "universe-limit",
            int(config.defaults["universe"]["maximum_active"]) == 25,
            {"maximum_active": int(config.defaults["universe"]["maximum_active"])},
        )
        _require(
            checks,
            "global-risk-limit",
            float(config.defaults["risk"]["maximum_position_risk_dollars"]) == 100.0,
            {
                "maximum_position_risk_dollars": float(
                    config.defaults["risk"]["maximum_position_risk_dollars"]
                )
            },
        )

        registry = StrategyRegistry(config.strategies)
        strategies = registry.all()
        strategy_versions = {
            strategy.id: {
                "version": strategy.config.get("version"),
                "configuration_hash": strategy.config.get("configuration_hash"),
            }
            for strategy in strategies
        }
        _require(
            checks,
            "strategy-registry",
            len(strategies) == 6
            and all(
                value["version"] and len(str(value["configuration_hash"])) == 64
                for value in strategy_versions.values()
            ),
            {"strategy_count": len(strategies), "strategies": strategy_versions},
        )

        database_path = (root / config.defaults["database"]["path"]).resolve()
        expected_database_path = (root / "data" / "tradysquid.db").resolve()
        _require(
            checks,
            "database-path",
            database_path == expected_database_path,
            {"database_path": str(database_path)},
        )
        database = Database(database_path)
        database.initialize()
        database.register_strategies(config.strategies)
        _require(
            checks,
            "database-integrity",
            database.integrity_check() == "ok",
            {"integrity": database.integrity_check()},
        )
        _require(
            checks,
            "database-wal",
            database.journal_mode() == "wal",
            {"journal_mode": database.journal_mode()},
        )
        with database.connect() as connection:
            foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
        _require(
            checks,
            "database-foreign-keys",
            foreign_keys == 1,
            {"foreign_keys": foreign_keys},
        )

        forbidden_terms = ("order", "cancel", "replace", "preview", "submit")
        public_provider_methods = [
            name
            for name, member in inspect.getmembers(TradierClient, callable)
            if not name.startswith("_")
        ]
        forbidden_provider_methods = sorted(
            name
            for name in public_provider_methods
            if any(term in name.lower() for term in forbidden_terms)
        )
        _require(
            checks,
            "read-only-provider",
            not forbidden_provider_methods,
            {
                "public_methods": public_provider_methods,
                "forbidden_methods": forbidden_provider_methods,
            },
        )

        result.update(
            {
                "status": "PASS",
                "python_executable": str(running_python),
                "virtual_environment": str(running_prefix),
                "tradysquid_package_path": str(package_path),
                "database_path": str(database_path),
                "strategy_count": len(strategies),
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
    except Exception as exc:  # production boundary: record a sanitized failure receipt
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
