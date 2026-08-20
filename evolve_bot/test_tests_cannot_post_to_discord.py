"""A test run must never reach the real Discord server.

evolve's unit fixtures use trade_id "T1" with entry 0.50 / exit 0.20. Those
cards were found sitting in the live #evolve-losses channel showing a fake
$970 balance and blank strike/expiration - at a glance indistinguishable
from a real losing trade, and they made the owner believe evolve was
trading and mis-tracking its balance when in fact it had not traded since
2026-08-14 and its real balance was $478.

Having credentials is not evidence that posting is wanted: .env is loaded
in this process for the real bot, so every test inherits a working token.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import discord_post


def test_posting_is_disabled_while_pytest_is_running(monkeypatch):
    """THE regression - this is how T1 cards reached #evolve-losses."""
    monkeypatch.setattr(discord_post, "BOT_TOKEN", "real-looking-token")
    monkeypatch.setattr(discord_post, "GUILD_ID", "123456789")
    monkeypatch.delenv("EVOLVE_ALLOW_TEST_DISCORD", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "some::test")
    assert discord_post.enabled() is False, (
        "a test run can post to the live server - this is exactly how the "
        "fake T1 cards ended up in #evolve-losses"
    )


def test_a_test_can_opt_in_deliberately(monkeypatch):
    monkeypatch.setattr(discord_post, "BOT_TOKEN", "real-looking-token")
    monkeypatch.setattr(discord_post, "GUILD_ID", "123456789")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "some::test")
    monkeypatch.setenv("EVOLVE_ALLOW_TEST_DISCORD", "1")
    assert discord_post.enabled() is True


def test_post_message_returns_none_instead_of_posting(monkeypatch):
    """The guard must stop the request, not merely be advisory."""
    monkeypatch.setattr(discord_post, "BOT_TOKEN", "real-looking-token")
    monkeypatch.setattr(discord_post, "GUILD_ID", "123456789")
    monkeypatch.delenv("EVOLVE_ALLOW_TEST_DISCORD", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "some::test")

    def explode(*args, **kwargs):
        raise AssertionError("a live Discord request was attempted from a test")

    monkeypatch.setattr(discord_post, "_request", explode)
    assert discord_post.post_message("losses", "T1 fake card") is None


def test_the_guard_does_not_disable_the_real_bot(monkeypatch):
    """Outside pytest, credentials alone must still enable posting."""
    monkeypatch.setattr(discord_post, "BOT_TOKEN", "real-looking-token")
    monkeypatch.setattr(discord_post, "GUILD_ID", "123456789")
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.delenv("EVOLVE_ALLOW_TEST_DISCORD", raising=False)
    assert discord_post.enabled() is True
