"""Run the local information engine with always-on operations installed."""

from __future__ import annotations

import ford_scan

# Register the two always-on Discord destinations before the engine discovers
# channels. The underlying scanner remains read-only and cannot place orders.
ford_scan.CHANNEL_NAMES.setdefault("system_activity", "system-activity")
ford_scan.CHANNEL_NAMES.setdefault("automation_diagnostics", "automation-diagnostics")
for key in ("system_activity", "automation_diagnostics"):
    if key not in ford_scan.AUTOMATED_CHANNEL_KEYS:
        ford_scan.AUTOMATED_CHANNEL_KEYS.append(key)
ford_scan.SYSTEM_CHANNEL_KEYS.add("automation_diagnostics")

import always_on_operations  # noqa: E402
import local_information_engine as engine  # noqa: E402


always_on_operations.install()


if __name__ == "__main__":
    raise SystemExit(engine.main())
