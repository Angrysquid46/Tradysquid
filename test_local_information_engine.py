from __future__ import annotations

import tempfile
import unittest
import socket
import json
from datetime import date
from pathlib import Path
from unittest.mock import patch

import discord_command_bot
import ai_coordination
import dynamic_universe
import ford_scan
import local_information_engine as engine
import multi_ticker_scan
import outcome_learning
import register_discord_commands
import run_with_env
import ticker_registry
import sync_discord_structure
import ensure_tradingview_secret
import robinhood_readonly_bridge
import tradier_stream


class InformationEngineTests(unittest.TestCase):
    @staticmethod
    def market_history(closes: list[float]) -> list[dict[str, float]]:
        return [
            {"close": close, "volume": 1_000_000 + index * 1_000}
            for index, close in enumerate(closes)
        ]

    @staticmethod
    def intraday_history(closes: list[float]) -> list[dict[str, float]]:
        return [
            {"close": close, "volume": 10_000 + index * 100}
            for index, close in enumerate(closes)
        ]

    def test_intraday_selloff_can_override_slow_bullish_daily_trend(self) -> None:
        daily = self.market_history([10 + index * 0.1 for index in range(60)])
        intraday = self.intraday_history([15.9 - index * 0.08 for index in range(24)])
        context = ford_scan.directional_market_context(daily, intraday[-1]["close"], intraday)
        self.assertTrue(context["qualified"])
        self.assertEqual(context["regime"], "BEARISH / CONTROLLED")
        self.assertLessEqual(context["evidence_score"], -2)

    def test_intraday_rally_can_override_slow_bearish_daily_trend(self) -> None:
        daily = self.market_history([16 - index * 0.1 for index in range(60)])
        intraday = self.intraday_history([10.1 + index * 0.08 for index in range(24)])
        context = ford_scan.directional_market_context(daily, intraday[-1]["close"], intraday)
        self.assertTrue(context["qualified"])
        self.assertEqual(context["regime"], "BULLISH / CONTROLLED")
        self.assertGreaterEqual(context["evidence_score"], 2)

    def test_balanced_intraday_evidence_qualifies_range_strategy(self) -> None:
        daily = self.market_history([
            15.0 + (0.1 if index % 2 else -0.1)
            for index in range(60)
        ])
        intraday = self.intraday_history([
            15.0 + (0.02 if index % 2 else -0.02)
            for index in range(24)
        ])
        context = ford_scan.directional_market_context(daily, 15.0, intraday)
        self.assertTrue(context["qualified"])
        self.assertEqual(context["regime"], "NEUTRAL / RANGE")

    def test_mixed_daily_evidence_without_intraday_confirmation_is_rejected(self) -> None:
        daily = self.market_history([
            15.0 + (0.1 if index % 2 else -0.1)
            for index in range(60)
        ])
        context = ford_scan.directional_market_context(daily, 15.0)
        self.assertFalse(context["qualified"])
        self.assertEqual(context["regime"], "NO TRADE")

    def test_regular_and_swing_expirations_are_both_considered(self) -> None:
        regular, swing = ford_scan.pick_expirations(
            ["2026-08-07", "2026-08-21", "2026-09-11"],
            date(2026, 7, 30),
        )
        self.assertEqual(regular, ["2026-08-07"])
        self.assertEqual(swing, ["2026-08-21", "2026-09-11"])

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

    def test_discord_redesign_channel_names_are_unique(self) -> None:
        names = [item.name for item in sync_discord_structure.CHANNELS]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("qualified-trades", names)
        self.assertNotIn("scratches", names)
        self.assertIn("new-positions", names)
        self.assertIn("losses", names)

    def test_scanner_outputs_use_consolidated_channels(self) -> None:
        self.assertEqual(ford_scan.CHANNEL_NAMES["qualified"], "new-positions")
        self.assertEqual(ford_scan.CHANNEL_NAMES["scratches"], "losses")
        self.assertEqual(ford_scan.CHANNEL_NAMES["charts"], "charts-and-levels")

    def test_env_runner_preserves_safe_script_arguments(self) -> None:
        self.assertIn(
            "Usage: python run_with_env.py <script.py> [arguments...]",
            run_with_env.main.__code__.co_consts,
        )

    def test_tradingview_secret_initializer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / ".env"
            path.write_text("EXAMPLE=value\n", encoding="utf-8")
            self.assertTrue(ensure_tradingview_secret.ensure_secret(path))
            first = path.read_text(encoding="utf-8")
            self.assertIn("TRADINGVIEW_WEBHOOK_SECRET=", first)
            self.assertFalse(ensure_tradingview_secret.ensure_secret(path))
            self.assertEqual(path.read_text(encoding="utf-8"), first)

    def test_github_syncing_ticker_commands_are_owner_locked(self) -> None:
        owner_commands = {
            "ticker-add",
            "ticker-pause",
            "ticker-resume",
            "ticker-remove",
        }
        definitions = {
            command["name"]: command
            for command in register_discord_commands.COMMANDS
        }
        for name in owner_commands:
            self.assertEqual(definitions[name]["default_member_permissions"], "0")

    def test_learning_bot_answers_calls_and_refuses_unknown_topics(self) -> None:
        call_answer = discord_command_bot.ask_reply("What's a call option?")
        self.assertIn("Call option", call_answer)
        self.assertIn("100 shares", call_answer)
        unknown = discord_command_bot.ask_reply("Predict tomorrow's exact winner")
        self.assertIn("do not have a reliable curated answer", unknown)
        self.assertIn("will not invent", unknown)

    def test_outcome_learning_uses_all_tickers_without_auto_changes(self) -> None:
        rows = [
            {
                "ticker": ticker,
                "play_type": "LONG",
                "call_or_put": "call",
                "market_regime": "BULLISH",
                "outcome": outcome,
                "realized_pl_dollars": pnl,
                "dte_at_entry": 30,
            }
            for ticker, outcome, pnl in (
                ("F", "WIN", "5"),
                ("VALE", "LOSS", "-3"),
            )
        ]
        summary = outcome_learning.summarize(rows)
        ticker_groups = {
            item["value"]
            for item in summary["groups"]
            if item["feature"] == "ticker"
        }
        self.assertEqual(ticker_groups, {"F", "VALE"})
        self.assertIn(
            "No scanner filters are changed automatically.",
            summary["guardrails"],
        )

    def test_ai_coordination_snapshot_identifies_authoritative_commit(self) -> None:
        snapshot = ai_coordination.repository_snapshot()
        self.assertEqual(len(snapshot["commit"]), 40)
        self.assertTrue(snapshot["branch"])
        self.assertIn("dirty_files", snapshot)

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
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            dynamic_universe.CONFIG_PATH = Path(temp) / "universe.json"
            dynamic_universe.CONFIG_PATH.write_text(
                '{"seed_symbols":["VALE"],"exclude_symbols":[],"max_active_symbols":10}',
                encoding="utf-8",
            )
            self.assertEqual(discord_command_bot.command_ticker("vale"), "VALE")
            with self.assertRaises(ValueError):
                discord_command_bot.command_ticker("XYZ")
            dynamic_universe.CONFIG_PATH.write_text(
                '{"seed_symbols":["VALE"],"exclude_symbols":["VALE"],"max_active_symbols":10}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                discord_command_bot.command_ticker("VALE")
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_consolidated_channels_do_not_force_a_ticker_context(self) -> None:
        interaction = {
            "channel_id": "former-ticker-channel",
            "data": {"options": []},
        }
        self.assertEqual(
            discord_command_bot.interaction_ticker(interaction),
            discord_command_bot.command_ticker(None),
        )
        interaction["data"]["options"] = [{"name": "ticker", "value": "F"}]
        self.assertEqual(discord_command_bot.interaction_ticker(interaction), "F")

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

    def test_dynamic_universe_rotates_provider_safe_batches(self) -> None:
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            config = Path(temp) / "universe.json"
            config.write_text(
                """
                {
                  "version": 2,
                  "seed_symbols": ["F", "VALE", "XYZ"],
                  "exclude_symbols": ["XYZ"],
                  "max_active_symbols": 10
                }
                """,
                encoding="utf-8",
            )
            dynamic_universe.CONFIG_PATH = config
            dynamic_universe.initialize()
            self.assertEqual(set(dynamic_universe.active_symbols()), {"F", "VALE"})
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_tradingview_webhook_is_authenticated_and_deduplicated(self) -> None:
        original_secret = discord_command_bot.TRADINGVIEW_WEBHOOK_SECRET
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            discord_command_bot.TRADINGVIEW_WEBHOOK_SECRET = "test-secret"
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            dynamic_universe.CONFIG_PATH = Path(temp) / "universe.json"
            dynamic_universe.CONFIG_PATH.write_text(
                '{"seed_symbols":[],"exclude_symbols":[],"max_active_symbols":10}',
                encoding="utf-8",
            )
            client = discord_command_bot.APP.test_client()
            denied = client.post("/tradingview", json={"ticker": "AMD"})
            self.assertEqual(denied.status_code, 401)
            first = client.post(
                "/tradingview?secret=test-secret",
                json={"id": "same-alert", "ticker": "NASDAQ:AMD", "event": "breakout"},
            )
            second = client.post(
                "/tradingview?secret=test-secret",
                json={"id": "same-alert", "ticker": "NASDAQ:AMD", "event": "breakout"},
            )
            self.assertEqual(first.status_code, 202)
            self.assertTrue(first.get_json()["queued"])
            self.assertFalse(second.get_json()["queued"])
        discord_command_bot.TRADINGVIEW_WEBHOOK_SECRET = original_secret
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_robinhood_adapter_rejects_order_shaped_payloads(self) -> None:
        with self.assertRaises(ValueError):
            dynamic_universe.import_robinhood_snapshot({
                "orders": [{"symbol": "F", "side": "buy"}]
            })
        with self.assertRaises(ValueError):
            dynamic_universe.import_robinhood_snapshot({
                "symbols": [{"symbol": "F", "order": {"side": "buy"}}]
            })

    def test_robinhood_bridge_accepts_symbols_without_trade_capability(self) -> None:
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            dynamic_universe.CONFIG_PATH = Path(temp) / "universe.json"
            dynamic_universe.CONFIG_PATH.write_text(
                '{"seed_symbols":[],"exclude_symbols":[],"max_active_symbols":10}',
                encoding="utf-8",
            )
            self.assertEqual(
                robinhood_readonly_bridge.ingest_symbols(["f", "F"]), 1
            )
            dynamic_universe.seed_universe()
            self.assertEqual(dynamic_universe.active_symbols(), ["F"])
            connection = dynamic_universe.connect()
            try:
                row = connection.execute(
                    "SELECT source FROM universe WHERE symbol='F'"
                ).fetchone()
                self.assertEqual(row["source"], "robinhood_mcp")
            finally:
                connection.close()
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_new_closed_trades_are_binary_not_scratch(self) -> None:
        row = {"play_type": "LONG", "entry_price": "0.50"}
        ford_scan.close_row(
            row,
            {"signal": "EXPIRY CLOSE", "mark": 0.50, "pl_dollars": 0},
            ford_scan.now_ct(),
        )
        self.assertEqual(row["outcome"], "LOSS")

    def test_contract_price_guard_is_one_dollar(self) -> None:
        self.assertEqual(ford_scan.MAX_CONTRACT_ASK, 1.0)
        self.assertEqual(ford_scan.MAX_RISK_PER_TRADE, 100.0)

    def test_open_position_symbols_are_dynamic_and_deduplicated(self) -> None:
        rows = [
            {
                "ticker": "VALE",
                "play_type": "LONG",
                "option_symbol": "VALE260821C00015000",
            },
            {
                "ticker": "F",
                "play_type": "SPREAD",
                "short_symbol": "F260821P00014000",
                "long_symbol": "F260821P00013500",
            },
        ]
        self.assertEqual(
            ford_scan.symbols_for_rows(rows),
            [
                "VALE",
                "VALE260821C00015000",
                "F",
                "F260821P00014000",
                "F260821P00013500",
            ],
        )

    def test_tradier_stream_subscribes_only_to_quote_events(self) -> None:
        payload = json.loads(
            tradier_stream.TradierPositionStream._payload(
                "session", ["VALE260821C00015000"]
            )
        )
        self.assertEqual(payload["filter"], ["quote"])
        self.assertEqual(payload["symbols"], ["VALE260821C00015000"])
        self.assertTrue(payload["validOnly"])

    def test_streamed_quote_closes_paper_position_immediately(self) -> None:
        original_log = ford_scan.LOG_PATH
        with tempfile.TemporaryDirectory() as temp:
            ford_scan.LOG_PATH = Path(temp) / "plays.csv"
            row = {field: "" for field in ford_scan.LOG_HEADER}
            row.update(
                {
                    "trade_id": "VALE-STREAM-001",
                    "ticker": "VALE",
                    "play_type": "LONG",
                    "option_symbol": "VALE260821C00015000",
                    "expiration": "2026-08-21",
                    "entry_price": "0.50",
                    "outcome": "OPEN",
                }
            )
            ford_scan.write_log([row])
            engine.STREAM_QUOTES.clear()
            engine.STREAM_LAST_WRITTEN.clear()
            with (
                patch.object(
                    engine.ford_scan,
                    "market_is_open_now",
                    return_value=(True, ford_scan.now_ct()),
                ),
                patch.object(engine, "_route_stream_close") as route_close,
            ):
                engine._stream_quote_event(
                    {
                        "type": "quote",
                        "symbol": "VALE260821C00015000",
                        "bid": 0.61,
                        "ask": 0.63,
                    }
                )
            closed = ford_scan.read_log()[0]
            self.assertEqual(closed["outcome"], "WIN")
            self.assertEqual(closed["last_signal"], "TAKE PROFIT")
            route_close.assert_called_once()
        ford_scan.LOG_PATH = original_log

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
