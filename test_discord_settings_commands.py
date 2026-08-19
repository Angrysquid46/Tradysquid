"""Behavioral tests confirming Discord's settings surface reflects the real,
live SPY 0DTE constants and does not crash - regular/swing/spread filter
editing was removed along with those retired strategies.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import discord_command_bot as bot
import dynamic_universe
import spy_scanner


def _with_temp_scanner_config(initial: dict):
    class _Swap:
        def __enter__(self):
            self.original_dynamic = dynamic_universe.SCANNER_CONFIG_PATH
            self.original_spy_scanner = spy_scanner.SCANNER_CONFIG_PATH
            self.tmp = tempfile.TemporaryDirectory()
            path = Path(self.tmp.name) / "scanner.json"
            path.write_text(json.dumps(initial), encoding="utf-8")
            dynamic_universe.SCANNER_CONFIG_PATH = path
            spy_scanner.SCANNER_CONFIG_PATH = path
            return path

        def __exit__(self, *exc):
            dynamic_universe.SCANNER_CONFIG_PATH = self.original_dynamic
            spy_scanner.SCANNER_CONFIG_PATH = self.original_spy_scanner
            self.tmp.cleanup()

    return _Swap()


BASE_CONFIG = {"trade_types_enabled": {"spy_0dte_1m": True, "spy_0dte_5m": True}}






