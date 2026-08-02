from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import updater_test_command as command


class UpdaterTestCommandTests(unittest.TestCase):
    def test_commits_match_full_and_short_sha(self) -> None:
        full = "57e8ba2c99067b8bbc512c2a741b9a5593ee5c0f"
        self.assertTrue(command.commits_match(full, full[:12]))
        self.assertTrue(command.commits_match(full[:12], full))
        self.assertFalse(command.commits_match(full, "deadbeefdead"))
        self.assertFalse(command.commits_match("unknown", full))

    def test_supervisor_state_reads_object_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"deployed_sha": "abc123"}), encoding="utf-8")
            self.assertEqual(command.supervisor_state(path)["deployed_sha"], "abc123")
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(command.supervisor_state(path), {})

    @mock.patch.object(command, "ngrok_healthy", return_value=True)
    @mock.patch.object(command, "information_engine_healthy", return_value=True)
    @mock.patch.object(command, "supervisor_state")
    @mock.patch.object(command, "running_commit")
    def test_reply_passes_only_on_matching_deployed_commit_and_healthy_services(
        self,
        running_commit: mock.Mock,
        supervisor_state: mock.Mock,
        information_engine_healthy: mock.Mock,
        ngrok_healthy: mock.Mock,
    ) -> None:
        running_commit.return_value = "57e8ba2c99067b8bbc512c2a741b9a5593ee5c0f"
        supervisor_state.return_value = {
            "deployed_sha": "57e8ba2c9906",
            "last_update_status": "DEPLOYED",
        }
        reply = command.updater_test_reply()
        self.assertIn("Automatic updater test: **PASS**", reply)
        self.assertIn("Rollback triggered: **NO**", reply)
        self.assertIn("Information engine: **healthy**", reply)
        self.assertIn("Ngrok: **healthy**", reply)

    @mock.patch.object(command, "ngrok_healthy", return_value=True)
    @mock.patch.object(command, "information_engine_healthy", return_value=True)
    @mock.patch.object(command, "supervisor_state")
    @mock.patch.object(command, "running_commit", return_value="abc123")
    def test_reply_fails_after_rollback(
        self,
        running_commit: mock.Mock,
        supervisor_state: mock.Mock,
        information_engine_healthy: mock.Mock,
        ngrok_healthy: mock.Mock,
    ) -> None:
        supervisor_state.return_value = {
            "deployed_sha": "abc123",
            "last_update_status": "ROLLED_BACK",
        }
        reply = command.updater_test_reply()
        self.assertIn("Automatic updater test: **FAIL**", reply)
        self.assertIn("Rollback triggered: **YES**", reply)


if __name__ == "__main__":
    unittest.main()
