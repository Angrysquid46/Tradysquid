from __future__ import annotations

import sys
import types
from pathlib import Path

# The schema unit under test does not call the optional Parquet collector.
# Stub that one import so this SQLite-only regression stays executable on
# Windows systems where application-control blocks PyArrow's native DLL.
collector_stub = types.ModuleType("market_data_collector")
collector_stub.capture_cycle_job = lambda _connection: "collector stub"
collector_stub.bars_capture_job = lambda _connection: "bars stub"
sys.modules.setdefault("market_data_collector", collector_stub)

import local_information_engine as engine


def test_connect_db_creates_provider_event_queue_for_startup(monkeypatch, tmp_path: Path):
    """The startup heartbeat must be able to consume an empty event queue.

    This catches the migration gap that otherwise makes an existing local
    database fail at ``provider-event-queue`` before Discord surfaces publish.
    """
    monkeypatch.setattr(engine, "DB_PATH", tmp_path / "local-information.db")
    connection = engine.connect_db()
    try:
        row = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='provider_events'"
        ).fetchone()
        assert row is not None
        assert engine.provider_event_job(connection) == "0/0 provider events processed"
    finally:
        connection.close()
