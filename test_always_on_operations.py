from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import always_on_operations as operations
import local_information_engine as engine
import run_supervisor


class AlwaysOnOperationsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_jobs = list(engine.JOBS)
        self.original_installed = operations._INSTALLED

    def tearDown(self) -> None:
        engine.JOBS = self.original_jobs
        operations._INSTALLED = self.original_installed

    def temporary_database(self):
        directory = tempfile.TemporaryDirectory()
        path = Path(directory.name) / "operations.db"
        heartbeat = Path(directory.name) / "operations-heartbeat.json"
        return directory, path, heartbeat

    def test_install_adds_expected_always_on_jobs_once(self) -> None:
        operations._INSTALLED = False
        operations.install()
        names = [job.name for job in engine.JOBS]
        for required in (
            "scheduler-diagnostics",
            "system-activity",
            "off-hours-universe-screen",
            "rotating-event-sweep",
            "automatic-self-repair",
        ):
            self.assertEqual(names.count(required), 1)
        operations.install()
        names_after = [job.name for job in engine.JOBS]
        self.assertEqual(names, names_after)

    def test_job_health_detects_success_failure_overdue_and_closed_market_pause(self) -> None:
        directory, db_path, heartbeat = self.temporary_database()
        self.addCleanup(directory.cleanup)
        now = engine.utc_now()
        jobs = [
            engine.Job("good", timedelta(minutes=5), lambda connection: "ok"),
            engine.Job("failed", timedelta(minutes=5), lambda connection: "ok", retry_interval=timedelta(minutes=1)),
            engine.Job("overdue", timedelta(minutes=30), lambda connection: "ok"),
            engine.Job("market-only", timedelta(minutes=15), lambda connection: "ok", market_hours_only=True),
        ]
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(operations, "HEARTBEAT_PATH", heartbeat),
            patch.object(engine, "JOBS", jobs),
            patch.object(operations, "market_open_now", return_value=False),
        ):
            connection = engine.connect_db()
            try:
                engine.set_state(connection, "operations-started-at", (now - timedelta(hours=2)).isoformat())
                connection.execute(
                    "INSERT INTO job_runs(job_name, started_at, finished_at, status, detail) VALUES (?, ?, ?, ?, ?)",
                    ("good", (now - timedelta(minutes=2)).isoformat(), (now - timedelta(minutes=1)).isoformat(), "OK", "done"),
                )
                connection.execute(
                    "INSERT INTO job_runs(job_name, started_at, finished_at, status, detail) VALUES (?, ?, ?, ?, ?)",
                    ("failed", (now - timedelta(minutes=4)).isoformat(), (now - timedelta(minutes=3)).isoformat(), "ERROR", "provider timeout"),
                )
                connection.execute(
                    "INSERT INTO job_runs(job_name, started_at, finished_at, status, detail) VALUES (?, ?, ?, ?, ?)",
                    ("overdue", (now - timedelta(hours=3)).isoformat(), (now - timedelta(hours=3)).isoformat(), "OK", "old receipt"),
                )
                connection.commit()
                rows = {row["name"]: row for row in operations.job_health_rows(connection, now=now)}
            finally:
                connection.close()
        self.assertEqual(rows["good"]["status"], "OK")
        self.assertEqual(rows["failed"]["status"], "FAILED")
        self.assertEqual(rows["overdue"]["status"], "OVERDUE")
        self.assertEqual(rows["market-only"]["status"], "PAUSED")

    def test_self_repair_restarts_failed_job_and_records_action(self) -> None:
        directory, db_path, heartbeat = self.temporary_database()
        self.addCleanup(directory.cleanup)
        job = engine.Job(
            "failed-job",
            timedelta(minutes=5),
            lambda connection: "ok",
            retry_interval=timedelta(minutes=1),
        )
        now = engine.utc_now()
        starter = Mock(return_value=True)
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(operations, "HEARTBEAT_PATH", heartbeat),
            patch.object(engine, "JOBS", [job]),
            patch.object(operations, "market_open_now", return_value=False),
            patch.object(engine, "start_background_job", starter),
        ):
            connection = engine.connect_db()
            try:
                engine.set_state(connection, "operations-started-at", (now - timedelta(hours=1)).isoformat())
                connection.execute(
                    "INSERT INTO job_runs(job_name, started_at, finished_at, status, detail) VALUES (?, ?, ?, ?, ?)",
                    (job.name, (now - timedelta(minutes=10)).isoformat(), (now - timedelta(minutes=9)).isoformat(), "ERROR", "boom"),
                )
                connection.commit()
                result = operations.automatic_self_repair_job(connection)
                repair = connection.execute(
                    "SELECT * FROM repair_actions ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                connection.close()
        starter.assert_called_once_with(job)
        self.assertIn("failed-job", result)
        self.assertEqual(repair["target_job"], "failed-job")
        self.assertEqual(repair["result"], "STARTED")

    def test_off_hours_screen_rotates_without_calling_trade_scanner(self) -> None:
        directory, db_path, heartbeat = self.temporary_database()
        self.addCleanup(directory.cleanup)
        dashboards: list[tuple[str, str]] = []

        def snapshot(symbol: str):
            return {
                "price": 10.0,
                "change_pct": 1.0,
                "regime": "BULLISH / CONTROLLED",
                "qualified": True,
                "reason": "constructive",
                "rsi14": 55.0,
                "support20": 9.0,
                "resistance20": 11.0,
                "relative_volume": 1.2,
                "evidence_score": 70,
            }

        def dashboard(connection, channel, key, content):
            dashboards.append((channel, content))
            return True

        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(operations, "HEARTBEAT_PATH", heartbeat),
            patch.object(operations, "market_open_now", return_value=False),
            patch.object(operations.dynamic_universe, "initialize", return_value=["AAPL", "F", "SPY"]),
            patch.object(operations.dynamic_universe, "active_symbols", return_value=["AAPL", "F", "SPY"]),
            patch.object(operations.dynamic_universe, "max_active_symbols", return_value=25),
            patch.object(engine, "market_snapshot", side_effect=snapshot),
            patch.object(engine, "ranked_option_chain", return_value=[]),
            patch.object(engine, "upsert_dashboard", side_effect=dashboard),
            patch.object(operations.time, "sleep"),
        ):
            connection = engine.connect_db()
            try:
                result = operations.off_hours_universe_screen_job(connection)
                observation = connection.execute(
                    "SELECT payload_json FROM observations WHERE kind='off-hours-universe-screen' ORDER BY id DESC LIMIT 1"
                ).fetchone()
            finally:
                connection.close()
        self.assertIn("screened 3/3", result)
        payload = json.loads(observation["payload_json"])
        self.assertEqual(payload["batch"], ["AAPL", "F", "SPY"])
        self.assertEqual({channel for channel, _ in dashboards}, {"scanner_feed", "universe_watch"})
        self.assertTrue(any("opens no paper position" in content for _, content in dashboards))

    def test_event_sweep_posts_even_when_market_is_closed(self) -> None:
        directory, db_path, heartbeat = self.temporary_database()
        self.addCleanup(directory.cleanup)
        dashboards: list[str] = []
        with (
            patch.object(engine, "DB_PATH", db_path),
            patch.object(operations, "HEARTBEAT_PATH", heartbeat),
            patch.object(operations.dynamic_universe, "initialize", return_value=["F", "SPY"]),
            patch.object(
                engine,
                "fetch_ticker_news",
                return_value=[{"title": "Example event", "url": "https://example.invalid", "date": "now"}],
            ),
            patch.object(
                engine,
                "upsert_dashboard",
                side_effect=lambda connection, channel, key, content: dashboards.append(content) or True,
            ),
            patch.object(operations.time, "sleep"),
        ):
            connection = engine.connect_db()
            try:
                result = operations.rotating_event_sweep_job(connection)
            finally:
                connection.close()
        self.assertIn("checked events for 2/2", result)
        self.assertTrue(any("including weekends and off-hours" in content for content in dashboards))

    def test_heartbeat_requires_fresh_scheduler_receipt(self) -> None:
        directory, db_path, heartbeat = self.temporary_database()
        self.addCleanup(directory.cleanup)
        with patch.object(operations, "HEARTBEAT_PATH", heartbeat):
            heartbeat.write_text(
                json.dumps({"updated_at": engine.iso_now(), "scheduler": "ONLINE"}),
                encoding="utf-8",
            )
            self.assertTrue(operations.heartbeat_healthy(12))
            heartbeat.write_text(
                json.dumps({"updated_at": (engine.utc_now() - timedelta(hours=1)).isoformat()}),
                encoding="utf-8",
            )
            self.assertFalse(operations.heartbeat_healthy(12))

    def test_supervisor_information_health_requires_port_and_scheduler_heartbeat(self) -> None:
        with (
            patch.object(run_supervisor.supervisor, "port_healthy", return_value=True),
            patch.object(run_supervisor.always_on_operations, "heartbeat_healthy", return_value=False),
        ):
            self.assertFalse(run_supervisor.information_engine_health())
        with (
            patch.object(run_supervisor.supervisor, "port_healthy", return_value=True),
            patch.object(run_supervisor.always_on_operations, "heartbeat_healthy", return_value=True),
        ):
            self.assertTrue(run_supervisor.information_engine_health())


if __name__ == "__main__":
    unittest.main()
