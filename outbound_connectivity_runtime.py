"""Aggregate broad outbound HTTPS failures before diagnostic persistence.

The laptop can lose access to several HTTPS providers at once. Those symptoms are
one transport incident, not separate code defects for every scheduler job. This
runtime groups all current connection-timeout checks into one stable diagnostic
and emits one recovery check only after an entire cycle has no remaining outbound
timeout.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any, Callable

import diagnostic_review_runtime as review
import diagnostic_upgrade_system as diagnostics

VERSION = "outbound-connectivity-runtime-v1"
INCIDENT_KEY = "incident-outbound-https-connectivity"
_INSTALLED = False
_BASE_COLLECT: Callable[[Any], tuple[list[diagnostics.HealthCheck], dict[str, dict[str, Any]]]] | None = None
_BASE_CANONICAL: Callable[[diagnostics.HealthCheck], diagnostics.HealthCheck] | None = None

_TIMEOUT_MARKERS = (
    "connecttimeout",
    "connecttimeouterror",
    "connection timed out",
    "could not connect",
    "failed to connect",
    "max retries exceeded",
    "connectionerror",
)


def _is_outbound_timeout(check: diagnostics.HealthCheck) -> bool:
    if check.passed:
        return False
    text = " ".join(
        (
            str(check.detail or ""),
            str(check.runtime_target or ""),
            str(check.operation or ""),
        )
    ).casefold()
    timeout = any(marker in text for marker in _TIMEOUT_MARKERS)
    https = any(
        marker in text
        for marker in (
            "httpsconnectionpool",
            "port=443",
            ":443",
            "https://",
            "discord.com",
            "github.com",
            "tradier.com",
            "news.google.com",
        )
    )
    return timeout and https


def _hostnames(checks: list[diagnostics.HealthCheck]) -> list[str]:
    hosts: set[str] = set()
    for check in checks:
        text = " ".join((str(check.detail or ""), str(check.runtime_target or "")))
        for host in re.findall(
            r"(?i)(?:host=['\"]|https?://)([a-z0-9.-]+)",
            text,
        ):
            hosts.add(host.casefold())
    return sorted(hosts)


def _aggregate(checks: list[diagnostics.HealthCheck]) -> list[diagnostics.HealthCheck]:
    failures = [check for check in checks if _is_outbound_timeout(check)]
    remaining = [check for check in checks if check not in failures]
    if failures:
        hosts = _hostnames(failures)
        sources = sorted({f"{check.component}:{check.operation}" for check in failures})
        detail = (
            f"{len(failures)} current HTTPS timeout symptom(s) were consolidated; "
            f"hosts={', '.join(hosts) if hosts else 'unparsed'}; "
            f"sources={' | '.join(sources[:12])}"
        )
        remaining.append(
            diagnostics.HealthCheck(
                INCIDENT_KEY,
                False,
                "network",
                "outbound HTTPS connectivity",
                detail,
                severity="WARNING",
                channels="#upgrade-review · #workflow-log · #system-health",
                runtime_target="external HTTPS providers on TCP 443",
                automatic_retry="normal service schedules, five-minute diagnostics, and two-minute updater continue independently",
                healthy_services="local services remain online unless their own health checks fail",
                repair_objective="Restore reliable outbound HTTPS access without creating one repair request per endpoint or restarting healthy services.",
                acceptance_tests="Three complete diagnostic cycles contain no outbound HTTPS connection timeout across GitHub, Discord, market-data, or news providers.",
            )
        )
    else:
        remaining.append(
            diagnostics.HealthCheck(
                INCIDENT_KEY,
                True,
                "network",
                "outbound HTTPS connectivity",
                "No outbound HTTPS connection timeout was detected in the current diagnostic cycle.",
                severity="INFO",
                runtime_target="external HTTPS providers on TCP 443",
                automatic_retry="normal schedules",
                healthy_services="unchanged",
            )
        )
    return remaining


def collect_health_checks(
    engine_connection: Any,
) -> tuple[list[diagnostics.HealthCheck], dict[str, dict[str, Any]]]:
    if _BASE_COLLECT is None:
        raise RuntimeError("Outbound connectivity runtime was not installed")
    checks, channels = _BASE_COLLECT(engine_connection)
    return _aggregate(list(checks)), channels


def canonical_check(check: diagnostics.HealthCheck) -> diagnostics.HealthCheck:
    if check.key == INCIDENT_KEY:
        return check
    if _BASE_CANONICAL is None:
        raise RuntimeError("Outbound connectivity runtime was not installed")
    return _BASE_CANONICAL(check)


def install() -> None:
    global _INSTALLED, _BASE_COLLECT, _BASE_CANONICAL
    if _INSTALLED:
        return
    _BASE_COLLECT = diagnostics.collect_health_checks
    _BASE_CANONICAL = review._canonical_check
    diagnostics.collect_health_checks = collect_health_checks
    review._canonical_check = canonical_check
    _INSTALLED = True
