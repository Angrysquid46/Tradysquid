from __future__ import annotations

import subprocess
import unittest
from unittest.mock import Mock, patch

import run_supervisor_simple as simple


class SimpleSupervisorReconciliationTests(unittest.TestCase):
    def test_fast_forwarded_checkout_restarts_when_loaded_version_is_older(self) -> None:
        current = "a" * 40

        def fake_git(*arguments: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if arguments == ("rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(["git"], 0, stdout="main\n")
            if arguments == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(["git"], 0, stdout=f"{current}\n")
            raise AssertionError(f"unexpected git invocation: {arguments}")

        write_state = Mock()
        post = Mock()
        with (
            patch.object(simple.supervisor, "git", side_effect=fake_git),
            patch.object(simple, "fetch_remote_sha", return_value=current),
            patch.object(simple.supervisor, "state_payload", return_value={"deployed_sha": "b" * 12}),
            patch.object(simple, "validate_checkout", return_value=(True, "focused validation passed")),
            patch.object(simple.supervisor, "write_state", write_state),
            patch.object(simple.supervisor, "discord_post", post),
        ):
            self.assertTrue(simple.deploy_if_needed())

        self.assertEqual(write_state.call_args.kwargs["last_update_status"], "DEPLOYED")
        self.assertEqual(write_state.call_args.kwargs["deployed_sha"], current)
        post.assert_called_once()

    def test_matching_loaded_checkout_clears_a_stale_update_error(self) -> None:
        current = "c" * 40

        def fake_git(*arguments: str, **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if arguments == ("rev-parse", "--abbrev-ref", "HEAD"):
                return subprocess.CompletedProcess(["git"], 0, stdout="main\n")
            if arguments == ("rev-parse", "HEAD"):
                return subprocess.CompletedProcess(["git"], 0, stdout=f"{current}\n")
            raise AssertionError(f"unexpected git invocation: {arguments}")

        write_state = Mock()
        with (
            patch.object(simple.supervisor, "git", side_effect=fake_git),
            patch.object(simple, "fetch_remote_sha", return_value=current),
            patch.object(simple.supervisor, "state_payload", return_value={"deployed_sha": current[:12]}),
            patch.object(simple.supervisor, "write_state", write_state),
            patch.object(simple.supervisor, "discord_post") as post,
        ):
            self.assertFalse(simple.deploy_if_needed())

        self.assertEqual(write_state.call_args.kwargs["last_update_status"], "UP_TO_DATE")
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
