from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import strategy_profiles
import strategy_runtime_consumption as runtime
import strategy_runtime_registry as registry


class FakeGitHub:
    def __init__(self) -> None:
        self.issues: list[dict] = []
        self.comments: dict[int, list[dict]] = {}
        self.requests: list[tuple[str, str, object]] = []
        self.next_issue = 100
        self.next_comment = 1000

    def list_open_issues(self):
        return list(self.issues)

    def list_comments(self, issue_number: int):
        return list(self.comments.get(issue_number, []))

    def request(self, method: str, path: str, *, params=None, payload=None):
        self.requests.append((method, path, payload))
        if method == "POST" and path == "/issues":
            self.next_issue += 1
            issue = {
                "number": self.next_issue,
                "title": payload["title"],
                "body": payload["body"],
                "html_url": f"https://example.invalid/issues/{self.next_issue}",
            }
            self.issues.append(issue)
            self.comments[self.next_issue] = []
            return issue
        if method == "PATCH" and path.startswith("/issues/comments/"):
            comment_id = int(path.rsplit("/", 1)[-1])
            for comments in self.comments.values():
                for comment in comments:
                    if comment["id"] == comment_id:
                        comment["body"] = payload["body"]
                        return comment
            raise AssertionError(f"Unknown comment {comment_id}")
        if method == "PATCH" and path.startswith("/issues/"):
            issue_number = int(path.rsplit("/", 1)[-1])
            issue = next(item for item in self.issues if item["number"] == issue_number)
            issue["body"] = payload["body"]
            return issue
        if method == "POST" and path.endswith("/comments"):
            issue_number = int(path.split("/")[2])
            self.next_comment += 1
            comment = {
                "id": self.next_comment,
                "body": payload["body"],
                "html_url": f"https://example.invalid/comments/{self.next_comment}",
            }
            self.comments.setdefault(issue_number, []).append(comment)
            return comment
        raise AssertionError(f"Unhandled fake GitHub request: {method} {path}")


class StrategyRuntimeRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        runtime._CACHED_DOCUMENT = None
        runtime._LAST_LOAD_META = {}

    def path_patch(self, directory: str):
        root = Path(directory)
        return patch.multiple(
            runtime,
            ACTIVE_CONFIG_PATH=root / "strategy-active.json",
            LAST_VALID_CONFIG_PATH=root / "strategy-last-valid.json",
            RUNTIME_STATE_PATH=root / "strategy-runtime.json",
            TRADE_PLAN_DIR=root / "strategy-trade-plans",
        )

    def github_patch(self, fake: FakeGitHub):
        return patch.multiple(
            registry.github,
            configured=lambda: True,
            _list_open_issues=fake.list_open_issues,
            _list_comments=fake.list_comments,
            _request=fake.request,
        )

    def test_publish_creates_one_issue_and_one_comment_per_profile(self) -> None:
        fake = FakeGitHub()
        with tempfile.TemporaryDirectory() as directory, self.path_patch(directory), patch.object(
            registry, "STATE_PATH", Path(directory) / "registry.json"
        ), self.github_patch(fake):
            document = runtime.load_active_document()
            runtime.acknowledge_profiles(document, "scanner")
            runtime.acknowledge_profiles(document, "position_manager")
            result = registry.publish_once()
            comments = fake.comments[result["issue_number"]]
        self.assertEqual(result["status"], "OK")
        self.assertTrue(result["all_profiles_active"])
        self.assertEqual(len(fake.issues), 1)
        self.assertEqual(len(comments), 6)
        self.assertEqual(
            {
                name
                for name in strategy_profiles.PROFILE_IDENTITIES
                if any(registry.profile_marker(name) in comment["body"] for comment in comments)
            },
            set(strategy_profiles.PROFILE_IDENTITIES),
        )
        self.assertTrue(all("Strategy writes enabled here:** NO" in item["body"] for item in comments))
        self.assertTrue(all("Updater involved:** NO" in item["body"] for item in comments))

    def test_second_publish_updates_without_duplicate_comments(self) -> None:
        fake = FakeGitHub()
        with tempfile.TemporaryDirectory() as directory, self.path_patch(directory), patch.object(
            registry, "STATE_PATH", Path(directory) / "registry.json"
        ), self.github_patch(fake):
            document = runtime.load_active_document()
            runtime.acknowledge_profiles(document, "scanner")
            runtime.acknowledge_profiles(document, "position_manager")
            first = registry.publish_once()
            second = registry.publish_once()
            comments = fake.comments[first["issue_number"]]
        self.assertEqual(first["issue_number"], second["issue_number"])
        self.assertEqual(len(comments), 6)
        comment_patches = [
            request
            for request in fake.requests
            if request[0] == "PATCH" and "/issues/comments/" in request[1]
        ]
        self.assertEqual(len(comment_patches), 6)

    def test_machine_record_contains_stored_and_runtime_proof(self) -> None:
        document = strategy_profiles.load_document()
        snapshot = strategy_profiles.registry_snapshot(
            document, {"schema_version": 2, "profiles": {}}
        )
        body = registry.profile_comment(
            snapshot["profiles"][0],
            {"source": "active", "fallback_used": False},
        )
        self.assertIn('"effective_profile"', body)
        self.assertIn('"scanner"', body)
        self.assertIn('"position_manager"', body)
        self.assertIn("Runtime hash match:** NO", body)
        self.assertIn("Strategy writes enabled here:** NO", body)

    def test_not_configured_is_a_nonfatal_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.object(
            registry, "STATE_PATH", Path(directory) / "registry.json"
        ), patch.object(registry.github, "configured", return_value=False), patch.object(
            registry.github, "configuration_message", return_value="missing token"
        ):
            result = registry.publish_once()
        self.assertEqual(result["status"], "NOT_CONFIGURED")
        self.assertFalse(result["updater_involved"])
        self.assertIn("missing token", result["reason"])

    def test_contract_is_read_only_and_has_six_profiles(self) -> None:
        result = registry.validate_contract()
        self.assertEqual(result["profiles"], 6)
        self.assertTrue(result["read_only"])
        self.assertEqual(result["issue_title"], registry.ISSUE_TITLE)


if __name__ == "__main__":
    unittest.main()
