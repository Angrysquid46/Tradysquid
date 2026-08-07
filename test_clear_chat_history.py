"""Tests for /clear-chat-history: deletes bot-authored command-reply clutter
from #general-chat while leaving pinned messages and anything a real person
posted untouched. Owner-gated with a typed confirm string, same pattern as
/reset-trading-data."""

from __future__ import annotations

from unittest import mock

import discord_command_bot as bot
import ford_scan


def test_preserve_pinned_skips_pinned_bot_messages_but_deletes_the_rest():
    tracker = ford_scan.DiscordTracker("fake-token", "fake-guild")
    tracker.ready = True
    tracker.channels = {"general_chat": "c-general"}
    calls: list[tuple[str, str]] = []
    remaining = [
        {"id": "pinned-welcome-1", "author": {"bot": True}},
        {"id": "old-scan-reply-1", "author": {"bot": True}},
        {"id": "human-msg-1", "author": {"bot": False}},
    ]

    def fake_request(method, path, *a, **k):
        calls.append((method, path))
        if method == "GET" and path == "/channels/c-general/pins":
            return [{"id": "pinned-welcome-1"}]
        if method == "GET" and path.startswith("/channels/c-general/messages"):
            return [] if "before=" in path else list(remaining)
        if method == "DELETE":
            message_id = path.rsplit("/", 1)[-1]
            remaining[:] = [item for item in remaining if item["id"] != message_id]
        return {}

    with mock.patch.object(ford_scan.DiscordTracker, "_request", side_effect=fake_request):
        removed = tracker.wipe_channel_messages("general_chat", preserve_pinned=True)

    assert removed == 1
    assert ("DELETE", "/channels/c-general/messages/old-scan-reply-1") in calls
    assert ("DELETE", "/channels/c-general/messages/pinned-welcome-1") not in calls
    assert ("DELETE", "/channels/c-general/messages/human-msg-1") not in calls


def test_without_preserve_pinned_a_pinned_bot_message_is_still_deleted():
    # Confirms the new keyword is opt-in and doesn't change existing callers
    # (reset_all_trade_data) that never asked for pin-awareness.
    tracker = ford_scan.DiscordTracker("fake-token", "fake-guild")
    tracker.ready = True
    tracker.channels = {"general_chat": "c-general"}
    calls: list[tuple[str, str]] = []
    remaining = [{"id": "pinned-welcome-1", "author": {"bot": True}}]

    def fake_request(method, path, *a, **k):
        calls.append((method, path))
        if method == "GET" and path.startswith("/channels/c-general/messages"):
            return [] if "before=" in path else list(remaining)
        if method == "DELETE":
            message_id = path.rsplit("/", 1)[-1]
            remaining[:] = [item for item in remaining if item["id"] != message_id]
        return {}

    with mock.patch.object(ford_scan.DiscordTracker, "_request", side_effect=fake_request):
        removed = tracker.wipe_channel_messages("general_chat")

    assert removed == 1
    assert ("GET", "/channels/c-general/pins") not in calls
    assert ("DELETE", "/channels/c-general/messages/pinned-welcome-1") in calls


def test_wrong_confirm_string_refuses_and_deletes_nothing():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {
        "member": {"user": {"id": "owner-1"}},
        "data": {"options": [{"name": "confirm", "value": "clear"}]},  # wrong case
    }
    with mock.patch.object(ford_scan.DiscordTracker, "_request") as request:
        try:
            bot.clear_chat_history_reply(interaction)
            assert False, "should have raised"
        except ValueError as exc:
            assert "CLEAR" in str(exc)
        request.assert_not_called()


def test_non_owner_cannot_clear_even_with_correct_confirm_string():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {
        "member": {"user": {"id": "someone-else"}},
        "data": {"options": [{"name": "confirm", "value": "CLEAR"}]},
    }
    with mock.patch.object(ford_scan.DiscordTracker, "_request") as request:
        try:
            bot.clear_chat_history_reply(interaction)
            assert False, "should have raised"
        except PermissionError:
            pass
        request.assert_not_called()


def test_correct_confirm_and_owner_wipes_general_chat_preserving_pins():
    bot.ALLOWED_USER_ID = "owner-1"
    interaction = {
        "member": {"user": {"id": "owner-1"}},
        "data": {"options": [{"name": "confirm", "value": "CLEAR"}]},
    }
    with mock.patch.object(
        ford_scan.DiscordTracker, "wipe_channel_messages", return_value=7
    ) as wipe:
        reply = bot.clear_chat_history_reply(interaction)
    wipe.assert_called_once_with("general_chat", preserve_pinned=True)
    assert "7" in reply
    assert "Pinned" in reply
