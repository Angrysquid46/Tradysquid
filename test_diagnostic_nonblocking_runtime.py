from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import diagnostic_nonblocking_runtime as nonblocking
import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics


class DiagnosticNonblockingRuntimeTests(unittest.TestCase):
    def test_channel_bootstrap_failure_does_not_skip_local_cycle(self) -> None:
        local_cycle = Mock(return_value="20 checks; 1 failing; 0 recovered")
        collect = Mock(return_value=([], {}))
        with (
            patch.object(
                startup,
                "_ensure_required_owner_channels",
                side_effect=RuntimeError("Discord timeout"),
            ),
            patch.object(startup, "_ORIGINAL_CYCLE", local_cycle),
            patch.object(startup, "_run_stable_message_self_test"),
            patch.object(startup, "collect_health_checks", collect),
            patch.object(diagnostics, "_post_live_acceptance"),
            patch.object(nonblocking, "_local_failure") as failure,
            patch.object(nonblocking, "_local_recovery"),
        ):
            detail = nonblocking.diagnostic_cycle_job(object())
        local_cycle.assert_called_once()
        collect.assert_called_once()
        failure.assert_any_call(
            nonblocking.CHANNEL_BOOTSTRAP_KEY,
            "owner diagnostic channel bootstrap",
            unittest.mock.ANY,
        )
        self.assertIn("publication retry pending", detail)
        self.assertIn("Discord timeout", detail)

    def test_stable_message_failure_is_recorded_without_failing_cycle(self) -> None:
        with (
            patch.object(startup, "_ensure_required_owner_channels", return_value=[]),
            patch.object(startup, "_ORIGINAL_CYCLE", return_value="cycle complete"),
            patch.object(
                startup,
                "_run_stable_message_self_test",
                side_effect=RuntimeError("post failed"),
            ),
            patch.object(startup, "collect_health_checks", return_value=([], {})),
            patch.object(diagnostics, "_post_live_acceptance"),
            patch.object(nonblocking, "_local_failure") as failure,
            patch.object(nonblocking, "_local_recovery"),
        ):
            detail = nonblocking.diagnostic_cycle_job(object())
        failure.assert_any_call(
            nonblocking.LIVE_SELF_TEST_KEY,
            "stable Discord diagnostic create-and-recover proof",
            unittest.mock.ANY,
        )
        self.assertIn("cycle complete", detail)
        self.assertIn("post failed", detail)

    def test_acceptance_post_failure_is_recorded_without_failing_cycle(self) -> None:
        post = Mock(side_effect=RuntimeError("acceptance timeout"))
        with (
            patch.object(startup, "_ensure_required_owner_channels", return_value=[]),
            patch.object(startup, "_ORIGINAL_CYCLE", return_value="cycle complete"),
            patch.object(startup, "_run_stable_message_self_test"),
            patch.object(startup, "collect_health_checks", return_value=([], {})),
            patch.object(diagnostics, "_post_live_acceptance", post),
            patch.object(nonblocking, "_local_failure") as failure,
            patch.object(nonblocking, "_local_recovery"),
        ):
            detail = nonblocking.diagnostic_cycle_job(object())
        failure.assert_any_call(
            nonblocking.ACCEPTANCE_POST_KEY,
            "itemized live acceptance publication",
            unittest.mock.ANY,
        )
        self.assertIn("acceptance timeout", detail)

    def test_successful_publication_recovers_external_diagnostics(self) -> None:
        with (
            patch.object(startup, "_ensure_required_owner_channels", return_value=[]),
            patch.object(startup, "_ORIGINAL_CYCLE", return_value="cycle complete"),
            patch.object(startup, "_run_stable_message_self_test"),
            patch.object(startup, "collect_health_checks", return_value=([], {})),
            patch.object(diagnostics, "_post_live_acceptance"),
            patch.object(nonblocking, "_local_failure"),
            patch.object(nonblocking, "_local_recovery") as recovery,
        ):
            detail = nonblocking.diagnostic_cycle_job(object())
        recovered_keys = {call.args[0] for call in recovery.call_args_list}
        self.assertEqual(
            recovered_keys,
            {
                nonblocking.CHANNEL_BOOTSTRAP_KEY,
                nonblocking.LIVE_SELF_TEST_KEY,
                nonblocking.ACCEPTANCE_POST_KEY,
            },
        )
        self.assertIn("external diagnostic publication completed", detail)

    def test_module_has_no_deployment_or_restart_calls(self) -> None:
        source = open(nonblocking.__file__, encoding="utf-8").read()
        self.assertNotIn("stop_all_services", source)
        self.assertNotIn("merge --ff-only", source)
        self.assertNotIn("reset --hard", source)
        self.assertNotIn("Start-Process", source)
        self.assertNotIn("Stop-Process", source)


if __name__ == "__main__":
    unittest.main()
