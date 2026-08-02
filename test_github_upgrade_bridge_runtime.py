from __future__ import annotations

import unittest
from unittest.mock import patch

import github_upgrade_bridge as bridge
import github_upgrade_bridge_runtime as runtime


class GitHubUpgradeBridgeRuntimeTests(unittest.TestCase):
    def test_comments_paginate_beyond_first_hundred(self) -> None:
        first = [{"id": index} for index in range(100)]
        second = [{"id": 100}, {"id": 101}]
        with patch.object(bridge, "_request", side_effect=[first, second]) as request:
            values = runtime.list_comments(44)
        self.assertEqual(len(values), 102)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].kwargs["params"]["page"], 1)
        self.assertEqual(request.call_args_list[1].kwargs["params"]["page"], 2)

    def test_open_issue_pagination_excludes_pull_requests(self) -> None:
        payload = [
            {"number": 1, "title": bridge.OPEN_TITLE},
            {"number": 2, "title": "PR", "pull_request": {}},
        ]
        with patch.object(runtime, "_paged", return_value=payload):
            issues = runtime.list_open_issues()
        self.assertEqual([item["number"] for item in issues], [1])

    def test_failing_check_run_wins_over_combined_status(self) -> None:
        payload = {
            "check_runs": [
                {
                    "status": "completed",
                    "conclusion": "failure",
                }
            ]
        }
        with (
            patch.object(bridge, "_request", return_value=payload),
        ):
            self.assertEqual(runtime.pull_ci_state("sha"), "FAILURE")

    def test_incomplete_check_run_is_pending(self) -> None:
        payload = {
            "check_runs": [
                {
                    "status": "in_progress",
                    "conclusion": None,
                }
            ]
        }
        with patch.object(bridge, "_request", return_value=payload):
            self.assertEqual(runtime.pull_ci_state("sha"), "PENDING")

    def test_successful_check_runs_are_success(self) -> None:
        payload = {
            "check_runs": [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "neutral"},
                {"status": "completed", "conclusion": "skipped"},
            ]
        }
        with patch.object(bridge, "_request", return_value=payload):
            self.assertEqual(runtime.pull_ci_state("sha"), "SUCCESS")

    def test_combined_status_is_used_when_no_check_runs_exist(self) -> None:
        with patch.object(
            bridge,
            "_request",
            side_effect=[{"check_runs": []}, {"state": "success"}],
        ):
            self.assertEqual(runtime.pull_ci_state("sha"), "SUCCESS")

    def test_pull_queue_contains_exact_ci_next_action(self) -> None:
        pull = {
            "number": 54,
            "title": "Repair updater",
            "html_url": "url",
            "updated_at": "2026-08-02T00:00:00Z",
            "draft": False,
            "mergeable_state": "clean",
            "head": {"sha": "abc"},
        }
        with (
            patch.object(runtime, "_paged", return_value=[pull]),
            patch.object(runtime, "pull_ci_state", return_value="FAILURE"),
        ):
            queue = runtime.pull_request_queue()
        self.assertEqual(queue[0]["ci_state"], "FAILURE")
        self.assertIn("Repair", queue[0]["next_action"])

    def test_install_replaces_only_read_helpers(self) -> None:
        originals = (
            bridge._list_open_issues,
            bridge._list_comments,
            bridge.pull_request_queue,
        )
        try:
            runtime._INSTALLED = False
            runtime.install()
            self.assertIs(bridge._list_open_issues, runtime.list_open_issues)
            self.assertIs(bridge._list_comments, runtime.list_comments)
            self.assertIs(bridge.pull_request_queue, runtime.pull_request_queue)
            self.assertTrue(callable(bridge.add_request))
            self.assertTrue(callable(bridge.ready_batch))
        finally:
            (
                bridge._list_open_issues,
                bridge._list_comments,
                bridge.pull_request_queue,
            ) = originals
            runtime._INSTALLED = False


if __name__ == "__main__":
    unittest.main()
