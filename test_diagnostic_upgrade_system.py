from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import diagnostic_upgrade_system as diagnostics
import github_upgrade_bridge as bridge
import upgrade_batch_44


class FakeTracker:
    guild_id = "guild"

    def __init__(self, channels=None):
        self.channels = list(channels or [])
        self.calls = []
        self.next_id = 1000

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and path.endswith("/channels"):
            return self.channels
        if method == "POST" and path.endswith("/channels"):
            self.next_id += 1
            item = {"id": str(self.next_id), **(payload or {})}
            self.channels.append(item)
            return item
        if method == "POST" and "/messages" in path:
            self.next_id += 1
            return {"id": str(self.next_id)}
        if method == "PATCH":
            return {"id": path.rsplit("/", 1)[-1]}
        return None


class FakeEngine:
    def __init__(self, tracker=None):
        self.tracker = tracker
        self.state = {}
        self.JOBS = []

    def discord_tracker(self):
        return self.tracker

    def get_state(self, connection, key, default=""):
        return self.state.get(key, default)

    def set_state(self, connection, key, value):
        self.state[key] = value

    def store_observation(self, connection, kind, payload):
        self.state[f"observation:{kind}"] = payload


class DiscordCheckTests(unittest.TestCase):
    def test_discord_checks_use_current_transport_not_removed_engine_helper(self) -> None:
        tracker = FakeTracker([{"id": "1", "name": "workflow-log"}])
        with patch.object(upgrade_batch_44, "_tracker", return_value=tracker):
            checks, channels = diagnostics._discord_checks()
        self.assertEqual(channels["workflow-log"]["id"], "1")
        self.assertTrue(all(check.passed for check in checks))


class MeaningfullyDirtyTests(unittest.TestCase):
    def test_runtime_mutable_paths_are_filtered_out(self) -> None:
        # Real noise caught live: this check was flagging docs/index.html
        # etc. as "dirty" even though they're already explicitly
        # allowlisted as safe-to-be-dirty in the real deploy logic
        # (tradysquid_supervisor.runtime_mutable) - alarming on something
        # that never actually blocks a deploy.
        raw = "\n".join(
            [
                " M docs/index.html",
                " M docs/spy-market-chart.png",
                " M docs/spy-market-chart.svg",
                " M config/scanner.json",
                " M state/discord-report-state.json",
            ]
        )
        self.assertEqual(diagnostics._meaningfully_dirty(raw), "")

    def test_a_genuine_source_change_still_counts_as_dirty(self) -> None:
        raw = " M spy_scanner.py\n M docs/index.html"
        result = diagnostics._meaningfully_dirty(raw)
        self.assertIn("spy_scanner.py", result)
        self.assertNotIn("docs/index.html", result)

    def test_empty_status_stays_empty(self) -> None:
        self.assertEqual(diagnostics._meaningfully_dirty(""), "")


class LogFailureEvidenceTests(unittest.TestCase):
    def test_a_healthy_status_line_reporting_zero_failures_is_not_suspicious(self) -> None:
        # Real bug caught live: this flagged log-information-engine.log
        # DEGRADED with 27 consecutive failures, but the check's own stored
        # evidence read "trade-intelligence-health: OK - 0 failed syncs" -
        # a routine healthy status line that happened to contain the word
        # "failed" while reporting zero of them.
        line = "trade-intelligence-health: OK - 25 trades checked; 0 failed syncs; 0 research items awaiting review"
        self.assertFalse(diagnostics._line_has_genuine_failure_evidence(line))

    def test_zero_qualified_error_and_timeout_are_also_not_suspicious(self) -> None:
        self.assertFalse(diagnostics._line_has_genuine_failure_evidence("scan complete: 0 errors, 0 timeouts"))

    def test_a_genuine_nonzero_failure_count_is_still_flagged(self) -> None:
        self.assertTrue(diagnostics._line_has_genuine_failure_evidence("sync run: 3 failed syncs"))

    def test_a_real_traceback_line_is_still_flagged(self) -> None:
        self.assertTrue(diagnostics._line_has_genuine_failure_evidence("Traceback (most recent call last):"))

    def test_a_real_exception_message_is_still_flagged(self) -> None:
        self.assertTrue(diagnostics._line_has_genuine_failure_evidence("ConnectionError: timeout connecting to provider"))

    def test_zero_count_elsewhere_on_the_line_does_not_mask_a_real_failure(self) -> None:
        # "0 trades processed, 3 failed" - the zero qualifies a different
        # metric, not the failure count right before "failed".
        self.assertTrue(diagnostics._line_has_genuine_failure_evidence("0 trades processed, 3 failed"))


class TcpOpenRetryTests(unittest.TestCase):
    def test_succeeds_immediately_when_the_port_is_open(self) -> None:
        with patch.object(diagnostics.socket, "create_connection") as fake_connect:
            fake_connect.return_value.__enter__ = Mock(return_value=Mock())
            fake_connect.return_value.__exit__ = Mock(return_value=False)
            with patch.object(diagnostics.time, "sleep") as fake_sleep:
                self.assertTrue(diagnostics._tcp_open(8876))
            fake_sleep.assert_not_called()
            self.assertEqual(fake_connect.call_count, 1)

    def test_retries_past_a_transient_backlog_race_before_succeeding(self) -> None:
        # tradysquid_supervisor.py's lock port is a pure mutex with a
        # listen(1) backlog and no accept() loop - multiple independent,
        # uncoordinated health-checkers probing it at once (this 5-minute
        # diagnostic cycle, the 2-minute watchdog loop) can genuinely lose
        # the race for that single slot even though the service is
        # completely healthy. Confirmed live as the cause of
        # service-supervisor showing FAILED with the service actually up.
        calls = {"n": 0}

        def flaky_connect(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] < 3:
                raise OSError("backlog full")
            return Mock(__enter__=Mock(return_value=Mock()), __exit__=Mock(return_value=False))

        with patch.object(diagnostics.socket, "create_connection", side_effect=flaky_connect):
            with patch.object(diagnostics.time, "sleep"):
                self.assertTrue(diagnostics._tcp_open(8876))
        self.assertEqual(calls["n"], 3)

    def test_a_genuinely_down_service_still_fails_after_all_retries(self) -> None:
        with patch.object(diagnostics.socket, "create_connection", side_effect=OSError("refused")):
            with patch.object(diagnostics.time, "sleep") as fake_sleep:
                self.assertFalse(diagnostics._tcp_open(8876, attempts=3, retry_delay=0.01))
            self.assertEqual(fake_sleep.call_count, 2)


class DiagnosticUpgradeSystemTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db_patch = patch.object(diagnostics, "DB_PATH", self.root / "diagnostics.db")
        self.state_patch = patch.object(
            diagnostics, "SUPERVISOR_STATE_PATH", self.root / "supervisor-state.json"
        )
        self.db_patch.start()
        self.state_patch.start()
        self.addCleanup(self.db_patch.stop)
        self.addCleanup(self.state_patch.stop)
        diagnostics.SUPERVISOR_STATE_PATH.write_text(
            json.dumps(
                {
                    "local_sha": "abc123def456",
                    "deployed_sha": "abc123def456",
                    "last_known_working_sha": "abc123def456",
                }
            ),
            encoding="utf-8",
        )

    def check(self, key="same-failure", detail="boom", severity="ERROR", force=False):
        return diagnostics.HealthCheck(
            key,
            False,
            "test-component",
            "test operation",
            detail,
            severity=severity,
            runtime_target="test-job",
            force_upgrade=force,
        )

    def test_secret_redaction_removes_configured_and_common_tokens(self) -> None:
        with patch.dict(
            os.environ,
            {"GITHUB_UPGRADE_TOKEN": "github_pat_supersecretvalue"},
            clear=False,
        ):
            text = diagnostics.redact(
                "Authorization: Bearer abc.def token=thing "
                "github_pat_supersecretvalue sk-proj-secretvalue"
            )
        self.assertNotIn("supersecretvalue", text)
        self.assertNotIn("sk-proj-secretvalue", text)
        self.assertIn("REDACTED", text)

    def test_normalization_removes_unstable_values(self) -> None:
        first = diagnostics.normalize_error(
            "2026-08-02T01:22:33-05:00 line 123 object 0xABC request_id=foo"
        )
        second = diagnostics.normalize_error(
            "2026-08-03T02:33:44-05:00 line 999 object 0xDEF request_id=bar"
        )
        self.assertEqual(first, second)

    def test_same_failure_updates_one_local_record(self) -> None:
        with patch.object(bridge, "add_or_update_diagnostic") as github:
            diagnostics.record_failure(self.check(), sync=False)
            diagnostics.record_failure(self.check(), sync=False)
        connection = diagnostics.connect_store()
        try:
            count = connection.execute("SELECT COUNT(*) FROM diagnostics").fetchone()[0]
            row = connection.execute("SELECT * FROM diagnostics").fetchone()
        finally:
            connection.close()
        self.assertEqual(count, 1)
        self.assertEqual(row["consecutive_failures"], 2)
        self.assertEqual(row["total_failures"], 2)
        github.assert_not_called()

    def test_third_consecutive_failure_uses_shared_batch(self) -> None:
        result = {
            "issue_number": 55,
            "request_number": 4,
            "comment_id": 900,
            "created": True,
        }
        with patch.object(bridge, "add_or_update_diagnostic", return_value=result) as github:
            diagnostics.record_failure(self.check(), sync=False)
            diagnostics.record_failure(self.check(), sync=False)
            row = diagnostics.record_failure(self.check(), sync=False)
        self.assertEqual(github.call_count, 1)
        self.assertEqual(row["github_issue_number"], 55)
        self.assertEqual(row["github_request_number"], 4)
        sent = github.call_args.args[0]
        self.assertEqual(sent["diagnostic_id"], row["diagnostic_id"])
        self.assertEqual(sent["consecutive_failures"], 3)

    def test_force_upgrade_escalates_first_failure(self) -> None:
        with patch.object(
            bridge,
            "add_or_update_diagnostic",
            return_value={"issue_number": 1, "request_number": 1, "comment_id": 1},
        ) as github:
            diagnostics.record_failure(self.check(force=True), sync=False)
        github.assert_called_once()

    def test_recovery_updates_same_record(self) -> None:
        diagnostics.record_failure(self.check(), sync=False)
        recovered = diagnostics.record_recovery(
            "same-failure", "port recovered", sync=False
        )
        self.assertEqual(recovered["status"], "RECOVERED")
        self.assertEqual(recovered["consecutive_failures"], 0)
        self.assertTrue(recovered["recovery_time"])

    def test_returned_failure_is_failed_again(self) -> None:
        diagnostics.record_failure(self.check(), sync=False)
        diagnostics.record_recovery("same-failure", "recovered", sync=False)
        returned = diagnostics.record_failure(self.check(), sync=False)
        self.assertEqual(returned["status"], "FAILED AGAIN")
        self.assertEqual(returned["total_failures"], 2)

    def test_diagnostic_state_survives_reopen(self) -> None:
        created = diagnostics.record_failure(self.check(), sync=False)
        connection = diagnostics.connect_store()
        connection.close()
        reopened = diagnostics.connect_store()
        try:
            row = reopened.execute(
                "SELECT diagnostic_id FROM diagnostics WHERE signature=?",
                (created["signature"],),
            ).fetchone()
        finally:
            reopened.close()
        self.assertEqual(row["diagnostic_id"], created["diagnostic_id"])

    def test_sync_discord_is_a_no_op_since_upgrade_review_was_retired(self) -> None:
        connection = diagnostics.connect_store()
        try:
            record = diagnostics.record_failure(self.check(), connection=connection, sync=True)
            self.assertFalse(diagnostics._sync_discord(connection, record))
        finally:
            connection.close()

    def test_weekend_has_no_market_session(self) -> None:
        saturday = datetime(2026, 8, 1, 10, 0, tzinfo=diagnostics.market_data.MARKET_TZ)
        self.assertIsNone(diagnostics.official_market_session(saturday, calendar_payload={}))

    def test_market_holiday_is_skipped(self) -> None:
        self.assertIsNone(diagnostics.fallback_market_session(date(2026, 12, 25)))

    def test_day_after_thanksgiving_uses_early_close(self) -> None:
        session = diagnostics.fallback_market_session(date(2026, 11, 27))
        self.assertIsNotNone(session)
        self.assertEqual(session[1].hour, 12)

    def test_provider_calendar_controls_early_close(self) -> None:
        moment = datetime(2026, 7, 2, 11, 0, tzinfo=diagnostics.market_data.MARKET_TZ)
        payload = {
            "calendar": {
                "days": {
                    "day": {
                        "date": "2026-07-02",
                        "status": "open",
                        "open": {"start": "08:30", "end": "12:00"},
                    }
                }
            }
        }
        session = diagnostics.official_market_session(moment, calendar_payload=payload)
        self.assertEqual(session[1].hour, 12)

    def test_diagnostics_source_never_stops_or_deploys_services(self) -> None:
        text = (Path(diagnostics.__file__).read_text(encoding="utf-8"))
        self.assertNotIn("stop_all_services(", text)
        self.assertNotIn("reset --hard", text)
        self.assertNotIn("merge --ff-only", text)

    def test_install_registers_each_diagnostic_job_once(self) -> None:
        upgrade_batch_44.install_engine()
        engine = upgrade_batch_44._engine()
        original = list(engine.JOBS)
        try:
            diagnostics._INSTALLED = False
            with patch.object(diagnostics, "_seed_immediate_runs"):
                diagnostics.install()
                diagnostics._INSTALLED = False
                diagnostics.install()
            names = [job.name for job in engine.JOBS]
            self.assertEqual(names.count(diagnostics.DIAGNOSTIC_JOB), 1)
            self.assertEqual(
                int(
                    next(
                        job.interval.total_seconds()
                        for job in engine.JOBS
                        if job.name == diagnostics.DIAGNOSTIC_JOB
                    )
                ),
                300,
            )
        finally:
            engine.JOBS = original
            diagnostics._INSTALLED = False


class SharedDiagnosticBridgeTests(unittest.TestCase):
    def report(self):
        return {
            "title": "Repair updater",
            "signature": "a" * 64,
            "diagnostic_id": "DIA-AAAAAAAAAAAA",
            "severity": "ERROR",
            "component": "updater",
            "operation": "fetch",
            "evidence": "timeout",
            "consecutive_failures": 3,
            "total_failures": 3,
        }

    def test_new_diagnostic_posts_to_normal_batch(self) -> None:
        issue = {"number": 77, "html_url": "issue-url"}
        with (
            patch.object(bridge, "_open_batch", return_value=issue),
            patch.object(bridge, "_request_comments", return_value=[]),
            patch.object(bridge, "_request", return_value={"id": 900}) as request,
        ):
            result = bridge.add_or_update_diagnostic(self.report())
        self.assertTrue(result["created"])
        self.assertEqual(result["issue_number"], 77)
        self.assertEqual(request.call_args.args[0], "POST")
        body = request.call_args.kwargs["payload"]["body"]
        self.assertIn(bridge.REQUEST_MARKER, body)
        self.assertIn("DIAGNOSTIC-GENERATED", body)
        self.assertIn("AUTOMATIC DIAGNOSTIC", body)

    def test_repeated_diagnostic_updates_existing_batch_comment(self) -> None:
        marker = bridge._diagnostic_marker("a" * 64)
        existing = {
            "id": 901,
            "body": f"{bridge.REQUEST_MARKER}\n{marker}\n## Upgrade request 5",
        }
        issue = {"number": 77, "html_url": "issue-url"}
        with (
            patch.object(bridge, "_open_batch", return_value=issue),
            patch.object(bridge, "_request_comments", return_value=[existing]),
            patch.object(bridge, "_request", return_value={"id": 901}) as request,
        ):
            result = bridge.add_or_update_diagnostic(self.report())
        self.assertFalse(result["created"])
        self.assertEqual(result["request_number"], 5)
        self.assertEqual(request.call_args.args[0], "PATCH")
        self.assertIn("/issues/comments/901", request.call_args.args[1])


if __name__ == "__main__":
    unittest.main()
