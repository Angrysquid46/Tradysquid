from __future__ import annotations

import unittest
from dataclasses import dataclass
from types import SimpleNamespace

import applied_upgrades
import upgrade_batch_44
import upgrade_batch_44_live_acceptance as live


@dataclass(frozen=True)
class FakeChannelSpec:
    category: str
    name: str
    topic: str
    channel_type: int = 0


class FakeSync:
    ChannelSpec = FakeChannelSpec
    CHANNELS = [
        FakeChannelSpec("OWNER CONTROL", "workflow-log", "releases"),
        FakeChannelSpec("OWNER CONTROL", "upgrade-requests", "requests"),
        FakeChannelSpec("OWNER CONTROL", "upgrade-review", "review"),
    ]
    CHANNEL_STARTERS = {}
    GUIDES = {}


class AppliedUpgradesTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeSync.CHANNELS = [
            FakeChannelSpec("OWNER CONTROL", "workflow-log", "releases"),
            FakeChannelSpec("OWNER CONTROL", "upgrade-requests", "requests"),
            FakeChannelSpec("OWNER CONTROL", "upgrade-review", "review"),
        ]
        FakeSync.CHANNEL_STARTERS = {}
        FakeSync.GUIDES = {}
        applied_upgrades._STRUCTURE_INSTALLED = False

    def test_catalog_preserves_original_thirteen_and_adds_reliability_repairs(self) -> None:
        payload = applied_upgrades.validate()
        self.assertEqual(payload["original_batch_upgrades"], 13)
        self.assertGreaterEqual(payload["reliability_upgrades"], 6)
        self.assertEqual(
            [item.acceptance_number for item in applied_upgrades.BATCH_SPECS],
            list(range(1, 14)),
        )
        self.assertTrue(payload["generated_card_is_not_proof"])

    def test_structure_adds_one_owner_only_applied_upgrades_channel(self) -> None:
        applied_upgrades.install_structure(FakeSync)
        applied_upgrades.install_structure(FakeSync)
        names = [item.name for item in FakeSync.CHANNELS]
        self.assertEqual(names.count("applied-upgrades"), 1)
        self.assertLess(names.index("applied-upgrades"), names.index("upgrade-requests"))
        self.assertIn("generated card alone", FakeSync.CHANNEL_STARTERS["applied-upgrades"])
        self.assertIn("ACTIVE", FakeSync.GUIDES["applied-upgrades"])
        self.assertIn("FAILED", FakeSync.GUIDES["applied-upgrades"])

    def test_generated_card_cannot_be_active_without_attachment_and_channels(self) -> None:
        self.assertEqual(
            applied_upgrades._overall_status(False, True, "PASS"),
            "FAILED",
        )
        self.assertEqual(
            applied_upgrades._overall_status(True, False, "PASS"),
            "FAILED",
        )
        self.assertEqual(
            applied_upgrades._overall_status(True, True, "PENDING"),
            "PENDING",
        )
        self.assertEqual(
            applied_upgrades._overall_status(True, True, "PASS"),
            "ACTIVE",
        )

    def test_card_names_concrete_implementation_channels_and_runtime_proof(self) -> None:
        spec = applied_upgrades.BATCH_SPECS[0]
        record = applied_upgrades._record(
            spec,
            implementation_attached=True,
            channels_present=True,
            affected="#news-and-events · #breaking-alerts",
            channel_detail="2/2 required channels present",
            runtime_status="PASS",
            runtime_detail="managed-ticker-news completed and observation exists",
        )
        text = applied_upgrades._render_card(record, "abc123def456")
        self.assertIn("What it does", text)
        self.assertIn("Affected channels", text)
        self.assertIn("Implementation", text)
        self.assertIn("Attachment proof", text)
        self.assertIn("Runtime proof", text)
        self.assertIn("abc123def456", text)
        self.assertIn("ACTIVE", text)

    def test_engine_registers_one_change_only_dashboard_job(self) -> None:
        upgrade_batch_44.install_engine()
        live.install()
        applied_upgrades._INSTALLED = False
        applied_upgrades.install_engine()
        applied_upgrades.install_engine()
        jobs = [
            job
            for job in upgrade_batch_44._engine().JOBS
            if job.name == applied_upgrades.JOB_NAME
        ]
        self.assertEqual(len(jobs), 1)
        self.assertIs(jobs[0].callback, applied_upgrades.dashboard_job)
        self.assertTrue(jobs[0].background)
        self.assertEqual(int(jobs[0].interval.total_seconds()), 300)
        self.assertEqual(int(jobs[0].retry_interval.total_seconds()), 120)

    def test_missing_target_channel_is_reported_in_channel_proof(self) -> None:
        spec = SimpleNamespace(
            channels=("system-health", "applied-upgrades"),
            display_channels="",
        )
        present, affected, detail = applied_upgrades._channel_proof(
            spec,
            {"system-health": {"id": "123", "name": "system-health"}},
        )
        self.assertFalse(present)
        self.assertIn("<#123>", affected)
        self.assertIn("#applied-upgrades missing", affected)
        self.assertIn("1/2 required channels present", detail)


if __name__ == "__main__":
    unittest.main()
