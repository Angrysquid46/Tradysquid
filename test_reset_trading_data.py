"""Tests for the owner-triggered trade-data reset. This is the one genuinely
destructive action in the system, so it gets tested more thoroughly than
most: the confirm-string gate, the archive-or-not choice, and the actual
clear all get verified directly against real files, not just mocked calls."""

from __future__ import annotations

import csv
import tempfile
from pathlib import Path
from unittest import mock

import discord_command_bot as bot
import spy_scanner


def _row(trade_id: str, thread_id: str = "", outcome: str = "OPEN") -> dict[str, str]:
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({"trade_id": trade_id, "discord_thread_id": thread_id, "outcome": outcome})
    return row


def _with_temp_paths():
    class _Swap:
        def __enter__(self):
            self.original_log = spy_scanner.LOG_PATH
            self.original_state_dir = spy_scanner.STATE_DIR
            self.original_report_state = spy_scanner.REPORT_STATE_PATH
            self.tmp = tempfile.TemporaryDirectory()
            root = Path(self.tmp.name)
            spy_scanner.LOG_PATH = root / "plays.csv"
            spy_scanner.STATE_DIR = root / "state"
            # REPORT_STATE_PATH is computed once from STATE_DIR at import
            # time, so it does not follow the STATE_DIR swap above on its
            # own - without this, tests in this file share and pollute one
            # real state file on disk instead of getting a clean, isolated
            # one each, which caused a real (if confusing) flaky failure.
            spy_scanner.REPORT_STATE_PATH = root / "state" / "discord-report-state.json"
            return root

        def __exit__(self, *exc):
            spy_scanner.LOG_PATH = self.original_log
            spy_scanner.STATE_DIR = self.original_state_dir
            spy_scanner.REPORT_STATE_PATH = self.original_report_state
            self.tmp.cleanup()

    return _Swap()


def test_reset_with_archive_saves_a_backup_before_clearing():
    with _with_temp_paths():
        spy_scanner.write_log([_row("T1"), _row("T2")])
        tracker = spy_scanner.DiscordTracker("", "")
        result = spy_scanner.reset_all_trade_data(tracker, archive=True)

        assert result["cleared_trades"] == 2
        assert result["backup_path"] is not None
        backup = Path(result["backup_path"])
        assert backup.exists()
        with backup.open() as handle:
            saved_ids = {row["trade_id"] for row in csv.DictReader(handle)}
        assert saved_ids == {"T1", "T2"}
        # The live log must actually be empty now, not just report a count.
        assert spy_scanner.read_log() == []


def test_reset_without_archive_saves_nothing():
    with _with_temp_paths() as root:
        spy_scanner.write_log([_row("T1")])
        tracker = spy_scanner.DiscordTracker("", "")
        result = spy_scanner.reset_all_trade_data(tracker, archive=False)

        assert result["backup_path"] is None
        assert not (root / "state" / "archive").exists()
        assert spy_scanner.read_log() == []


def test_reset_deletes_every_thread_in_the_channel_directly():
    # Channel-driven, not log-driven: this proves the exact bug just
    # reported - a thread with NO matching row in the current log (already
    # cleared by an earlier, less complete reset attempt) still gets found
    # and deleted, because this asks Discord what's actually there instead
    # of walking the log's trade IDs.
    with _with_temp_paths():
        spy_scanner.write_log([_row("T1", thread_id="thread-1", outcome="OPEN")])
        tracker = spy_scanner.DiscordTracker("fake-token", "fake-guild")
        tracker.ready = True
        tracker.channels = {"forum": "journal-channel-id"}
        calls: list[tuple[str, str]] = []
        # wipe_channel_threads retries up to 5 passes specifically to
        # survive a burst hitting a rate limit or a thread created mid-wipe
        # - a real Discord list call reflects real deletions, so a static
        # mock that keeps returning already-deleted threads makes every
        # pass "find" them again and overcounts (a real bug this test once
        # had: asserted deleted_threads == 3 but got 15, exactly 5 passes x
        # 3 threads - the reset code was correct, the mock wasn't
        # simulating deletion). Track live thread ids explicitly instead.
        live_threads = {"thread-1", "orphaned-thread-999", "unrelated-thread-1", "archived-thread-42"}

        def fake_request(method, path, *a, **k):
            calls.append((method, path))
            if method == "DELETE" and path.startswith("/channels/"):
                live_threads.discard(path.rsplit("/", 1)[-1])
                return {}
            if path == "/guilds/fake-guild/threads/active":
                active = [
                    {"id": "thread-1", "parent_id": "journal-channel-id"},
                    {"id": "orphaned-thread-999", "parent_id": "journal-channel-id"},
                    # A different forum channel's active thread - must NOT
                    # be touched, since the guild-wide endpoint returns
                    # threads from every channel, not just this one.
                    {"id": "unrelated-thread-1", "parent_id": "some-other-channel"},
                ]
                return {"threads": [t for t in active if t["id"] in live_threads]}
            if path.startswith("/channels/journal-channel-id/threads/archived/public"):
                if "archived-thread-42" in live_threads:
                    return {"threads": [{"id": "archived-thread-42"}], "has_more": False}
                return {"threads": [], "has_more": False}
            return None

        with mock.patch.object(spy_scanner.DiscordTracker, "_request", side_effect=fake_request):
            result = spy_scanner.reset_all_trade_data(tracker, archive=False)

        assert result["deleted_threads"] == 3
        assert ("DELETE", "/channels/thread-1") in calls
        # The orphaned thread - no row for it anywhere in the current log -
        # still gets deleted, because this never depended on the log to
        # find it in the first place.
        assert ("DELETE", "/channels/orphaned-thread-999") in calls
        assert ("DELETE", "/channels/archived-thread-42") in calls
        assert ("DELETE", "/channels/unrelated-thread-1") not in calls


def test_reset_wipes_channel_messages_directly_not_by_trade_id():
    with _with_temp_paths():
        spy_scanner.write_log([])
        tracker = spy_scanner.DiscordTracker("fake-token", "fake-guild")
        tracker.ready = True
        tracker.channels = {
            "qualified": "c-qualified", "entry": "c-entry", "updates": "c-updates",
            "wins": "c-wins", "losses": "c-losses", "scratches": "c-scratches",
            "expired": "c-expired",
        }
        calls: list[tuple[str, str]] = []

        def fake_request(method, path, *a, **k):
            calls.append((method, path))
            if method == "GET" and path.startswith("/channels/c-wins/messages"):
                if "before=" in path:
                    return []
                # One bot card with no corresponding log row at all - the
                # exact orphaned-message scenario just reported - plus one
                # message from a real person, which must survive.
                return [
                    {"id": "orphan-card-1", "author": {"bot": True}},
                    {"id": "human-msg-1", "author": {"bot": False}},
                ]
            if method == "GET":
                return []
            return {}

        with mock.patch.object(spy_scanner.DiscordTracker, "_request", side_effect=fake_request):
            spy_scanner.reset_all_trade_data(tracker, archive=False)

        assert ("DELETE", "/channels/c-wins/messages/orphan-card-1") in calls
        assert ("DELETE", "/channels/c-wins/messages/human-msg-1") not in calls


def test_reset_on_an_already_empty_log_does_not_crash_or_write_a_backup():
    with _with_temp_paths() as root:
        spy_scanner.write_log([])
        tracker = spy_scanner.DiscordTracker("", "")
        result = spy_scanner.reset_all_trade_data(tracker, archive=True)

        assert result["cleared_trades"] == 0
        assert result["deleted_threads"] == 0
        assert result["backup_path"] is None
        assert not (root / "state" / "archive").exists()


def test_wrong_confirm_string_refuses_and_never_touches_data():
    with _with_temp_paths():
        spy_scanner.write_log([_row("T1")])
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = {
            "member": {"user": {"id": "owner-1"}},
            "data": {"options": [
                {"name": "confirm", "value": "reset"},  # wrong case, must be exact
                {"name": "archive", "value": True},
            ]},
        }
        try:
            bot.reset_trading_data_reply(interaction)
            assert False, "should have raised"
        except ValueError as exc:
            assert "RESET" in str(exc)
        # The whole point of the gate: nothing was touched.
        assert len(spy_scanner.read_log()) == 1


def test_non_owner_cannot_reset_even_with_correct_confirm_string():
    with _with_temp_paths():
        spy_scanner.write_log([_row("T1")])
        bot.ALLOWED_USER_ID = "owner-1"
        interaction = {
            "member": {"user": {"id": "someone-else"}},
            "data": {"options": [
                {"name": "confirm", "value": "RESET"},
                {"name": "archive", "value": True},
            ]},
        }
        try:
            bot.reset_trading_data_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        assert len(spy_scanner.read_log()) == 1


def test_reset_refreshes_every_summary_dashboard_immediately():
    with _with_temp_paths():
        spy_scanner.write_log([])
        calls = []

        class FakeTracker:
            ready = True

            def wipe_channel_threads(self, logical_name):
                calls.append(("wipe_threads", logical_name))
                return 0

            def wipe_channel_messages(self, logical_name):
                calls.append(("wipe_messages", logical_name))
                return 0

            def upsert_channel_message(self, logical_name, state, token, content, search_token=""):
                calls.append(("refresh_dashboard", logical_name))
                return "msg-1", 0

        spy_scanner.reset_all_trade_data(FakeTracker(), archive=False)

        # Every live-trading-desk channel gets wiped directly, not driven
        # by trade IDs still present in the log.
        wiped = {c[1] for c in calls if c[0] in ("wipe_threads", "wipe_messages")}
        # Live cards moved out of the single shared #held-positions channel
        # into one channel per strategy, so a reset has to wipe each of
        # those too - otherwise it reports success while leaving a stale
        # HOLD card in every strategy channel.
        held = {k for k in spy_scanner.CHANNEL_NAMES if k.startswith("held_")}
        assert held, "no per-strategy held channels are registered"
        assert wiped == {
            "forum", "qualified", "entry",
            "wins", "losses", "scratches", "expired",
        } | held

        # refresh_all_summary_dashboards only owns ticker_results and
        # wins/losses/scratches now - performance_1m/results_1m/
        # performance_5m/results_5m are owned exclusively by
        # performance_reconciliation.py's sync_reports (installed as
        # spy_scanner.sync_reports) to avoid the "two systems fighting over
        # the same cards" problem that posting them from both places would
        # reintroduce. Those four zero out on the next scheduled sync_reports
        # cycle instead, once the ledger signature changes.
        refreshed = {c[1] for c in calls if c[0] == "refresh_dashboard"}
        assert refreshed == {
            "ticker_results",
            "wins",
            "losses",
            "scratches",
        }
