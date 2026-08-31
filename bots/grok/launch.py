"""GROK launch — start the independent paper competitor."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("grok.launch")


def build_runtime_dependencies() -> dict[str, Any]:
    """Wire shared infrastructure. Callers may override for tests."""
    import scoreboard as sb

    conn = sb.connect_db()

    def get_features() -> dict[str, Any]:
        # Placeholder — integrate with spy_intraday_features / market_memory in live deploy
        return {}

    def get_chain() -> list[dict[str, Any]]:
        return []

    def get_underlying() -> dict[str, Any]:
        return {}

    def is_session_open() -> bool:
        return True  # refine with market_calendar_runtime in live

    def minutes_to_close() -> float:
        return 120.0

    def provider_ok() -> bool:
        return True

    return {
        "scoreboard_conn": conn,
        "get_features": get_features,
        "get_chain": get_chain,
        "get_underlying": get_underlying,
        "is_session_open": is_session_open,
        "minutes_to_close": minutes_to_close,
        "provider_ok": provider_ok,
    }


def main(loop: bool = True, sleep_seconds: float = 30.0) -> None:
    from bots.grok.runtime import GrokRuntime

    deps = build_runtime_dependencies()
    runtime = GrokRuntime(**deps)
    runtime.start()
    logger.info("GROK paper competitor is live")

    try:
        while loop:
            decision = runtime.cycle()
            logger.info("cycle decision: %s — %s", decision.action, decision.reason)
            time.sleep(sleep_seconds)
    except KeyboardInterrupt:
        logger.info("shutdown requested")
    finally:
        runtime.stop()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
