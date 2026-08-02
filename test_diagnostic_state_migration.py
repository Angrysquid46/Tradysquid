from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import diagnostic_state_migration as migration
import diagnostic_upgrade_system as diagnostics


class DiagnosticStateMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db_patch = patch.object(
            diagnostics,
            "DB_PATH",
            Path(self.temp.name) / "diagnostics.db",
        )
        self.db_patch.start()
        self.addCleanup(self.db_patch.stop)

    def insert(self, signature: str, *, failures: int, request: int | None) -> None:
        connection = diagnostics.connect_store()
        try:
            connection.execute(
                """
                INSERT INTO diagnostics(
                    signature, diagnostic_id, signature_key, severity, component,
                    operation, normalized_error, first_seen, last_seen,
                    consecutive_failures, total_failures, status,
                    github_request_number
                ) VALUES (?, ?, ?, 'WARNING', 'test', 'test', 'error', ?, ?, ?, ?, 'DEGRADED', ?)
                """,
                (
                    signature,
                    f"DIA-{signature[:12].upper()}",
                    signature,
                    diagnostics.iso_now(),
                    diagnostics.iso_now(),
                    failures,
                    failures,
                    request,
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def test_resolves_only_non_escalated_legacy_observations(self) -> None:
        self.insert("a" * 64, failures=1, request=None)
        self.insert("b" * 64, failures=3, request=None)
        self.insert("c" * 64, failures=1, request=9)
        with patch.object(diagnostics, "_current_sha", return_value="abc123def456"):
            result = migration.migrate()
        self.assertEqual(result["resolved"], 1)
        self.assertEqual(result["preserved_escalated"], 2)
        connection = diagnostics.connect_store()
        try:
            rows = {
                row["signature"]: dict(row)
                for row in connection.execute("SELECT * FROM diagnostics").fetchall()
            }
        finally:
            connection.close()
        self.assertEqual(rows["a" * 64]["status"], "RESOLVED")
        self.assertEqual(rows["a" * 64]["consecutive_failures"], 0)
        self.assertEqual(rows["b" * 64]["status"], "DEGRADED")
        self.assertEqual(rows["c" * 64]["status"], "DEGRADED")

    def test_migration_is_idempotent(self) -> None:
        self.insert("d" * 64, failures=1, request=None)
        first = migration.migrate()
        second = migration.migrate()
        self.assertEqual(first["resolved"], 1)
        self.assertTrue(second["already_completed"])
        self.assertEqual(second["resolved"], 0)


if __name__ == "__main__":
    unittest.main()
