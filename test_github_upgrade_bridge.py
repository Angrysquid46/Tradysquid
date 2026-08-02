from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

import github_upgrade_bridge as bridge


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300
        self.content = b"" if payload is None else b"json"
        self.text = ""

    def json(self):
        return self._payload


class GitHubUpgradeBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(
            os.environ,
            {
                "GITHUB_UPGRADE_TOKEN": "github_pat_test",
                "GITHUB_REPOSITORY": "Angrysquid46/Tradysquid",
            },
            clear=False,
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_missing_token_reports_configuration_problem(self) -> None:
        with patch.dict(os.environ, {"GITHUB_UPGRADE_TOKEN": ""}, clear=False):
            self.assertFalse(bridge.configured())
            self.assertIn("GITHUB_UPGRADE_TOKEN", bridge.configuration_message())
            with self.assertRaises(bridge.GitHubUpgradeError):
                bridge.batch_status()

    def test_add_request_creates_batch_and_comment(self) -> None:
        issue = {
            "number": 41,
            "title": bridge.OPEN_TITLE,
            "html_url": "https://github.com/Angrysquid46/Tradysquid/issues/41",
            "body": "**Status:** OPEN",
        }
        responses = [
            FakeResponse(200, []),
            FakeResponse(201, issue),
            FakeResponse(200, []),
            FakeResponse(201, {"id": 9001}),
        ]
        request = Mock(side_effect=responses)
        with patch.object(bridge.requests, "request", request):
            result = bridge.add_request(
                "Add IV percentile to option cards", discord_user_id="123"
            )

        self.assertEqual(result["issue_number"], 41)
        self.assertEqual(result["request_number"], 1)
        self.assertEqual(request.call_count, 4)
        posted = request.call_args_list[-1].kwargs["json"]["body"]
        self.assertIn(bridge.REQUEST_MARKER, posted)
        self.assertIn("Add IV percentile", posted)
        headers = request.call_args_list[-1].kwargs["headers"]
        self.assertEqual(headers["Authorization"], "Bearer github_pat_test")

    def test_ready_batch_marks_issue_ready(self) -> None:
        issue = {
            "number": 42,
            "title": bridge.OPEN_TITLE,
            "html_url": "https://github.com/Angrysquid46/Tradysquid/issues/42",
            "body": "**Status:** OPEN",
        }
        comments = [{"body": f"{bridge.REQUEST_MARKER}\nRequest"}]
        updated = dict(issue)
        updated["title"] = f"{bridge.READY_PREFIX} now"
        responses = [
            FakeResponse(200, [issue]),
            FakeResponse(200, comments),
            FakeResponse(201, {"id": 12}),
            FakeResponse(200, updated),
        ]
        request = Mock(side_effect=responses)
        with patch.object(bridge.requests, "request", request):
            result = bridge.ready_batch("Implement together", discord_user_id="123")

        self.assertEqual(result["request_count"], 1)
        self.assertEqual(request.call_args_list[-1].args[0], "PATCH")
        payload = request.call_args_list[-1].kwargs["json"]
        self.assertTrue(payload["title"].startswith(bridge.READY_PREFIX))
        self.assertIn("**Status:** READY", payload["body"])

    def test_forbidden_response_explains_permissions(self) -> None:
        response = FakeResponse(403, {"message": "Resource not accessible"})
        with patch.object(bridge.requests, "request", return_value=response):
            with self.assertRaisesRegex(bridge.GitHubUpgradeError, "Issues read/write"):
                bridge.batch_status()


if __name__ == "__main__":
    unittest.main()
