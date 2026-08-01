from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

import run_supervisor
import tradysquid_supervisor as supervisor


class SupervisorAvailabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        run_supervisor._LAST_READY_SIGNATURE = None

    def test_deployment_pauses_only_information_engine_until_final_restart(self) -> None:
        full_stop = Mock()
        stopped: list[str] = []

        def fake_deploy(*, force: bool = False) -> bool:
            self.assertTrue(force)
            supervisor.stop_all_services()
            return True

        with (
            patch.object(run_supervisor, "ORIGINAL_DEPLOY_IF_NEEDED", fake_deploy),
            patch.object(supervisor, "stop_all_services", full_stop),
            patch.object(supervisor, "stop_process", side_effect=stopped.append),
            patch.object(supervisor, "supervisor_log"),
            patch.object(run_supervisor.time, "sleep"),
        ):
            result = run_supervisor.low_downtime_deploy_if_needed(force=True)

        self.assertTrue(result)
        self.assertEqual(stopped, ["information-engine"])
        full_stop.assert_not_called()
        self.assertIs(supervisor.stop_all_services, full_stop)

    def test_readiness_posts_once_when_every_service_is_verified_online(self) -> None:
        ready = {service.name: True for service in supervisor.SERVICES}
        post = Mock()
        write_state = Mock()

        with (
            patch.object(run_supervisor, "ORIGINAL_ENSURE_SERVICES"),
            patch.object(supervisor, "LAST_HEALTH", ready.copy()),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "write_state", write_state),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
        ):
            run_supervisor.ensure_services_with_readiness()
            run_supervisor.ensure_services_with_readiness()

        post.assert_called_once()
        message, channel = post.call_args.args
        self.assertEqual(channel, "system-health")
        self.assertIn("services ready", message)
        self.assertIn("command-bot: **ONLINE**", message)
        self.assertIn("information-engine: **ONLINE**", message)
        self.assertIn("ngrok: **ONLINE**", message)
        self.assertEqual(write_state.call_count, 2)

    def test_readiness_posts_again_after_an_unhealthy_transition_recovers(self) -> None:
        ready = {service.name: True for service in supervisor.SERVICES}
        unhealthy = ready.copy()
        unhealthy["ngrok"] = False
        post = Mock()

        with (
            patch.object(run_supervisor, "ORIGINAL_ENSURE_SERVICES"),
            patch.object(supervisor, "discord_post", post),
            patch.object(supervisor, "write_state"),
            patch.object(supervisor, "current_sha", return_value="abc123def456"),
        ):
            with patch.object(supervisor, "LAST_HEALTH", ready.copy()):
                run_supervisor.ensure_services_with_readiness()
            with patch.object(supervisor, "LAST_HEALTH", unhealthy):
                run_supervisor.ensure_services_with_readiness()
            with patch.object(supervisor, "LAST_HEALTH", ready.copy()):
                run_supervisor.ensure_services_with_readiness()

        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
