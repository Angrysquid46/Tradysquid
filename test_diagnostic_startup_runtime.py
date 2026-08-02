from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics
import github_upgrade_bridge as bridge
import shared_upgrade_lifecycle as lifecycle


class FakeTracker:
    guild_id = "guild"

    def __init__(self, channels=None):
        self.channels = list(channels or [])
        self.calls = []
        self.next_id = 100

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.endswith("/channels"):
            return self.channels
        if method == "POST" and path.endswith("/channels"):
            self.next_id += 1
            item = {"id": str(self.next_id), **(payload or {})}
            self.channels.append(item)
            return item
        return {"id": "message"}


@dataclass(frozen=True)
class FakeJob:
    name: str
    interval: timedelta
    callback: object
    market_hours_only: bool = False
    after_hours_interval: timedelta | None = None
    background: bool = False
    provider_heavy: bool = False
    retry_interval: timedelta | None = None


class FakeEngine:
    Job = FakeJob

    def __init__(self, tracker=None):
        self.tracker = tracker
        self.JOBS = [
            FakeJob(
                diagnostics.DIAGNOSTIC_JOB,
                timedelta(minutes=5),
                lambda connection: "old",
                background=True,
                retry_interval=timedelta(minutes=2),
            )
        ]

    def discord_tracker(self):
        return self.tracker


class DiagnosticStartupRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.db_patch = patch.object(diagnostics, "DB_PATH", root / "diagnostics.db")
        self.state_patch = patch.object(
            diagnostics, "SUPERVISOR_STATE_PATH", root / "supervisor-state.json"
        )
        self.db_patch.start()
        self.state_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.state_patch.stop)
        diagnostics.SUPERVISOR_STATE_PATH.write_text(
            json.dumps(
                {
                    "service_restart_counts": {"command-bot": 1},
                    "service_health": {"command-bot": True},
                }
            ),
            encoding="utf-8",
        )

    def test_owner_channels_are_created_once_with_owner_permissions(self) -> None:
        tracker = FakeTracker(
            [
                {
                    "id": "workflow",
                    "name": "workflow-log",
                    "type": 0,
                    "parent_id": "owner-category",
                    "permission_overwrites": [{"id": "guild", "deny": "1024"}],
                }
            ]
        )
        engine = FakeEngine(tracker)
        with patch.object(diagnostics, "_engine", return_value=engine):
            created = startup._ensure_required_owner_channels()
            second = startup._ensure_required_owner_channels()
        self.assertEqual(
            set(created),
            {"upgrade-requests", "upgrade-review", "applied-upgrades"},
        )
        self.assertEqual(second, [])
        posts = [call for call in tracker.calls if call[0] == "POST"]
        self.assertEqual(len(posts), 3)
        for _, _, payload in posts:
            self.assertEqual(payload["parent_id"], "owner-category")
            self.assertEqual(payload["permission_overwrites"][0]["deny"], "1024")

    def test_restart_loop_requires_three_new_restarts_in_ten_minutes(self) -> None:
        first = startup._restart_loop_check()
        self.assertTrue(first.passed)
        diagnostics.SUPERVISOR_STATE_PATH.write_text(
            json.dumps(
                {
                    "service_restart_counts": {"command-bot": 4},
                    "service_health": {"command-bot": False},
                }
            ),
            encoding="utf-8",
        )
        second = startup._restart_loop_check()
        self.assertFalse(second.passed)
        self.assertTrue(second.force_upgrade)
        self.assertIn("command-bot restarted 3", second.detail)

    def test_acceptance_is_pending_until_real_create_recover_test_passes(self) -> None:
        with (
            patch.object(
                startup,
                "_ORIGINAL_ACCEPTANCE_CONTENT",
                return_value="✅ **PASS · Diagnostic stable reporting** · old claim",
            ),
            patch.object(startup, "_self_test_complete", return_value=False),
        ):
            pending = startup.acceptance_content([], {})
        self.assertIn("PENDING", pending)
        with (
            patch.object(
                startup,
                "_ORIGINAL_ACCEPTANCE_CONTENT",
                return_value="✅ **PASS · Diagnostic stable reporting** · old claim",
            ),
            patch.object(startup, "_self_test_complete", return_value=True),
        ):
            passed = startup.acceptance_content([], {})
        self.assertIn("PASS", passed)
        self.assertIn("failure and recovery", passed)

    def test_install_replaces_one_job_and_forces_startup_cycle(self) -> None:
        engine = FakeEngine()
        startup._INSTALLED = False
        with (
            patch.object(diagnostics, "_engine", return_value=engine),
            patch.object(startup, "_force_startup_cycle") as force,
        ):
            startup.install()
        jobs = [job for job in engine.JOBS if job.name == diagnostics.DIAGNOSTIC_JOB]
        self.assertEqual(len(jobs), 1)
        self.assertIs(jobs[0].callback, startup.diagnostic_cycle_job)
        force.assert_called_once()
        startup._INSTALLED = False


class SharedUpgradeLifecycleTests(unittest.TestCase):
    def report(self):
        return {
            "signature": "b" * 64,
            "diagnostic_id": "DIA-BBBBBBBBBBBB",
            "title": "Repair a recurring failure",
            "component": "scheduler",
            "operation": "job receipt",
            "severity": "ERROR",
            "evidence": "job failed",
            "consecutive_failures": 4,
            "total_failures": 9,
        }

    def test_ready_batch_diagnostic_is_updated_instead_of_duplicated(self) -> None:
        marker = bridge._diagnostic_marker("b" * 64)
        issue = {
            "number": 44,
            "title": f"{bridge.READY_PREFIX} 2026-08-02 · #44",
            "html_url": "ready-batch",
        }
        existing = {
            "id": 700,
            "body": f"{bridge.REQUEST_MARKER}\n{marker}\n## Upgrade request 6",
        }
        with (
            patch.object(bridge, "_list_open_issues", return_value=[issue]),
            patch.object(bridge, "_request_comments", return_value=[existing]),
            patch.object(bridge, "_request", return_value={"id": 700}) as request,
            patch.object(lifecycle, "_ORIGINAL_ADD_OR_UPDATE") as original,
        ):
            result = lifecycle.add_or_update_diagnostic(self.report())
        self.assertFalse(result["created"])
        self.assertEqual(result["batch_state"], "READY")
        self.assertEqual(result["request_number"], 6)
        self.assertEqual(request.call_args.args[0], "PATCH")
        original.assert_not_called()

    def test_new_signature_uses_normal_open_batch_creation(self) -> None:
        expected = {"created": True, "issue_number": 45, "request_number": 1}
        with (
            patch.object(bridge, "_list_open_issues", return_value=[]),
            patch.object(lifecycle, "_ORIGINAL_ADD_OR_UPDATE", return_value=expected) as original,
        ):
            result = lifecycle.add_or_update_diagnostic(self.report())
        self.assertEqual(result, expected)
        original.assert_called_once()


if __name__ == "__main__":
    unittest.main()
