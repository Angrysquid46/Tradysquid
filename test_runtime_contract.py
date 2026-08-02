from __future__ import annotations

import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import ford_scan
import runtime_contract


ROOT = Path(__file__).resolve().parent


class FakeJob:
    def __init__(self, name: str):
        self.name = name


class RuntimeContractTests(unittest.TestCase):
    def test_runtime_keeps_one_current_job_and_removes_completed_verifiers(self) -> None:
        engine = SimpleNamespace(
            JOBS=[
                FakeJob("self-diagnostics"),
                FakeJob("self-diagnostics"),
                FakeJob("intraday-chart-refresh"),
                FakeJob("upgrade-request-migration"),
                FakeJob("upgrade-batch-44-acceptance"),
                FakeJob("upgrade-lifecycle-dashboard"),
                FakeJob("applied-upgrades-dashboard"),
                FakeJob("market-hours-upgrade-review"),
            ]
        )
        runtime_contract.dedupe_and_retire_jobs(engine)
        self.assertEqual(
            [job.name for job in engine.JOBS],
            ["self-diagnostics", "intraday-chart-refresh"],
        )

    def test_weekend_intraday_window_uses_last_completed_weekday(self) -> None:
        runtime_contract.install_safe_intraday_history(ford_scan)
        moment = datetime(2026, 8, 2, 7, 25, tzinfo=ford_scan.MARKET_TZ)
        start, end = ford_scan.intraday_session_window(moment)
        self.assertEqual(start, "2026-07-31 08:30")
        self.assertEqual(end, "2026-07-31 15:00")

    def test_premarket_intraday_window_never_uses_future_open(self) -> None:
        runtime_contract.install_safe_intraday_history(ford_scan)
        moment = datetime(2026, 8, 3, 7, 0, tzinfo=ford_scan.MARKET_TZ)
        start, end = ford_scan.intraday_session_window(moment)
        self.assertEqual(start, "2026-07-31 08:30")
        self.assertEqual(end, "2026-07-31 15:00")

    def test_live_intraday_window_ends_one_minute_before_now(self) -> None:
        runtime_contract.install_safe_intraday_history(ford_scan)
        moment = datetime(2026, 8, 3, 10, 0, tzinfo=ford_scan.MARKET_TZ)
        start, end = ford_scan.intraday_session_window(moment)
        self.assertEqual(start, "2026-08-03 08:30")
        self.assertEqual(end, "2026-08-03 09:59")

    def test_network_and_log_symptoms_never_create_code_repairs(self) -> None:
        fake_diagnostics = SimpleNamespace(
            _github_report=lambda record: {"signature": record.get("signature", "x")}
        )
        fake_review = SimpleNamespace(_actionable=lambda record: True)
        runtime_contract.install_diagnostic_policy(fake_diagnostics, fake_review)
        self.assertFalse(
            fake_diagnostics._escalation_required(
                {
                    "signature_key": "incident-outbound-https-connectivity",
                    "component": "network",
                    "consecutive_failures": 99,
                },
                True,
            )
        )
        self.assertFalse(
            fake_diagnostics._escalation_required(
                {
                    "signature_key": "log-information-engine.log-timeout",
                    "component": "logs",
                    "consecutive_failures": 99,
                },
                True,
            )
        )
        self.assertFalse(
            fake_review._actionable(
                {
                    "signature_key": "incident-outbound-https-connectivity",
                    "component": "network",
                    "consecutive_failures": 99,
                    "github_request_number": 1,
                }
            )
        )

    def test_core_failure_escalates_only_after_three_consecutive_failures(self) -> None:
        fake_diagnostics = SimpleNamespace(
            _github_report=lambda record: {"signature": record.get("signature", "x")}
        )
        fake_review = SimpleNamespace(_actionable=lambda record: True)
        runtime_contract.install_diagnostic_policy(fake_diagnostics, fake_review)
        record = {
            "signature_key": "service-information-engine",
            "component": "information-engine",
            "consecutive_failures": 2,
        }
        self.assertFalse(fake_diagnostics._escalation_required(record, False))
        record["consecutive_failures"] = 3
        self.assertTrue(fake_diagnostics._escalation_required(record, False))

    def test_updater_contract_still_contains_validation_and_rollback(self) -> None:
        text = (ROOT / "run_supervisor_simple.py").read_text(encoding="utf-8")
        for marker in (
            '"fetch", "--quiet", "origin", "main"',
            '"merge-base", "--is-ancestor"',
            '"merge", "--ff-only", "origin/main"',
            "validate_checkout",
            "last_known_working_sha",
            "rollback_ref",
            "ROLLED_BACK",
            "supervisor.stop_all_services()",
            "supervisor.start_all_services()",
        ):
            self.assertIn(marker, text)

    def test_active_runtime_does_not_install_historical_acceptance_layers(self) -> None:
        loader = (ROOT / "run_with_env.py").read_text(encoding="utf-8")
        contract = (ROOT / "runtime_contract.py").read_text(encoding="utf-8")
        active_text = loader + "\n" + contract
        for forbidden in (
            "upgrade_batch_44_live_acceptance.install()",
            "diagnostic_startup_runtime.install()",
            "diagnostic_nonblocking_runtime.install()",
            "diagnostic_state_migration.install()",
            "upgrade_lifecycle_dashboard.install()",
            "applied_upgrades.install_engine()",
        ):
            self.assertNotIn(forbidden, active_text)

    def test_contract_reports_one_supervisor_and_rollback(self) -> None:
        result = runtime_contract.validate()
        self.assertEqual(result["single_supervisor"], "run_supervisor_simple.py:8876")
        self.assertEqual(result["update_seconds"], 120)
        self.assertTrue(result["rollback_required"])
        self.assertFalse(result["provider_failures_open_code_repairs"])


if __name__ == "__main__":
    unittest.main()
