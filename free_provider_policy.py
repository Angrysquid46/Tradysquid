"""Apply published free-provider ceilings to the resource worker.

Callers may request a lower conservative budget, but the owner explicitly wants
the available free capacity used. This policy raises known buckets to the
provider's published free allowance and relies on actual 429 responses for
backoff. It never raises an unknown provider or bypasses a returned rate limit.
"""

from __future__ import annotations

import os
from typing import Any

_INSTALLED = False


def _policy() -> dict[str, tuple[int, int]]:
    return {
        "finnhub-minute": (60, 60),
        "twelve-data-minute": (8, 60),
        "twelve-data-day": (800, 86_400),
        "alpha-vantage-day": (25, 86_400),
        "sec-second": (10, 1),
        "fred-second": (2, 1),
        "bls-day": (
            500 if os.environ.get("BLS_API_KEY", "").strip() else 25,
            86_400,
        ),
        "eia-second": (5, 1),
    }


def install(worker: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    original_reserve = worker.reserve_quota
    original_wait = worker.wait_quota

    def ceiling(
        bucket: str, limit: int, window_seconds: int
    ) -> tuple[int, int]:
        configured = _policy().get(bucket)
        if configured is None:
            return int(limit), int(window_seconds)
        published_limit, published_window = configured
        return max(int(limit), published_limit), published_window

    def reserve_quota(
        bucket: str,
        *,
        limit: int,
        window_seconds: int,
        cost: int = 1,
    ) -> bool:
        effective_limit, effective_window = ceiling(
            bucket, limit, window_seconds
        )
        return original_reserve(
            bucket,
            limit=effective_limit,
            window_seconds=effective_window,
            cost=cost,
        )

    def wait_quota(
        bucket: str,
        *,
        limit: int,
        window_seconds: int,
        cost: int = 1,
        max_wait_seconds: int = 75,
    ) -> bool:
        effective_limit, effective_window = ceiling(
            bucket, limit, window_seconds
        )
        return original_wait(
            bucket,
            limit=effective_limit,
            window_seconds=effective_window,
            cost=cost,
            max_wait_seconds=max_wait_seconds,
        )

    worker.reserve_quota = reserve_quota
    worker.wait_quota = wait_quota
    worker.FREE_PROVIDER_QUOTA_POLICY = {
        bucket: {"limit": limit, "window_seconds": window}
        for bucket, (limit, window) in _policy().items()
    }
    _INSTALLED = True


__all__ = ["install"]
