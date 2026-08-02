"""Priority-aware provider lanes for the local information engine.

The old runtime serialized every provider-heavy job behind one lock.  That
protected Tradier but allowed slow news or Discord work to delay option scans.
This module keeps bounded concurrency while separating unrelated providers and
prioritizing position protection above discovery and background research.
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "provider-lanes.json"
_INSTALLED = False


@dataclass(order=True, frozen=True)
class Waiter:
    priority: int
    sequence: int
    job_name: str
    arrived_at: float


class PriorityLane:
    def __init__(self, name: str) -> None:
        self.name = name
        self._condition = threading.Condition()
        self._active: Waiter | None = None
        self._waiters: list[Waiter] = []
        self._sequence = 0
        self.last_completed = ""
        self.last_wait_seconds = 0.0

    @contextmanager
    def acquire(self, job_name: str, priority: int) -> Iterator[None]:
        with self._condition:
            self._sequence += 1
            waiter = Waiter(priority, self._sequence, job_name, time.monotonic())
            self._waiters.append(waiter)
            while True:
                selected = min(self._waiters)
                if self._active is None and selected == waiter:
                    self._waiters.remove(waiter)
                    self._active = waiter
                    self.last_wait_seconds = max(0.0, time.monotonic() - waiter.arrived_at)
                    break
                self._condition.wait(timeout=1.0)
        try:
            yield
        finally:
            with self._condition:
                self.last_completed = job_name
                self._active = None
                self._condition.notify_all()

    def snapshot(self) -> dict[str, Any]:
        with self._condition:
            return {
                "name": self.name,
                "active": self._active.job_name if self._active else "",
                "active_priority": self._active.priority if self._active else None,
                "waiting": [
                    {
                        "job": waiter.job_name,
                        "priority": waiter.priority,
                        "wait_seconds": round(time.monotonic() - waiter.arrived_at, 1),
                    }
                    for waiter in sorted(self._waiters)
                ],
                "last_completed": self.last_completed,
                "last_wait_seconds": round(self.last_wait_seconds, 2),
            }


LANES = {
    "tradier": PriorityLane("tradier"),
    "discord": PriorityLane("discord"),
    "news": PriorityLane("news"),
    "local": PriorityLane("local"),
}

JOB_LANES: dict[str, tuple[str, int]] = {
    "position-tracker": ("tradier", 0),
    "targeted-options-scan": ("tradier", 1),
    "full-options-scan": ("tradier", 2),
    "dynamic-universe-refresh": ("tradier", 3),
    "session-briefing": ("tradier", 3),
    "managed-ticker-information": ("tradier", 4),
    "off-hours-universe-screen": ("tradier", 5),
    "rotating-event-sweep": ("tradier", 5),
    "managed-ticker-news": ("news", 4),
    "research-scoring": ("news", 5),
    "discord-reporting": ("discord", 2),
    "closed-position-cleanup": ("discord", 1),
    "discord-card-migration": ("discord", 5),
    "examples-and-reviews": ("discord", 5),
    "resource-mesh-collect": ("local", 1),
    "resource-mesh-dispatch": ("local", 4),
}


def lane_for(job: Any) -> tuple[PriorityLane, int]:
    name = str(getattr(job, "name", "unknown"))
    lane_name, priority = JOB_LANES.get(
        name,
        ("tradier", 5) if bool(getattr(job, "provider_heavy", False)) else ("local", 5),
    )
    return LANES[lane_name], priority


def _write_state() -> None:
    payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "lanes": {name: lane.snapshot() for name, lane in LANES.items()},
        "contract": (
            "position protection outranks targeted scans, rotating scans, "
            "background intelligence, news, and reporting"
        ),
    }
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(STATE_PATH)


def install(engine: Any) -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    def run_background_job(job: Any) -> None:
        lane, priority = lane_for(job)
        connection = engine.connect_db()
        try:
            with lane.acquire(job.name, priority):
                _write_state()
                engine.run_job(connection, job)
        finally:
            connection.close()
            with engine.RUNNING_JOBS_LOCK:
                engine.RUNNING_JOBS.discard(job.name)
            _write_state()

    engine.run_background_job = run_background_job
    engine.PROVIDER_LANES = LANES
    engine.PROVIDER_LANE_RUNTIME = "priority-provider-lanes-v1"
    _write_state()
    _INSTALLED = True


def snapshot() -> dict[str, Any]:
    return {name: lane.snapshot() for name, lane in LANES.items()}


__all__ = ["install", "lane_for", "snapshot"]
