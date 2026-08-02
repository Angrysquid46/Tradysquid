from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import applied_upgrade_status_runtime as status_runtime
import applied_upgrades as dashboard
import diagnostic_runtime_integration as integration
import diagnostic_upgrade_system as diagnostics


class AppliedUpgradeStatusRuntimeTests(unittest.TestCase):
    def test_status_model_covers_every_required_state(self) -> None:
        self.assertEqual(status_runtime.overall_status(True, True, "PASS"), "ACTIVE")
        self.assertEqual(
            status_runtime.overall_status(True, True, "INSTALLED"),
            "INSTALLED",
        )
        self.assertEqual(
            status_runtime.overall_status(True, True, "PENDING"),
            "PENDING",
        )
        self.assertEqual(status_runtime.overall_status(True, True, "FAIL"), "FAILED")
        self.assertEqual(
            status_runtime.overall_status(True, True, "ROLLED_BACK"),
            "ROLLED BACK",
        )
        self.assertEqual(
            status_runtime.overall_status(True, True, "SUPERSEDED"),
            "SUPERSEDED",
        )
        self.assertEqual(status_runtime.overall_status(False, True, "PASS"), "FAILED")
        self.assertEqual(status_runtime.overall_status(True, False, "PASS"), "FAILED")

    def test_no_first_receipt_is_installed_not_active(self) -> None:
        record = {
            "status": "PENDING",
            "implementation_attached": True,
            "channels_present": True,
            "runtime_detail": "no scheduler receipt yet",
        }
        self.assertTrue(status_runtime._installed_without_attempt(record))
        self.assertNotEqual(record["status"], "ACTIVE")

    def test_deployment_rollback_is_visible(self) -> None:
        channels = {
            "workflow-log": {"id": "1", "name": "workflow-log"},
            "upgrade-review": {"id": "2", "name": "upgrade-review"},
            "applied-upgrades": {"id": "3", "name": "applied-upgrades"},
        }
        state = {
            "last_update_status": "ROLLED_BACK",
            "local_sha": "oldcommit123",
            "deployed_sha": "oldcommit123",
            "rollback_result": "OK",
        }
        with (
            patch.object(dashboard, "_read_json", return_value=state),
            patch.object(dashboard, "_source_has", return_value=True),
            patch.object(dashboard, "_overall_status", status_runtime.overall_status),
        ):
            record = status_runtime._deployment_record(channels)
        self.assertEqual(record["status"], "ROLLED BACK")
        self.assertIn("rollback=OK", record["runtime_detail"])

    def test_superseded_behavior_cannot_be_reported_active(self) -> None:
        with patch.object(dashboard, "_overall_status", status_runtime.overall_status):
            records = status_runtime._superseded_records({})
        self.assertEqual(len(records), 2)
        self.assertTrue(all(item["status"] == "SUPERSEDED" for item in records))
        self.assertTrue(
            all("run_supervisor_simple.py" in item["runtime_detail"] for item in records)
        )

    def test_render_supports_every_status_without_key_error(self) -> None:
        base = {
            "title": "Test upgrade",
            "description": "Test description",
            "affected": "#upgrade-review",
            "implementation": "test.module",
            "implementation_attached": True,
            "channels_present": True,
            "channel_detail": "1/1 required channels present",
            "runtime_status": "PENDING",
            "runtime_detail": "waiting",
        }
        for state in status_runtime.STATUS_ORDER:
            record = {**base, "status": state}
            text = status_runtime.render_card(record, "abc123def456")
            self.assertIn(f"**Status:** {state}", text)
            self.assertIn("abc123def456", text)

    def test_collect_changes_only_unattempted_pending_records_to_installed(self) -> None:
        base_records = [
            {
                "key": "not-run",
                "status": "PENDING",
                "runtime_detail": "no scheduler receipt yet",
            },
            {
                "key": "retrying",
                "status": "PENDING",
                "runtime_detail": "runtime verification retry is in progress",
            },
        ]
        deployment = {"key": "deployment", "status": "ACTIVE"}
        with (
            patch.object(status_runtime, "_BASE_COLLECT", return_value=base_records),
            patch.object(status_runtime, "_deployment_record", return_value=deployment),
            patch.object(status_runtime, "_superseded_records", return_value=[]),
        ):
            records = status_runtime.collect_records(object(), {})
        by_key = {item["key"]: item for item in records}
        self.assertEqual(by_key["not-run"]["status"], "INSTALLED")
        self.assertEqual(by_key["retrying"]["status"], "PENDING")
        self.assertEqual(by_key["deployment"]["status"], "ACTIVE")


class RuntimeRendererCompositionTests(unittest.TestCase):
    def test_diagnostic_wrapper_captures_active_renderer_at_install_time(self) -> None:
        active_renderer = Mock(return_value=[{"key": "simple-two-minute-updater"}])
        original_renderer = dashboard._infra_records
        original_checks = diagnostics._job_checks
        original_specs = dashboard.INFRA_SPECS
        original_all_specs = dashboard.ALL_SPECS
        try:
            dashboard._infra_records = active_renderer
            integration._INSTALLED = False
            integration._BASE_INFRA_RECORDS = None
            integration._BASE_JOB_CHECKS = None
            integration.install()
            self.assertIs(integration._BASE_INFRA_RECORDS, active_renderer)
            self.assertIs(dashboard._infra_records, integration.diagnostic_infra_records)
        finally:
            dashboard._infra_records = original_renderer
            diagnostics._job_checks = original_checks
            dashboard.INFRA_SPECS = original_specs
            dashboard.ALL_SPECS = original_all_specs
            integration._INSTALLED = False
            integration._BASE_INFRA_RECORDS = None
            integration._BASE_JOB_CHECKS = None

    def test_status_wrapper_captures_combined_renderer_at_install_time(self) -> None:
        combined = Mock(return_value=[])
        original_collect = dashboard.collect_records
        original_status = dashboard._overall_status
        original_render = dashboard._render_card
        original_job = dashboard.dashboard_job
        try:
            dashboard.collect_records = combined
            status_runtime._INSTALLED = False
            status_runtime.install()
            self.assertIs(status_runtime._BASE_COLLECT, combined)
            self.assertIs(dashboard.collect_records, status_runtime.collect_records)
            self.assertIs(dashboard.dashboard_job, status_runtime.dashboard_job)
        finally:
            dashboard.collect_records = original_collect
            dashboard._overall_status = original_status
            dashboard._render_card = original_render
            dashboard.dashboard_job = original_job
            status_runtime._INSTALLED = False


if __name__ == "__main__":
    unittest.main()
