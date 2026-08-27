"""Regression guard for the retired Discord rivalry layout."""

import sync_discord_structure as structure


def test_rivalry_layout_is_explicitly_retired_from_every_future_sync():
    assert "blacktide-vs-claude" in structure.DELETE_CHANNELS
    assert "RIVALRY" in structure.DELETE_CATEGORIES
    assert "RIVALRY" not in structure.CATEGORY_ORDER
    assert all(channel.name != "blacktide-vs-claude" for channel in structure.CHANNELS)


def test_welcome_guide_does_not_advertise_retired_rivalry():
    welcome = structure.GUIDES["welcome"]
    assert "blacktide-vs-claude" not in welcome
    assert "vs BLACKTIDE" not in welcome
