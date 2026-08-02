from __future__ import annotations

import unittest
from datetime import datetime

import diagnostic_upgrade_system as diagnostics
import market_calendar_runtime as market_runtime


class MarketCalendarRuntimeTests(unittest.TestCase):
    def payload(self, *, status="open", start="09:30", end="16:00"):
        return {
            "calendar": {
                "days": {
                    "day": {
                        "date": "2026-07-02",
                        "status": status,
                        "open": {"start": start, "end": end},
                    }
                }
            }
        }

    def test_regular_eastern_session_converts_to_central(self) -> None:
        moment = datetime(
            2026,
            7,
            2,
            10,
            0,
            tzinfo=diagnostics.ford_scan.MARKET_TZ,
        )
        session = market_runtime.official_market_session(
            moment,
            calendar_payload=self.payload(),
        )
        self.assertIsNotNone(session)
        start, end = session
        self.assertEqual((start.hour, start.minute), (8, 30))
        self.assertEqual((end.hour, end.minute), (15, 0))
        self.assertEqual(start.tzinfo, diagnostics.ford_scan.MARKET_TZ)
        self.assertEqual(end.tzinfo, diagnostics.ford_scan.MARKET_TZ)

    def test_early_close_eastern_converts_to_noon_central(self) -> None:
        moment = datetime(
            2026,
            7,
            2,
            11,
            0,
            tzinfo=diagnostics.ford_scan.MARKET_TZ,
        )
        session = market_runtime.official_market_session(
            moment,
            calendar_payload=self.payload(status="early-close", end="13:00"),
        )
        self.assertIsNotNone(session)
        self.assertEqual((session[1].hour, session[1].minute), (12, 0))

    def test_closed_provider_day_has_no_session(self) -> None:
        moment = datetime(
            2026,
            7,
            2,
            10,
            0,
            tzinfo=diagnostics.ford_scan.MARKET_TZ,
        )
        self.assertIsNone(
            market_runtime.official_market_session(
                moment,
                calendar_payload=self.payload(status="closed"),
            )
        )

    def test_fallback_stays_in_central_market_timezone(self) -> None:
        moment = datetime(
            2026,
            7,
            2,
            10,
            0,
            tzinfo=diagnostics.ford_scan.MARKET_TZ,
        )
        session = market_runtime.official_market_session(
            moment,
            calendar_payload={},
        )
        self.assertIsNotNone(session)
        self.assertEqual((session[0].hour, session[0].minute), (8, 30))
        self.assertEqual((session[1].hour, session[1].minute), (15, 0))

    def test_install_replaces_diagnostic_calendar_function(self) -> None:
        original = diagnostics.official_market_session
        try:
            market_runtime._INSTALLED = False
            market_runtime.install()
            self.assertIs(
                diagnostics.official_market_session,
                market_runtime.official_market_session,
            )
        finally:
            diagnostics.official_market_session = original
            market_runtime._INSTALLED = False


if __name__ == "__main__":
    unittest.main()
