from __future__ import annotations

import unittest

import upgrade_batch_44
import upgrade_batch_44_live_acceptance as live


class FakeTracker:
    def __init__(self, pages=None):
        self.pages = list(pages or [])
        self.calls = []

    def _request(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        if method == "GET" and "/messages?" in path:
            return self.pages.pop(0) if self.pages else []
        if method == "POST":
            return {"id": "new-message"}
        return None


class UpgradeBatch44LiveAcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        upgrade_batch_44.install_engine()
        live.install()

    def test_migration_recognizes_old_and_current_confirmations(self) -> None:
        self.assertTrue(
            live.is_upgrade_confirmation(
                {
                    "author": {"bot": True},
                    "content": "✅ Upgrade request 4 uploaded\nBatch issue: #44",
                }
            )
        )
        self.assertTrue(
            live.is_upgrade_confirmation(
                {
                    "author": {"bot": True},
                    "content": "Upgrade request recorded from Discord in GitHub batch #44",
                }
            )
        )
        self.assertFalse(
            live.is_upgrade_confirmation(
                {
                    "author": {"bot": False},
                    "content": "upgrade request uploaded",
                }
            )
        )
        self.assertFalse(
            live.is_upgrade_confirmation(
                {
                    "author": {"bot": True},
                    "content": "ordinary system status",
                }
            )
        )

    def test_full_history_paginates_beyond_first_hundred(self) -> None:
        first = [{"id": str(1000 - index)} for index in range(100)]
        second = [{"id": str(900 - index)} for index in range(3)]
        tracker = FakeTracker([first, second])
        pages = list(live._message_pages(tracker, "channel", full_history=True))
        self.assertEqual([len(page) for page in pages], [100, 3])
        self.assertIn("before=901", tracker.calls[1][1])

    def test_incremental_scan_reads_only_one_page(self) -> None:
        first = [{"id": str(1000 - index)} for index in range(100)]
        tracker = FakeTracker([first, [{"id": "should-not-be-read"}]])
        pages = list(live._message_pages(tracker, "channel", full_history=False))
        self.assertEqual(len(pages), 1)
        self.assertEqual(len(tracker.calls), 1)

    def test_copy_is_acknowledged_before_source_delete(self) -> None:
        tracker = FakeTracker()
        live._copy_then_delete(
            tracker,
            "destination",
            "source",
            {
                "id": "old-message",
                "author": {"bot": True},
                "content": "Upgrade request 2 uploaded\nBatch issue: #44",
            },
        )
        self.assertEqual(tracker.calls[0][0:2], ("POST", "/channels/destination/messages"))
        self.assertEqual(
            tracker.calls[1][0:2],
            ("DELETE", "/channels/source/messages/old-message"),
        )

    def test_runtime_jobs_are_unique_and_repaired(self) -> None:
        jobs = upgrade_batch_44._engine().JOBS
        names = [job.name for job in jobs]
        self.assertEqual(names.count("upgrade-request-migration"), 1)
        self.assertEqual(names.count("upgrade-batch-44-acceptance"), 1)
        migration = next(job for job in jobs if job.name == "upgrade-request-migration")
        acceptance = next(job for job in jobs if job.name == "upgrade-batch-44-acceptance")
        self.assertIs(migration.callback, live.reliable_upgrade_migration_job)
        self.assertIs(acceptance.callback, live.live_acceptance_job)


if __name__ == "__main__":
    unittest.main()
