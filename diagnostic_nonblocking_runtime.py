"""Make every external diagnostic publication nonblocking.

Local health collection and persistence must complete even when Discord channel
creation, Discord posting, or the controlled live-message self-test cannot reach
Discord. External failures become ordinary local diagnostics and may later enter
the shared upgrade batch after their persistence threshold.
"""

from __future__ import annotations

from typing import Any

import diagnostic_startup_runtime as startup
import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
CHANNEL_BOOTSTRAP_KEY = "diagnostic-owner-channel-bootstrap"
LIVE_SELF_TEST_KEY = "diagnostic-live-message-proof"
ACCEPTANCE_POST_KEY = "diagnostic-live-acceptance-post"


def _local_failure(key: str, operation: str, exc: Exception) -> None:
    diagnostics.record_failure(
        diagnostics.HealthCheck(
            key,
            False,
            "diagnostic system",
            operation,
            f"{type(exc).__name__}: {exc}",
            severity="WARNING",
            channels="#upgrade-review, #upgrade-requests, #applied-upgrades",
            runtime_target="diagnostic_nonblocking_runtime",
            automatic_retry="next five-minute diagnostic cycle",
            healthy_services="unchanged",
            repair_objective="Restore external diagnostic publication without blocking local health collection.",
            acceptance_tests="Local diagnostics complete while Discord is unavailable, then the same report recovers after Discord returns.",
        ),
        sync=False,
    )


def _local_recovery(key: str, detail: str) -> None:
    diagnostics.record_recovery(key, detail, sync=False)


def diagnostic_cycle_job(engine_connection: Any) -> str:
    created: list[str] = []
    publication_failures: list[str] = []

    try:
        created = startup._ensure_required_owner_channels()
    except Exception as exc:
        publication_failures.append(f"owner channel bootstrap: {type(exc).__name__}: {exc}")
        _local_failure(
            CHANNEL_BOOTSTRAP_KEY,
            "owner diagnostic channel bootstrap",
            exc,
        )
    else:
        _local_recovery(
            CHANNEL_BOOTSTRAP_KEY,
            "Required owner diagnostic channels are accessible.",
        )

    original_post = diagnostics._post_live_acceptance
    diagnostics._post_live_acceptance = lambda *args, **kwargs: None
    try:
        detail = startup._ORIGINAL_CYCLE(engine_connection)
    finally:
        diagnostics._post_live_acceptance = original_post

    try:
        startup._run_stable_message_self_test()
    except Exception as exc:
        publication_failures.append(f"stable message self-test: {type(exc).__name__}: {exc}")
        _local_failure(
            LIVE_SELF_TEST_KEY,
            "stable Discord diagnostic create-and-recover proof",
            exc,
        )
    else:
        _local_recovery(
            LIVE_SELF_TEST_KEY,
            "Stable diagnostic create-and-recover proof completed.",
        )

    checks, channels = startup.collect_health_checks(engine_connection)
    try:
        original_post(engine_connection, checks, channels)
    except Exception as exc:
        publication_failures.append(f"live acceptance post: {type(exc).__name__}: {exc}")
        _local_failure(
            ACCEPTANCE_POST_KEY,
            "itemized live acceptance publication",
            exc,
        )
    else:
        _local_recovery(
            ACCEPTANCE_POST_KEY,
            "Itemized live acceptance publication completed.",
        )

    created_detail = (
        f"; created owner channels: {', '.join(created)}" if created else ""
    )
    failure_detail = (
        "; publication retry pending: " + " | ".join(publication_failures)[:700]
        if publication_failures
        else "; external diagnostic publication completed"
    )
    return f"{detail}{created_detail}{failure_detail}"


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    diagnostics.diagnostic_cycle_job = diagnostic_cycle_job
    engine = diagnostics._engine()
    rebuilt = []
    found = False
    for job in engine.JOBS:
        if job.name == diagnostics.DIAGNOSTIC_JOB:
            rebuilt.append(
                engine.Job(
                    job.name,
                    job.interval,
                    diagnostic_cycle_job,
                    market_hours_only=job.market_hours_only,
                    after_hours_interval=job.after_hours_interval,
                    background=job.background,
                    provider_heavy=job.provider_heavy,
                    retry_interval=job.retry_interval,
                )
            )
            found = True
        else:
            rebuilt.append(job)
    if not found:
        raise RuntimeError("The self-diagnostics scheduler job is missing")
    engine.JOBS = rebuilt
    startup._force_startup_cycle()
    _INSTALLED = True
