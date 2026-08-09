from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

import local_information_engine as engine
import local_information_engine_public as public


class MarketIntelligenceVisibilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.original_db_path = engine.DB_PATH
        engine.DB_PATH = Path(self.temporary.name) / "local-information.db"
        self.connection = engine.connect_db()

    def tearDown(self) -> None:
        self.connection.close()
        engine.DB_PATH = self.original_db_path
        self.temporary.cleanup()

    def test_visibility_jobs_are_installed_once(self) -> None:
        names = [job.name for job in engine.JOBS]
        self.assertEqual(names.count("premarket-visibility"), 1)
        provider = next(job for job in engine.JOBS if job.name == "provider-event-queue")
        self.assertIs(provider.callback, public.visible_provider_event_job)

        public.install_market_intelligence_visibility()
        names_after = [job.name for job in engine.JOBS]
        self.assertEqual(names_after.count("premarket-visibility"), 1)

    def test_provider_event_posts_alert_and_status_heartbeat(self) -> None:
        event = {
            "id": 42,
            "event_key": "tv:F:breakout:123",
            "provider": "tradingview",
            "event_type": "breakout",
            "symbol": "F",
            "priority": 9,
            "received_at": "2026-08-01T19:55:00-05:00",
            "payload": {"price": 12.34, "timeframe": "15m", "reason": "level break"},
        }
        with (
            mock.patch.object(public.dynamic_universe, "claim_events", return_value=[event]),
            mock.patch.object(public.dynamic_universe, "upsert_candidates", return_value=1),
            mock.patch.object(public.dynamic_universe, "complete_event") as complete,
            mock.patch.object(public.engine, "publish_change_only", return_value=True) as publish,
            mock.patch.object(public.engine, "upsert_dashboard", return_value=True) as dashboard,
            mock.patch.object(public, "_provider_queue_counts", return_value={
                "PENDING": 0,
                "PROCESSING": 0,
                "DONE": 1,
                "ERROR": 0,
            }),
            mock.patch.object(public, "_dashboard_due", return_value=True),
        ):
            detail = public.visible_provider_event_job(self.connection)

        self.assertIn("1/1", detail)
        complete.assert_called_once_with(42)
        self.assertEqual(publish.call_args.kwargs["logical_channel"], "breaking_alerts")
        self.assertIn("Breaking Provider Alert", publish.call_args.args[2])
        self.assertEqual(dashboard.call_args.args[1], "breaking_alerts")
        self.assertIn("Breaking Alerts Status", dashboard.call_args.args[3])

    def test_weekend_premarket_card_stays_live(self) -> None:
        saturday = datetime(2026, 8, 1, 19, 52, tzinfo=ZoneInfo("America/Chicago"))
        observations = {
            "off-hours-universe-screen": {
                "observed_at": "2026-08-01T19:40:00-05:00",
                "payload": {"batch": ["F", "AAL"]},
            },
            "rotating-event-sweep": {
                "observed_at": "2026-08-01T19:30:00-05:00",
                "payload": {"batch": ["SPY", "QQQ"]},
            },
        }

        with (
            mock.patch.object(public.spy_scanner, "now_ct", return_value=saturday),
            mock.patch.object(public.spy_scanner, "market_is_open_now", return_value=(False, "weekend")),
            mock.patch.object(public.dynamic_universe, "active_symbols", return_value=["F", "AAL"]),
            mock.patch.object(public.dynamic_universe, "max_active_symbols", return_value=25),
            mock.patch.object(public.spy_scanner, "get_quotes", return_value={
                "F": {"last": 12.34, "change_percentage": 1.2, "volume": 1_500_000},
                "AAL": {"last": 11.20, "change_percentage": -2.4, "volume": 2_000_000},
            }),
            mock.patch.object(public.engine, "latest_observation", side_effect=lambda kind: observations.get(kind)),
            mock.patch.object(public, "_provider_queue_counts", return_value={
                "PENDING": 0,
                "PROCESSING": 0,
                "DONE": 12,
                "ERROR": 0,
            }),
            mock.patch.object(public.engine, "upsert_dashboard", return_value=True) as dashboard,
        ):
            detail = public.premarket_visibility_job(self.connection)

        self.assertIn("weekend research", detail)
        self.assertEqual(dashboard.call_args.args[1], "premarket")
        card = dashboard.call_args.args[3]
        self.assertIn("WEEKEND RESEARCH", card)
        self.assertIn("F, AAL", card)
        self.assertIn("SPY, QQQ", card)


if __name__ == "__main__":
    unittest.main()
