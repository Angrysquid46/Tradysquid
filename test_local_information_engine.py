from __future__ import annotations

import tempfile
import unittest
import socket
from pathlib import Path
from unittest.mock import patch

import discord_command_bot
import local_information_engine as engine
import multi_ticker_scan
import register_discord_commands
import ticker_registry


class InformationEngineTests(unittest.TestCase):
    def test_exponential_moving_average(self) -> None:
        values = [float(value) for value in range(1, 31)]
        ema = engine.exponential_moving_average(values, 12)
        self.assertIsNotNone(ema)
        self.assertGreater(ema, 20)
        self.assertLess(ema, 30)

    def test_average_true_range(self) -> None:
        history = [
            {
                "high": 10 + index * 0.1,
                "low": 9 + index * 0.1,
                "close": 9.5 + index * 0.1,
            }
            for index in range(20)
        ]
        self.assertAlmostEqual(engine.average_true_range(history) or 0, 1.0)

    def test_option_quality_marks_liquid_contract(self) -> None:
        option = {
            "symbol": "F260821C00015000",
            "option_type": "call",
            "strike": 15,
            "expiration_date": "2026-08-21",
            "bid": 1.00,
            "ask": 1.05,
            "open_interest": 1000,
            "volume": 250,
            "greeks": {
                "delta": 0.65,
                "theta": -0.02,
                "mid_iv": 0.35,
            },
        }
        result = engine.option_quality(option, 15.50)
        self.assertTrue(result["liquidity_pass"])
        self.assertEqual(result["open_interest"], 1000)
        self.assertGreater(result["quality_score"], 50)

    def test_sqlite_state_and_observation_round_trip(self) -> None:
        original = engine.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            engine.DB_PATH = Path(temp) / "test.db"
            connection = engine.connect_db()
            try:
                engine.set_state(connection, "example", "value")
                engine.store_observation(connection, "market", {"price": 15.25})
                self.assertEqual(engine.get_state(connection, "example"), "value")
            finally:
                connection.close()
            latest = engine.latest_observation("market")
            self.assertIsNotNone(latest)
            self.assertEqual(latest["payload"]["price"], 15.25)
        engine.DB_PATH = original

    def test_registered_command_names_are_unique(self) -> None:
        names = [command["name"] for command in register_discord_commands.COMMANDS]
        self.assertEqual(len(names), len(set(names)))
        self.assertGreaterEqual(len(names), 18)
        self.assertIn("help", names)
        self.assertIn("chain", names)
        self.assertIn("status", names)

    def test_every_ticker_market_command_accepts_dynamic_ticker(self) -> None:
        ticker_commands = {
            "quote", "trend", "chart", "levels", "events", "chain",
            "setup", "watchlist", "performance", "dataage", "filings", "calendar",
            "why", "option", "risk", "status", "schedule", "lastscan",
        }
        commands = {
            command["name"]: command
            for command in register_discord_commands.COMMANDS
        }
        for name in ticker_commands:
            options = commands[name].get("options") or []
            ticker = next(
                (option for option in options if option.get("name") == "ticker"),
                None,
            )
            self.assertIsNotNone(ticker, name)
            self.assertFalse(ticker["required"], name)

    def test_dynamic_command_ticker_accepts_active_and_rejects_unknown_or_archived(self) -> None:
        original = ticker_registry.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            ticker_registry.DB_PATH = Path(temp) / "registry.db"
            ticker_registry.save("VALE", status="ACTIVE", note="test")
            self.assertEqual(discord_command_bot.command_ticker("vale"), "VALE")
            with self.assertRaises(ValueError):
                discord_command_bot.command_ticker("XYZ")
            ticker_registry.archive("VALE")
            with self.assertRaises(ValueError):
                discord_command_bot.command_ticker("VALE")
        ticker_registry.DB_PATH = original

    def test_ticker_channel_context_is_used_when_command_omits_ticker(self) -> None:
        original = ticker_registry.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            ticker_registry.DB_PATH = Path(temp) / "registry.db"
            ticker_registry.save(
                "VALE",
                status="ACTIVE",
                channels={"charts": "vale-chart-channel"},
                note="test",
            )
            interaction = {
                "channel_id": "vale-chart-channel",
                "data": {"options": []},
            }
            self.assertEqual(
                discord_command_bot.interaction_ticker(interaction), "VALE"
            )
            interaction["data"]["options"] = [
                {"name": "ticker", "value": "F"}
            ]
            self.assertEqual(
                discord_command_bot.interaction_ticker(interaction), "F"
            )
            self.assertEqual(
                discord_command_bot.interaction_ticker(
                    {"channel_id": "unmapped", "data": {"options": []}}
                ),
                "F",
            )
        ticker_registry.DB_PATH = original

    def test_performance_snapshot_filters_each_ticker(self) -> None:
        rows = [
            {"ticker": "F", "outcome": "OPEN"},
            {"ticker": "VALE", "outcome": "OPEN"},
        ]
        with patch.object(engine.ford_scan, "read_log", return_value=rows):
            ford = engine.performance_snapshot("F")
            vale = engine.performance_snapshot("VALE")
        self.assertEqual(ford["tracked"], 1)
        self.assertEqual(vale["tracked"], 1)

    def test_dynamic_market_replies_use_requested_ticker(self) -> None:
        snapshot = {
            "price": 14.77,
            "change_pct": 0.5,
            "bid": 14.76,
            "ask": 14.78,
            "spread_pct": 0.001,
            "volume": 1000,
            "relative_volume": 1.1,
            "day_low": 14.5,
            "day_high": 15.0,
            "observed_at": "2026-07-30T10:00:00-05:00",
            "regime": "NEUTRAL / RANGE",
            "sma20": 14.5,
            "sma50": 14.0,
            "sma200": 13.0,
            "rsi14": 56,
            "macd": 0.1,
            "atr14": 0.3,
            "bollinger_lower": 14.0,
            "bollinger_upper": 15.2,
            "support20": 14.05,
            "resistance20": 15.09,
            "reason": "range",
        }
        with patch.object(engine, "market_snapshot", return_value=snapshot):
            self.assertIn("VALE", discord_command_bot.quote_reply("VALE"))
            self.assertIn("VALE", discord_command_bot.trend_reply("VALE"))
            self.assertIn("VALE", discord_command_bot.watchlist_reply("VALE"))

    def test_ticker_desk_blocks_other_ticker_trade_and_contract_data(self) -> None:
        rows = [{
            "trade_id": "F-20260730-001",
            "ticker": "F",
            "outcome": "OPEN",
        }]
        with patch.object(
            discord_command_bot.ford_scan, "read_log", return_value=rows
        ):
            self.assertIn(
                "No tracked VALE trade",
                discord_command_bot.why_reply("VALE", "F-20260730-001"),
            )
        contract = {
            "symbol": "F260821C00015000",
            "underlying": "F",
        }
        with patch.object(engine, "contract_snapshot", return_value=contract):
            self.assertIn(
                "belongs to F, not VALE",
                discord_command_bot.option_reply(
                    "VALE", "F260821C00015000"
                ),
            )
        self.assertIn(
            "VALE",
            discord_command_bot.risk_reply("VALE", 0.25, 1, "call"),
        )

    def test_health_probe_queue_is_drained(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.bind(("127.0.0.1", 0))
        listener.listen(2)
        listener.setblocking(False)
        client = socket.create_connection(listener.getsockname(), timeout=2)
        try:
            engine.drain_health_probes(listener)
            self.assertEqual(client.recv(16), b"OK\n")
        finally:
            client.close()
            listener.close()

    def test_ticker_symbols_are_normalized(self) -> None:
        self.assertEqual(ticker_registry.normalize_ticker(" vale "), "VALE")
        with self.assertRaises(ValueError):
            ticker_registry.normalize_ticker("bad ticker!")

    def test_trade_ids_use_current_ticker(self) -> None:
        original = engine.ford_scan.TICKER
        engine.ford_scan.TICKER = "VALE"
        try:
            trade_id = engine.ford_scan.next_trade_id([], engine.ford_scan.now_ct())
            self.assertTrue(trade_id.startswith("VALE-"))
        finally:
            engine.ford_scan.TICKER = original

    def test_tracked_config_drives_all_active_backup_tickers(self) -> None:
        original = multi_ticker_scan.TICKER_CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            config = Path(temp) / "tickers.json"
            config.write_text(
                """
                {
                  "version": 1,
                  "tickers": [
                    {"ticker": "F", "status": "ACTIVE", "resume_on": ""},
                    {"ticker": "VALE", "status": "ACTIVE", "resume_on": ""},
                    {"ticker": "XYZ", "status": "ARCHIVED", "resume_on": ""}
                  ]
                }
                """,
                encoding="utf-8",
            )
            multi_ticker_scan.TICKER_CONFIG_PATH = config
            self.assertEqual(
                multi_ticker_scan.configured_active_tickers(),
                ["VALE", "F"],
            )
        multi_ticker_scan.TICKER_CONFIG_PATH = original

    def test_github_backup_workflow_runs_multi_ticker_entrypoint(self) -> None:
        workflow = (
            Path(__file__).resolve().parent
            / ".github"
            / "workflows"
            / "ford-scan.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("python multi_ticker_scan.py", workflow)
        self.assertIn("Multi-Ticker Options Scan", workflow)

    def test_ticker_pause_resume_and_archive_preserve_registry(self) -> None:
        original = ticker_registry.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            ticker_registry.DB_PATH = Path(temp) / "registry.db"
            ticker_registry.save("VALE", status="ACTIVE", note="test")
            self.assertEqual(
                ticker_registry.pause("VALE", today_only=False)["status"], "PAUSED"
            )
            self.assertEqual(ticker_registry.resume("VALE")["status"], "ACTIVE")
            self.assertEqual(ticker_registry.archive("VALE")["status"], "ARCHIVED")
            self.assertIsNotNone(ticker_registry.get("VALE"))
        ticker_registry.DB_PATH = original


if __name__ == "__main__":
    unittest.main()
