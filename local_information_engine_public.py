"""Run the local information engine with always-on operations installed."""

from __future__ import annotations

import json
from pathlib import Path

import dynamic_universe
import ford_scan

# Register the two always-on Discord destinations before the engine discovers
# channels. The underlying scanner remains read-only and cannot place orders.
ford_scan.CHANNEL_NAMES.setdefault("system_activity", "system-activity")
ford_scan.CHANNEL_NAMES.setdefault("automation_diagnostics", "automation-diagnostics")
for key in ("system_activity", "automation_diagnostics"):
    if key not in ford_scan.AUTOMATED_CHANNEL_KEYS:
        ford_scan.AUTOMATED_CHANNEL_KEYS.append(key)
ford_scan.SYSTEM_CHANNEL_KEYS.add("automation_diagnostics")

# Preserve the exact market-hours rotation so #system-activity can show what the
# scanner actually processed, not merely the next cursor position.
_ORIGINAL_NEXT_SCAN_BATCH = dynamic_universe.next_scan_batch
_ROTATION_STATE_PATH = Path(__file__).resolve().parent / "state" / "universe-scan-cursor.json"


def recorded_next_scan_batch(batch_size: int = 12, connection=None) -> list[str]:
    batch = _ORIGINAL_NEXT_SCAN_BATCH(batch_size=batch_size, connection=connection)
    try:
        payload = json.loads(_ROTATION_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    payload["last_batch"] = list(batch)
    payload["last_batch_at"] = dynamic_universe.now_iso()
    _ROTATION_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = _ROTATION_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(_ROTATION_STATE_PATH)
    return batch


dynamic_universe.next_scan_batch = recorded_next_scan_batch

import always_on_operations  # noqa: E402
import local_information_engine as engine  # noqa: E402

# Diagnostics and the repair worker itself are protected by the supervisor
# heartbeat. The visible activity, off-hours screen, and event sweep remain
# eligible for targeted repair if they fail, stall, or miss an interval.
always_on_operations.OPERATIONS_JOB_NAMES = {
    "scheduler-diagnostics",
    "automatic-self-repair",
}
always_on_operations.install()


if __name__ == "__main__":
    raise SystemExit(engine.main())
