from __future__ import annotations

import tempfile
import unittest
import socket
import json
from datetime import date, datetime, timedelta
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
import recover_discord_trade_history
import run_with_env
import ticker_registry
import sync_discord_structure
import ensure_tradingview_secret
import robinhood_readonly_bridge
import tradier_stream


class InformationEngineTests(unittest.TestCase):
    def test_discord_closed_archive_recovers_pl_and_marks_missing_thesis(self) -> None:
        message = {
            "id": "1532840284373647391",
            "content": "\n".join(
                [
                    "## 🟥 NU #009 · LOSS · LONG PUT",
                    "**Expiration:** 08/21/26",
                    "🟢 BUY 1 NU 14 PUT",
                    "**Entry debit:** $0.50 ($50)",
                    "**Exit credit:** $0.38 ($38)",
                    "**Realized P/L:** -$12",
                    "**Return:** -24%",
                    "**Close reason:** STOP OUT",
                    "**MFE:** +2%",
                    "**MAE:** -24%",
                    "**Closed:** 07/31/26 2:59 PM CT",
                ]
            ),
        }
        row = recover_discord_trade_history.parse_closed_card(message)
        self.assertIsNotNone(row)
        assert row is not None
        self.assertEqual(row["ticker"], "NU")
        self.assertEqual(float(row["realized_pl_dollars"]), -12.0)
        self.assertEqual(row["outcome"], "LOSS")
        self.assertIn("unavailable", row["thesis"])
        self.assertIn("NU #009", ford_scan.trade_title(row))

        later_version = dict(row)
        later_version["realized_pl_dollars"] = "-14"
        self.assertTrue(recover_discord_trade_history.same_trade(row, later_version))

    def test_new_trade_persists_full_thesis_checklist(self) -> None:
        candidate = {
            "play_type": "REGULAR", "call_or_put": "call", "strike": "15",
            "expiration": "2026-08-07", "option_symbol": "F260807C00015000",
            "cost_or_credit": "0.25 debit", "entry_price": 0.25, "delta": 0.4,
            "theta": -0.02, "iv": 0.5, "pop": 40, "max_profit": 0,
            "max_risk": 25, "breakeven": 15.25, "open_interest": 500,
            "bid_ask_width": 0.03, "option_volume": 100, "score": 80,
            "setup_reason": "price above VWAP with volume confirmation",
            "market_regime": "BULLISH / CONTROLLED",
        }
        row = ford_scan.candidate_to_row(candidate, [], ford_scan.now_ct())
        for key in (
            "thesis", "entry_confirmation", "invalidation", "risk_plan",
            "learning_plan", "evidence_limitations",
        ):
            self.assertTrue(row[key], key)

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

    def test_trade_cards_use_each_rows_ticker(self) -> None:
        row = {
            "ticker": "RIVN",
            "trade_id": "RIVN-20260731-001",
            "play_type": "CALL",
            "call_or_put": "CALL",
            "strike": "15",
            "expiration": "2026-08-07",
            "entry_price": "0.35",
        }
        self.assertTrue(ford_scan.trade_title(row).startswith("RIVN #001"))
        card = ford_scan.entry_alert_text(row)
        self.assertIn("RIVN #001", card)
        self.assertIn("BUY 1 RIVN 15 CALL", card)
        self.assertNotIn("BUY 1 F 15 CALL", card)

    def test_all_existing_play_types_map_to_separate_performance_styles(self) -> None:
        cases = {
            ("REGULAR", "call"): "regular-call",
            ("REGULAR", "put"): "regular-put",
            ("SWING", "call"): "swing-call",
            ("SWING", "put"): "swing-put",
            ("SPREAD", "put"): "bull-put-spread",
            ("SPREAD", "call"): "bear-call-spread",
        }
        for (play_type, kind), expected in cases.items():
            self.assertEqual(
                ford_scan.play_style_key(
                    {"play_type": play_type, "call_or_put": kind}
                ),
                expected,
            )

    def test_trade_cards_apply_learning_center_without_inventing_history(self) -> None:
        row = {
            "ticker": "F",
            "trade_id": "F-20260731-090",
            "play_type": "REGULAR",
            "call_or_put": "call",
            "strike": "15",
            "expiration": "2026-08-07",
            "entry_price": "0.25",
            "market_regime": "BULLISH / CONTROLLED",
            "setup_reason": "price held above VWAP with rising volume",
        }
        with patch(
            "ford_scan.learning_channel_reference",
            side_effect=lambda channel: f"#{channel}",
        ):
            card = ford_scan.entry_alert_text(row)
        self.assertIn("Applied Learning Center Analysis", card)
        self.assertIn("price held above VWAP", card)
        self.assertIn("#06-charts-price-action", card)
        self.assertIn("not reconstructed", card)

    def test_play_style_performance_includes_quality_and_journal_link(self) -> None:
        rows = [
            {
                "trade_id": "F-1",
                "ticker": "F",
                "play_type": "REGULAR",
                "call_or_put": "call",
                "strike": "15",
                "outcome": "WIN",
                "realized_pl_dollars": "20",
                "pct_gain_loss": "20",
                "max_favorable_pct": "25",
                "max_adverse_pct": "-5",
                "timestamp": "2026-07-31T10:00:00-05:00",
                "closed_at": "2026-07-31T12:00:00-05:00",
                "discord_thread_id": "thread-1",
            }
        ]
        with patch.object(ford_scan, "DISCORD_GUILD_ID", "guild-1"):
            card = ford_scan.format_play_style_performance(rows, "regular-call")
        self.assertIn("Regular Call Performance", card)
        self.assertIn("Profit factor", card)
        self.assertIn("avg hold **2.0h**", card)
        self.assertIn("journal", card)

    def test_trade_snapshot_renders_four_actionable_timeframes(self) -> None:
        intraday = [
            {"time": f"2026-08-01 10:{index:02d}:00", "close": 15 + index * 0.01}
            for index in range(30)
        ]
        daily = [
            {
                "date": (date(2025, 1, 1) + timedelta(days=index)).isoformat(),
                "close": 12 + index * 0.01,
                "volume": 1_000_000,
            }
            for index in range(420)
        ]
        row = {
            "trade_id": "F-20260801-001",
            "ticker": "F",
            "play_type": "SWING",
            "call_or_put": "call",
            "strike": "15",
            "expiration": "2026-08-21",
        }
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(ford_scan, "TRADE_SNAPSHOT_DIR", Path(directory)):
                output = ford_scan.render_trade_multitimeframe_snapshot(
                    row, "entry", intraday, daily
                )
            self.assertIsNotNone(output)
            self.assertTrue(output.exists())
            self.assertIn("multitimeframe", output.name)

    def test_trade_daily_history_is_cached_without_staling_intraday(self) -> None:
        ford_scan.DAILY_SNAPSHOT_CACHE.clear()
        bars = [{"date": "2026-08-01", "close": 10.0}]
        with patch.object(ford_scan, "get_daily_history", return_value=bars) as fetch:
            self.assertEqual(ford_scan.trade_daily_history("AAL"), bars)
            self.assertEqual(ford_scan.trade_daily_history("aal"), bars)
        fetch.assert_called_once_with("AAL", days=420)

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
        self.assertIn("scan-now", names)

    def test_discord_redesign_channel_names_are_unique(self) -> None:
        names = [item.name for item in sync_discord_structure.CHANNELS]
        self.assertEqual(len(names), len(set(names)))
        self.assertNotIn("qualified-trades", names)
        self.assertNotIn("scratches", names)
        self.assertIn("new-positions", names)
        self.assertIn("losses", names)
        self.assertIn("how-trades-are-found", names)
        methodology = sync_discord_structure.GUIDES["how-trades-are-found"]
        self.assertLessEqual(len(methodology), 2000)
        self.assertIn("7–20 DTE", methodology)
        self.assertIn("$100 or less", methodology)
        self.assertIn("not a probability of winning", methodology)
        self.assertNotIn("ARCHIVE - LEGACY", sync_discord_structure.CATEGORY_ORDER)
        self.assertIn("TICKER • F", sync_discord_structure.DELETE_CATEGORIES)
        self.assertIn("TICKER • VALE", sync_discord_structure.DELETE_CATEGORIES)

    def test_upgrade_review_is_manual_not_background_polled(self) -> None:
        job_names = [job.name for job in engine.JOBS]
        self.assertNotIn("upgrade-request-reactions", job_names)
        self.assertIn("upgrade-review", sync_discord_structure.CHANNEL_STARTERS)

    def test_all_automatic_information_jobs_are_registered(self) -> None:
        job_names = {job.name for job in engine.JOBS}
        self.assertTrue({
            "full-options-scan",
            "position-tracker",
            "closed-position-cleanup",
            "discord-reporting",
            "examples-and-reviews",
            "dynamic-universe-refresh",
            "managed-ticker-information",
            "managed-ticker-news",
            "session-briefing",
            "health-snapshot",
            "outcome-learning",
            "discord-card-migration",
        }.issubset(job_names))

    def test_playbook_covers_every_scanner_play_type(self) -> None:
        keys = {item[0] for item in engine.PLAYBOOK_SPECS}
        self.assertEqual(
            keys,
            {
                "regular-call",
                "regular-put",
                "swing-call",
                "swing-put",
                "bull-put-spread",
                "bear-call-spread",
            },
        )
        card = engine.playbook_card_text(
            "Regular Long Call",
            "REGULAR",
            "call",
            [{
                "trade_id": "F-1",
                "ticker": "F",
                "play_type": "REGULAR",
                "call_or_put": "call",
                "outcome": "WIN",
                "realized_pl_dollars": "12",
            }],
            date(2026, 7, 31),
        )
        self.assertIn("Why this play is selected", card)
        self.assertIn("BUY TO OPEN", card)
        self.assertIn("SELL TO CLOSE", card)
        self.assertIn("Delta estimates", card)
        self.assertIn("F-1", card)
        background = {job.name for job in engine.JOBS if job.background}
        self.assertTrue({
            "full-options-scan",
            "position-tracker",
            "managed-ticker-information",
            "managed-ticker-news",
            "session-briefing",
            "discord-card-migration",
        }.issubset(background))

    def test_reporting_job_refreshes_all_closed_trade_views(self) -> None:
        rows = [{"trade_id": "F-1", "ticker": "F", "outcome": "WIN"}]
        state: dict = {}
        tracker = object()
        connection = object()
        with (
            patch.object(engine.ford_scan, "read_log", return_value=rows),
            patch.object(engine, "discord_tracker", return_value=tracker),
            patch.object(engine.ford_scan, "read_report_state", return_value=state),
            patch.object(engine.ford_scan, "update_performance_pages") as pages,
            patch.object(engine.ford_scan, "sync_reports") as reports,
            patch.object(engine.ford_scan, "write_report_state") as write_state,
            patch.object(engine, "outcome_learning_job") as learning,
            patch.object(engine, "store_observation"),
            patch.object(engine.trade_intelligence, "pending_rows", return_value=rows),
            patch.object(engine.trade_intelligence, "acknowledge_many", return_value=6),
        ):
            result = engine.discord_reporting_job(connection)
        pages.assert_called_once_with(tracker, state, rows)
        reports.assert_called_once()
        write_state.assert_called_once_with(state)
        learning.assert_called_once_with(connection)
        self.assertIn("1 closed indexed; 1 changed", result)

    def test_reporting_job_skips_unchanged_aggregate_cards(self) -> None:
        rows = [{"trade_id": "F-1", "ticker": "F", "outcome": "WIN"}]
        with (
            patch.object(engine.ford_scan, "read_log", return_value=rows),
            patch.object(engine, "discord_tracker", return_value=object()),
            patch.object(engine.ford_scan, "read_report_state", return_value={}),
            patch.object(engine.ford_scan, "update_performance_pages") as pages,
            patch.object(engine.ford_scan, "sync_reports") as reports,
            patch.object(engine.ford_scan, "write_report_state"),
            patch.object(engine, "outcome_learning_job") as learning,
            patch.object(engine, "store_observation"),
            patch.object(engine.trade_intelligence, "pending_rows", return_value=[]),
        ):
            result = engine.discord_reporting_job(object())
        pages.assert_not_called()
        learning.assert_not_called()
        reports.assert_called_once()
        self.assertIn("0 changed", result)

    def test_ticker_results_use_all_closed_trades(self) -> None:
        rows = [
            {"ticker": "F", "outcome": "WIN", "realized_pl_dollars": "20"},
            {"ticker": "F", "outcome": "LOSS", "realized_pl_dollars": "-5"},
            {"ticker": "NU", "outcome": "LOSS", "realized_pl_dollars": "-10"},
        ]
        content = ford_scan.format_ticker_results(rows)
        self.assertIn("**F**", content)
        self.assertIn("1W / 1L", content)
        self.assertIn("**NU**", content)

    def test_weekly_report_marks_live_and_final(self) -> None:
        report_date = date(2026, 7, 31)
        self.assertIn("**Status:** LIVE", ford_scan.format_weekly_report([], report_date))
        self.assertIn(
            "**Status:** FINAL",
            ford_scan.format_weekly_report([], report_date, final=True),
        )
    def test_closed_position_cleanup_reconciles_without_market_scan(self) -> None:
        closed = [{"trade_id": "NU-009", "outcome": "LOSS"}]
        state: dict = {}
        tracker = object()
        connection = object()
        with (
            patch.object(engine.ford_scan, "read_log", return_value=closed),
            patch.object(engine.ford_scan, "closed_rows", return_value=closed),
            patch.object(engine, "discord_tracker", return_value=tracker),
            patch.object(engine.ford_scan, "read_report_state", return_value=state),
            patch.object(
                engine.ford_scan,
                "sync_all_trade_journals",
                return_value={"created": 0, "refreshed": 0, "closed_reviews": 1},
            ),
            patch.object(
                engine.ford_scan, "sync_closed_result_channels", return_value=0
            ) as sync,
            patch.object(engine.ford_scan, "write_log"),
            patch.object(engine.ford_scan, "write_report_state") as write_state,
            patch.object(engine, "store_observation") as observe,
            patch.object(engine.trade_intelligence, "record_event"),
            patch.object(engine.trade_intelligence, "pending_rows", return_value=closed),
        ):
            result = engine.closed_position_cleanup_job(connection)
        sync.assert_called_once_with(closed, tracker, state)
        write_state.assert_called_once_with(state)
        observe.assert_called_once()
        self.assertIn("1 closed indexed; 1 changed", result)

    def test_multi_ticker_scan_publishes_each_ticker_and_syncs_once(self) -> None:
        calls: list[tuple[str, bool]] = []

        def scanner(*, publish_shared: bool = True) -> int:
            calls.append((ford_scan.TICKER, publish_shared))
            return 0

        with patch.object(multi_ticker_scan.ford_scan, "main", scanner):
            result = multi_ticker_scan.main(["BAC", "CCL", "RIVN"])
        self.assertEqual(result, 0)
        self.assertEqual(multi_ticker_scan.LAST_RESULTS, {
            "BAC": 0,
            "CCL": 0,
            "RIVN": 0,
        })
        self.assertEqual(calls, [
            ("BAC", False),
            ("CCL", False),
            ("RIVN", True),
        ])

    def test_scanner_outputs_use_consolidated_channels(self) -> None:
        self.assertEqual(ford_scan.CHANNEL_NAMES["qualified"], "new-positions")
        self.assertEqual(ford_scan.CHANNEL_NAMES["scratches"], "losses")
        self.assertEqual(ford_scan.CHANNEL_NAMES["charts"], "charts-and-levels")
        self.assertEqual(ford_scan.CHANNEL_NAMES["universe_watch"], "universe-watch")
        self.assertEqual(ford_scan.CHANNEL_NAMES["premarket"], "premarket")

    def test_manual_full_scan_runs_every_local_section_in_order(self) -> None:
        original = engine.DB_PATH
        calls: list[str] = []

        def callback(name: str):
            def run(_connection):
                calls.append(name)
                return f"{name} complete"
            return run

        with tempfile.TemporaryDirectory() as temp:
            engine.DB_PATH = Path(temp) / "manual.db"
            with (
                patch.object(engine, "provider_event_job", callback("events")),
                patch.object(engine, "universe_refresh_job", callback("discovery")),
                patch.object(engine, "manual_intelligence_job", callback("intelligence")),
                patch.object(engine, "manual_options_scan_job", callback("options")),
                patch.object(engine, "position_tracker_job", callback("positions")),
                patch.object(engine, "status_job", callback("health")),
            ):
                result = engine.run_manual_scan("all")
        engine.DB_PATH = original
        self.assertEqual(
            calls,
            ["events", "discovery", "intelligence", "options", "positions", "health"],
        )
        self.assertEqual(result.count("**"), 12)
        self.assertNotIn("ERROR", result)

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
        owner_commands = register_discord_commands.OWNER_ONLY_COMMANDS
        definitions = {
            command["name"]: command
            for command in register_discord_commands.COMMANDS
        }
        for name in owner_commands:
            self.assertEqual(definitions[name]["default_member_permissions"], "0")
        self.assertTrue(
            {"filter-set", "ticker-pause", "ticker-resume", "scan-now"}.issubset(
                owner_commands
            )
        )
        self.assertEqual(
            {
                name
                for name, definition in definitions.items()
                if definition.get("default_member_permissions") == "0"
            },
            owner_commands,
        )

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
            # initialize() no longer force-seeds from config - VALE needs a
            # real source to actually be active, same as in production.
            dynamic_universe.seed_universe()
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

    def test_ticker_context_blocks_other_ticker_trade_and_contract_data(self) -> None:
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

    def test_any_member_can_add_ticker_to_shared_universe_without_desk(self) -> None:
        interaction = {
            "member": {"user": {"id": "member-123"}},
            "data": {"options": [{"name": "ticker", "value": "vale"}]},
        }
        with (
            patch.object(discord_command_bot.ford_scan, "get_quote", return_value={"last": 14.77}),
            patch.object(discord_command_bot.ford_scan, "get_expirations", return_value=["2026-08-07"]),
            patch.object(discord_command_bot.dynamic_universe, "upsert_candidates") as upsert,
            patch.object(discord_command_bot.ticker_registry, "save") as save,
        ):
            reply = discord_command_bot.ticker_add_reply(interaction)
        self.assertIn("shared scanner universe", reply)
        self.assertIn("No ticker category", reply)
        upsert.assert_called_once()
        save.assert_called_once_with(
            "VALE",
            status="ACTIVE",
            note="Added to the shared scanner universe through Discord",
        )

    def test_routed_closed_trade_is_removed_from_held_positions(self) -> None:
        calls: list[tuple[str, str, str, str]] = []

        class Tracker:
            ready = True

            def delete_trade_message(self, *args: str) -> None:
                calls.append(args)

        row = {
            "trade_id": "VALE-20260731-001",
            "ticker": "VALE",
            "outcome": "WIN",
            "closed_at": "2026-07-31T13:00:00-05:00",
        }
        state = {"routed_closed_trade_ids": [row["trade_id"]]}
        updated = ford_scan.sync_closed_result_channels([row], Tracker(), state)
        self.assertEqual(updated, 0)
        self.assertEqual(
            calls,
            [
                ("updates", state, "position", "VALE-20260731-001"),
                ("exit", state, "exit", "VALE-20260731-001"),
            ],
        )

    def test_delete_trade_message_finds_legacy_card_without_state(self) -> None:
        tracker = ford_scan.DiscordTracker("token", "guild")
        tracker.ready = True
        tracker.channels["updates"] = "held-channel"
        requests: list[tuple[str, str]] = []

        def request(method: str, path: str, payload=None):
            requests.append((method, path))
            if method == "GET":
                return [
                    {
                        "id": "legacy-message",
                        "author": {"bot": True},
                        "content": "",
                        "embeds": [{"title": "VALE-20260731-001 | LOSS"}],
                    }
                ]
            return {}

        tracker._request = request
        state: dict = {}
        tracker.delete_trade_message(
            "updates", state, "position", "VALE-20260731-001"
        )
        self.assertIn(
            ("DELETE", "/channels/held-channel/messages/legacy-message"), requests
        )
        self.assertEqual(state["messages"], {})

    def test_singleton_message_updates_newest_and_removes_older_duplicates(self) -> None:
        tracker = ford_scan.DiscordTracker("token", "guild")
        requests: list[tuple[str, str]] = []

        def request(method: str, path: str, payload=None):
            requests.append((method, path))
            if method == "GET":
                return [
                    {
                        "id": "newest",
                        "author": {"bot": True},
                        "embeds": [{"title": "Tradysquids"}],
                    },
                    {
                        "id": "older",
                        "author": {"bot": True},
                        "embeds": [{"title": "Tradysquids"}],
                    },
                ]
            return {}

        tracker._request = request
        message_id, removed = tracker.upsert_singleton_message(
            "welcome-channel", "# Tradysquids\nCanonical guide", "Tradysquids"
        )

        self.assertEqual(message_id, "newest")
        self.assertEqual(removed, 1)
        self.assertIn(
            ("PATCH", "/channels/welcome-channel/messages/newest"), requests
        )
        self.assertIn(
            ("DELETE", "/channels/welcome-channel/messages/older"), requests
        )

    def test_closed_trade_journal_backfill_is_canonical_and_idempotent(self) -> None:
        calls: list[tuple] = []

        class Tracker:
            ready = True

            def create_trade_thread(self, row, status):
                calls.append(("create", row["trade_id"], status))
                row["discord_thread_id"] = "thread-1"
                return "thread-1"

            def _request(self, method, path, payload=None):
                calls.append((method, path))
                return {}

            def upsert_singleton_message(self, channel_id, content, token):
                calls.append(("singleton", channel_id, token))
                return "review-1", 0

            def set_thread_status(self, thread_id, status, archive=False):
                calls.append(("status", thread_id, status, archive))

        row = {
            "trade_id": "F-20260731-100",
            "ticker": "F",
            "play_type": "REGULAR",
            "call_or_put": "call",
            "strike": "15",
            "expiration": "2026-08-07",
            "entry_price": "0.25",
            "outcome": "WIN",
            "realized_pl_dollars": "5",
            "pct_gain_loss": "20",
            "last_signal": "TAKE PROFIT",
        }
        result = ford_scan.sync_all_trade_journals([row], Tracker())
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["closed_reviews"], 1)
        self.assertIn(("singleton", "thread-1", "F #100 · WIN"), calls)
        self.assertEqual(row["discord_format_version"], ford_scan.DISCORD_FORMAT_VERSION)

    def test_new_close_is_not_posted_back_to_held_positions(self) -> None:
        calls: list[tuple] = []

        class Tracker:
            ready = True

            def upsert_trade_result(self, *args):
                calls.append(("result", *args))

            def delete_trade_message(self, *args):
                calls.append(("delete", *args))

        row = {
            "trade_id": "F-20260731-002",
            "ticker": "F",
            "outcome": "WIN",
            "closed_at": "2026-07-31T14:00:00-05:00",
            "pct_gain_loss": "10",
        }
        state: dict = {}
        self.assertEqual(ford_scan.sync_closed_result_channels([row], Tracker(), state), 1)
        self.assertEqual([call[0] for call in calls], ["result", "delete", "delete"])

    def test_entry_snapshot_is_sent_to_trade_thread_not_chart_channel(self) -> None:
        calls: list[tuple[str, str]] = []

        class Tracker:
            ready = True

            def create_trade_thread(self, row: dict[str, str], status: str) -> str:
                row["discord_thread_id"] = "thread-1"
                return "thread-1"

            def send_thread_file(self, thread_id: str, path: Path, *, content: str):
                calls.append((thread_id, content))

            def send_channel_file(self, *args, **kwargs):
                self.fail("entry snapshot must not use a shared chart channel")

        row = {
            "trade_id": "VALE-20260731-001",
            "ticker": "VALE",
            "play_type": "REGULAR",
            "strike": "15",
            "entry_price": "0.25",
            "discord_thread_id": "",
        }
        with tempfile.TemporaryDirectory() as temp:
            image = Path(temp) / "entry.png"
            image.write_bytes(b"png")
            with (
                patch.object(ford_scan, "sync_open_trade_cards"),
                patch.object(ford_scan, "build_trade_snapshot", return_value=image),
                patch.object(ford_scan.trade_intelligence, "register_snapshot", return_value=True),
                patch.object(ford_scan.trade_intelligence, "record_event"),
            ):
                ford_scan.post_new_trade(row, Tracker(), {})
        self.assertEqual(calls[0][0], "thread-1")
        self.assertIn("5-minute underlying session", calls[0][1])

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

    def test_stale_running_jobs_are_marked_interrupted(self) -> None:
        original = engine.DB_PATH
        with tempfile.TemporaryDirectory() as temp:
            engine.DB_PATH = Path(temp) / "scheduler.db"
            connection = engine.connect_db()
            connection.execute(
                "INSERT INTO job_runs(job_name, started_at, status) VALUES (?, ?, ?)",
                ("stale-job", engine.iso_now(), "RUNNING"),
            )
            connection.commit()
            self.assertEqual(engine.recover_interrupted_jobs(connection), 1)
            row = connection.execute(
                "SELECT status FROM job_runs WHERE job_name='stale-job'"
            ).fetchone()
            self.assertEqual(row["status"], "INTERRUPTED")
            connection.close()
        engine.DB_PATH = original

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
            # initialize() no longer force-seeds - explicitly seed here so this
            # test keeps proving exclude_symbols filtering works, independent
            # of whether anything auto-populates the universe.
            dynamic_universe.seed_universe()
            dynamic_universe.initialize()
            self.assertEqual(set(dynamic_universe.active_symbols()), {"F", "VALE"})
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_initialize_does_not_force_include_hardcoded_seed_symbols(self) -> None:
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            config = Path(temp) / "universe.json"
            config.write_text(
                """
                {
                  "version": 3,
                  "seed_symbols": ["F", "AAL", "AMD"],
                  "exclude_symbols": [],
                  "max_active_symbols": 25
                }
                """,
                encoding="utf-8",
            )
            dynamic_universe.CONFIG_PATH = config
            # Nothing has nominated F/AAL/AMD through a real source (owner add,
            # member add, TradingView, screener) - initialize() must not
            # resurrect them just because they're sitting in the config file.
            dynamic_universe.initialize()
            self.assertEqual(dynamic_universe.active_symbols(), [])
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_stale_time_limited_candidate_can_be_outranked_before_hard_expiry(
        self,
    ) -> None:
        original_db = dynamic_universe.DB_PATH
        original_config = dynamic_universe.CONFIG_PATH
        with tempfile.TemporaryDirectory() as temp:
            dynamic_universe.DB_PATH = Path(temp) / "universe.db"
            config = Path(temp) / "universe.json"
            config.write_text(
                '{"seed_symbols":[],"exclude_symbols":[],"max_active_symbols":1}',
                encoding="utf-8",
            )
            dynamic_universe.CONFIG_PATH = config
            dynamic_universe.upsert_candidates([
                dynamic_universe.Candidate(
                    "F", "tradingview", score=100, ttl_minutes=240
                )
            ])
            # Simulate F being 75% of the way through its 4-hour window -
            # still technically not expired, but should have decayed to
            # roughly a quarter of its original score by now.
            now = datetime.now().astimezone()
            stale_updated = (now - timedelta(minutes=180)).isoformat(timespec="seconds")
            stale_expires = (now + timedelta(minutes=60)).isoformat(timespec="seconds")
            connection = dynamic_universe.connect()
            connection.execute(
                "UPDATE universe SET updated_at=?, expires_at=? WHERE symbol='F'",
                (stale_updated, stale_expires),
            )
            connection.commit()
            connection.close()
            # A fresh hit with a much lower raw score should still win the
            # single available slot, because F has decayed well below it.
            dynamic_universe.upsert_candidates([
                dynamic_universe.Candidate(
                    "VALE", "tradingview", score=30, ttl_minutes=240
                )
            ])
            self.assertEqual(dynamic_universe.active_symbols(), ["VALE"])
        dynamic_universe.DB_PATH = original_db
        dynamic_universe.CONFIG_PATH = original_config

    def test_effective_score_decays_linearly_toward_expiry(self) -> None:
        now = datetime.now().astimezone()
        started = now - timedelta(minutes=180)
        expires = now + timedelta(minutes=60)
        decayed = dynamic_universe._effective_score(
            100,
            started.isoformat(timespec="seconds"),
            expires.isoformat(timespec="seconds"),
            now,
        )
        # 180 of 240 total minutes elapsed -> 25% of the score should remain.
        self.assertAlmostEqual(decayed, 25.0, delta=1.0)
        permanent = dynamic_universe._effective_score(
            200, started.isoformat(timespec="seconds"), None, now
        )
        self.assertEqual(permanent, 200)

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
        with patch.object(ford_scan.trade_intelligence, "record_event"):
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
        # This position already ran up to a +30% peak in an earlier cycle
        # (max_favorable_pct), so the new trailing-stop logic is what should
        # fire here, not the old flat +20% cap - the incoming quote pulls it
        # back to +20%, breaching the 8pt giveback allowed from that peak.
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
                    "max_favorable_pct": "30",
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
                patch.object(ford_scan.trade_intelligence, "record_event"),
            ):
                engine._stream_quote_event(
                    {
                        "type": "quote",
                        "symbol": "VALE260821C00015000",
                        "bid": 0.60,
                        "ask": 0.62,
                    }
                )
            closed = ford_scan.read_log()[0]
            self.assertEqual(closed["outcome"], "WIN")
            self.assertEqual(closed["last_signal"], "TAKE PROFIT")
            route_close.assert_called_once()
        ford_scan.LOG_PATH = original_log

    def test_trade_log_writes_atomically_and_rejects_zero_byte_history(self) -> None:
        original_log = ford_scan.LOG_PATH
        original_state = ford_scan.STATE_DIR
        try:
            with tempfile.TemporaryDirectory() as temp:
                ford_scan.STATE_DIR = Path(temp)
                ford_scan.LOG_PATH = Path(temp) / "plays.csv"
                row = {field: "" for field in ford_scan.LOG_HEADER}
                row.update({"trade_id": "TEST-001", "ticker": "TEST", "outcome": "OPEN"})
                ford_scan.write_log([row])
                self.assertEqual(ford_scan.read_log()[0]["trade_id"], "TEST-001")
                self.assertEqual(list(Path(temp).glob("*.tmp")), [])
                ford_scan.LOG_PATH.write_bytes(b"")
                with self.assertRaisesRegex(RuntimeError, "is empty"):
                    ford_scan.read_log()
        finally:
            ford_scan.LOG_PATH = original_log
            ford_scan.STATE_DIR = original_state

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
