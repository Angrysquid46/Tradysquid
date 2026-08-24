from __future__ import annotations
from unittest import mock

import discord_transport as spy_scanner
import sync_discord_cards


def _tracker():
    return spy_scanner.DiscordTracker("fake-token", "fake-guild")


def test_message_channels_excludes_the_evolve_bot_category():
    """evolve_bot owns its own Discord presence (category "SPY_EVOLVE")
    and deliberately posts plain content that it upserts in place - a
    migration PATCH from this main-system tool landing between two of
    its own upserts visually split one message into what looked like
    two things. Owner: "still other things so it's not 1 card"."""
    guild_channels = [
        {"id": "cat-main", "type": 4, "name": "SPY 0DTE 1-MINUTE"},
        {"id": "chan-main", "type": 0, "name": "new-positions", "parent_id": "cat-main"},
        {"id": "cat-evolve", "type": 4, "name": "SPY_EVOLVE"},
        {"id": "chan-evolve-trades", "type": 0, "name": "evolve-trades", "parent_id": "cat-evolve"},
        {"id": "chan-evolve-dashboard", "type": 0, "name": "evolve-dashboard", "parent_id": "cat-evolve"},
    ]
    tracker = _tracker()
    with (
        mock.patch.object(tracker, "_request", side_effect=[guild_channels, {}]) as fake_request,
    ):
        channels = sync_discord_cards._message_channels(tracker)

    channel_ids = {item["id"] for item in channels}
    assert "chan-main" in channel_ids
    assert "chan-evolve-trades" not in channel_ids
    assert "chan-evolve-dashboard" not in channel_ids
    assert fake_request.call_count == 2


def test_message_channels_excludes_evolve_bot_threads_too():
    guild_channels = [
        {"id": "cat-evolve", "type": 4, "name": "SPY_EVOLVE"},
        {"id": "chan-evolve-trades", "type": 0, "name": "evolve-trades", "parent_id": "cat-evolve"},
    ]
    active_threads = {
        "threads": [
            {"id": "thread-evolve", "type": 11, "parent_id": "chan-evolve-trades"},
            {"id": "thread-main", "type": 11, "parent_id": "some-other-channel"},
        ]
    }
    tracker = _tracker()
    with mock.patch.object(tracker, "_request", side_effect=[guild_channels, active_threads]):
        channels = sync_discord_cards._message_channels(tracker)

    channel_ids = {item["id"] for item in channels}
    assert "thread-main" in channel_ids
    assert "thread-evolve" not in channel_ids
