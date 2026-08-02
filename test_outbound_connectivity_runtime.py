from __future__ import annotations

import unittest
from unittest.mock import Mock

import diagnostic_review_runtime as review
import diagnostic_upgrade_system as diagnostics
import outbound_connectivity_runtime as outbound


class OutboundConnectivityRuntimeTests(unittest.TestCase):
    def timeout_check(self, key: str, component: str, host: str):
        return diagnostics.HealthCheck(
            key,
            False,
            component,
            f"request to {host}",
            (
                f"ConnectTimeout: HTTPSConnectionPool(host='{host}', port=443): "
                "Max retries exceeded; Connection timed out"
            ),
            severity="ERROR",
            runtime_target=f"https://{host}/api",
        )

    def test_multiple_provider_timeouts_become_one_incident(self) -> None:
        ordinary = diagnostics.HealthCheck(
            "service-command-bot",
            True,
            "command-bot",
            "health port",
            "healthy",
        )
        checks = [
            ordinary,
            self.timeout_check("job-rotating-event-sweep", "scheduler", "news.google.com"),
            self.timeout_check("job-intraday-chart-refresh", "scheduler", "api.tradier.com"),
            self.timeout_check("discord-connectivity", "Discord", "discord.com"),
            self.timeout_check("github-fetch", "updater", "github.com"),
        ]
        aggregated = outbound._aggregate(checks)
        incidents = [item for item in aggregated if item.key == outbound.INCIDENT_KEY]
        self.assertEqual(len(incidents), 1)
        self.assertFalse(incidents[0].passed)
        self.assertIn("4 current HTTPS timeout symptom", incidents[0].detail)
        self.assertIn("api.tradier.com", incidents[0].detail)
        self.assertIn("discord.com", incidents[0].detail)
        self.assertIn("github.com", incidents[0].detail)
        self.assertIn("news.google.com", incidents[0].detail)
        self.assertIn(ordinary, aggregated)
        self.assertFalse(any(item.key == "job-intraday-chart-refresh" for item in aggregated))

    def test_recovery_is_emitted_only_when_cycle_has_no_timeout(self) -> None:
        checks = [
            diagnostics.HealthCheck(
                "discord-connectivity",
                True,
                "Discord",
                "guild channel API",
                "connected",
            ),
            diagnostics.HealthCheck(
                "job-intraday-chart-refresh",
                True,
                "scheduler",
                "job intraday-chart-refresh",
                "status=OK",
            ),
        ]
        aggregated = outbound._aggregate(checks)
        incident = next(item for item in aggregated if item.key == outbound.INCIDENT_KEY)
        self.assertTrue(incident.passed)
        self.assertIn("No outbound HTTPS connection timeout", incident.detail)

    def test_non_network_scheduler_error_stays_separate(self) -> None:
        check = diagnostics.HealthCheck(
            "job-upgrade-request-migration",
            False,
            "scheduler",
            "job upgrade-request-migration",
            "RuntimeError: required channels are missing",
            severity="ERROR",
        )
        aggregated = outbound._aggregate([check])
        self.assertIn(check, aggregated)
        recovery = next(item for item in aggregated if item.key == outbound.INCIDENT_KEY)
        self.assertTrue(recovery.passed)

    def test_incident_bypasses_endpoint_specific_recanonicalization(self) -> None:
        incident = diagnostics.HealthCheck(
            outbound.INCIDENT_KEY,
            False,
            "network",
            "outbound HTTPS connectivity",
            "hosts=discord.com, github.com, api.tradier.com",
        )
        original = outbound._BASE_CANONICAL
        outbound._BASE_CANONICAL = Mock(side_effect=AssertionError("must not recanonicalize"))
        try:
            self.assertIs(outbound.canonical_check(incident), incident)
        finally:
            outbound._BASE_CANONICAL = original

    def test_install_wraps_collection_after_review_layer(self) -> None:
        original_collect = diagnostics.collect_health_checks
        original_canonical = review._canonical_check
        original_installed = outbound._INSTALLED
        original_base_collect = outbound._BASE_COLLECT
        original_base_canonical = outbound._BASE_CANONICAL
        fake_collect = Mock(return_value=([], {}))
        fake_canonical = Mock(side_effect=lambda check: check)
        try:
            diagnostics.collect_health_checks = fake_collect
            review._canonical_check = fake_canonical
            outbound._INSTALLED = False
            outbound._BASE_COLLECT = None
            outbound._BASE_CANONICAL = None
            outbound.install()
            self.assertIs(outbound._BASE_COLLECT, fake_collect)
            self.assertIs(outbound._BASE_CANONICAL, fake_canonical)
            self.assertIs(diagnostics.collect_health_checks, outbound.collect_health_checks)
            self.assertIs(review._canonical_check, outbound.canonical_check)
        finally:
            diagnostics.collect_health_checks = original_collect
            review._canonical_check = original_canonical
            outbound._INSTALLED = original_installed
            outbound._BASE_COLLECT = original_base_collect
            outbound._BASE_CANONICAL = original_base_canonical


if __name__ == "__main__":
    unittest.main()
