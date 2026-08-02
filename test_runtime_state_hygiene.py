from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNTIME_PATHS = (
    "state/discord-report-state.json",
    "state/ford-plays-log.csv",
    "state/diagnostics.db",
    "state/diagnostics.db-shm",
    "state/diagnostics.db-wal",
    "state/supervisor-watchdog.log",
    "state/supervisor-startup.log",
)


class RuntimeStateHygieneTests(unittest.TestCase):
    def test_runtime_paths_are_ignored_and_not_committed(self) -> None:
        ignored = {
            line.strip()
            for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        for relative in RUNTIME_PATHS:
            self.assertIn(relative, ignored)
            self.assertFalse(
                (ROOT / relative).exists(),
                f"{relative} is generated runtime data and must not be committed",
            )


if __name__ == "__main__":
    unittest.main()
