"""Phase 7: shared API budget and priority scheme (Master Spec Section 8).

Every Tradier call in this codebase already funnels through
market_data.tradier_get() - the "one shared factual market service"
Section 8 asks for structurally already exists. This module adds the
missing pieces: capturing the real rate-limit telemetry Tradier already
sends on every response, the named 8-tier priority scheme, and a gate
that uses both.

Verified live against the real API (not assumed): /markets/quotes then
/markets/options/chains back to back returned X-Ratelimit-Allowed: 120,
X-Ratelimit-Used incrementing 1->2 across both calls with the same
X-Ratelimit-Expiry - the spec's "provisional ~120/min" is exactly right,
and quotes/chain share one combined bucket, not separate ones.
"""

from __future__ import annotations

from typing import Any

# Section 8's priority order, exactly as listed. Only 4 and 5 have a
# real caller today (market_data_collector.py's jobs) - 1-3 have no
# caller until a bot exists (Phase 11+), but the ranking has to exist
# now so that phase has something to plug into instead of inventing it
# under pressure later. 6-8 map to the existing research/reporting jobs.
PRIORITY_OPEN_POSITION_SAFETY = 1
PRIORITY_EXIT_CRITICAL_DATA = 2
PRIORITY_ENTRY_CRITICAL_DATA = 3
PRIORITY_SHARED_SPY_OBSERVATIONS = 4
PRIORITY_SHARED_OPTIONS_COLLECTION = 5
PRIORITY_SECONDARY_CONTEXT = 6
PRIORITY_NONESSENTIAL_RESEARCH = 7
PRIORITY_RIVALRY_PRESENTATION = 8

# Never-blocked tiers: matches this codebase's existing principle that an
# open-position exit/safety path is never debounced or delayed by a
# display/research concern (see local_information_engine.py's card-push
# pacing comments for the same reasoning applied elsewhere).
_ALWAYS_ALLOWED = {
    PRIORITY_OPEN_POSITION_SAFETY,
    PRIORITY_EXIT_CRITICAL_DATA,
    PRIORITY_ENTRY_CRITICAL_DATA,
}

# Minimum fraction of the allowed budget that must remain for a tier to
# proceed. Policy, not measurement: today's real usage is roughly 2
# calls/minute against a 120/min budget, nowhere near either floor, so
# there is no real contention data to derive these from yet. Starting
# defaults, meant to be retuned once real contention is observed - same
# basis as Phase 5's daily_data_manifest grade thresholds.
_RESERVE_FRACTION = {
    PRIORITY_SHARED_SPY_OBSERVATIONS: 0.20,
    PRIORITY_SHARED_OPTIONS_COLLECTION: 0.20,
    PRIORITY_SECONDARY_CONTEXT: 0.40,
    PRIORITY_NONESSENTIAL_RESEARCH: 0.40,
    PRIORITY_RIVALRY_PRESENTATION: 0.40,
}

_STATE: dict[str, int] | None = None


def record_response_headers(response: Any) -> dict[str, int] | None:
    """Parse X-Ratelimit-* from a real requests.Response and update the
    shared state. Silently no-ops (returns None) if the headers aren't
    present - not every provider/endpoint is guaranteed to send them, and
    a missing header is not itself an error worth raising over."""
    global _STATE
    headers = getattr(response, "headers", None)
    if headers is None:
        return None
    try:
        allowed = int(headers["X-Ratelimit-Allowed"])
        used = int(headers["X-Ratelimit-Used"])
        available = int(headers["X-Ratelimit-Available"])
        expiry = int(headers["X-Ratelimit-Expiry"])
    except (KeyError, TypeError, ValueError):
        return None
    _STATE = {
        "allowed": allowed, "used": used,
        "available": available, "expiry": expiry,
    }
    return dict(_STATE)


def current_state() -> dict[str, int] | None:
    return dict(_STATE) if _STATE is not None else None


def request_allowed(priority: int) -> bool:
    """Whether a call at this priority may proceed right now.

    Fails open (True) when no telemetry has been recorded yet - blocking
    every caller before the first real response arrives would be worse
    than the rare case where an early burst goes ungated for one cycle.
    """
    if priority in _ALWAYS_ALLOWED:
        return True
    if _STATE is None:
        return True
    reserve_fraction = _RESERVE_FRACTION.get(priority, 0.0)
    allowed = _STATE["allowed"]
    if allowed <= 0:
        return True
    return (_STATE["available"] / allowed) >= reserve_fraction


def reset_for_test() -> None:
    global _STATE
    _STATE = None
