from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest import mock

import pytest

import discord_post


def _fake_response(status_code: int, json_body=None, content=b"{}"):
    response = mock.Mock()
    response.status_code = status_code
    response.ok = 200 <= status_code < 300
    response.content = content
    response.json.return_value = json_body if json_body is not None else {}
    response.text = str(json_body)
    return response


def _reset_cache():
    discord_post._channel_cache = {}



@pytest.fixture(autouse=True)
def _allow_discord_in_this_module(monkeypatch):
    """This module exercises the posting logic itself, with `_request`
    mocked - so it opts past the guard that stops the rest of the suite
    reaching the live server.

    The guard exists because evolve's fixtures posted seven fake "T1"
    trades into the real #evolve-losses channel, where they were
    indistinguishable from real losing trades. Opting in here is safe only
    because every test below replaces the transport; nothing in this file
    may perform a real request.
    """
    monkeypatch.setenv("EVOLVE_ALLOW_TEST_DISCORD", "1")


def test_enabled_is_false_without_credentials():
    with mock.patch.object(discord_post, "BOT_TOKEN", ""), mock.patch.object(discord_post, "GUILD_ID", "123"):
        assert discord_post.enabled() is False


def test_enabled_is_true_with_both_credentials():
    with mock.patch.object(discord_post, "BOT_TOKEN", "tok"), mock.patch.object(discord_post, "GUILD_ID", "123"):
        assert discord_post.enabled() is True


def test_post_message_returns_none_when_disabled():
    with mock.patch.object(discord_post, "BOT_TOKEN", ""), mock.patch.object(discord_post, "GUILD_ID", ""):
        assert discord_post.post_message("dashboard", "hello") is None


def test_post_file_returns_none_when_file_is_missing():
    with mock.patch.object(discord_post, "BOT_TOKEN", "tok"), mock.patch.object(discord_post, "GUILD_ID", "123"):
        assert discord_post.post_file("dashboard", Path("does-not-exist.png")) is None


def test_ensure_channels_creates_category_and_channels_when_none_exist():
    _reset_cache()
    created = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        if method == "GET":
            return _fake_response(200, [])
        created.append(json)
        if json["type"] == discord_post.GUILD_CATEGORY_CHANNEL_TYPE:
            return _fake_response(200, {"id": "cat-1", "name": json["name"], "type": 4})
        return _fake_response(200, {"id": f"chan-{json['name']}", "name": json["name"], "type": 0, "parent_id": "cat-1"})

    with (
        mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
        mock.patch.object(discord_post, "GUILD_ID", "123"),
        mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
    ):
        channels = discord_post.ensure_channels()

    assert set(channels.keys()) == {"dashboard", "trades", "journal", "wins", "losses", "reviews"}
    # category created once, then 6 channels - 7 POST calls total
    assert len(created) == 7
    assert created[0]["name"] == discord_post.CATEGORY_NAME


def test_ensure_channels_reuses_existing_category_and_channels_without_duplicating():
    _reset_cache()
    existing = [
        {"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
        {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"},
    ]
    post_calls = []

    def fake_request(method, url, headers=None, json=None, timeout=None):
        if method == "GET":
            return _fake_response(200, existing)
        post_calls.append(json)
        return _fake_response(200, {"id": "should-not-be-called"})

    with (
        mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
        mock.patch.object(discord_post, "GUILD_ID", "123"),
        mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
    ):
        channels = discord_post.ensure_channels()

    assert channels == {"dashboard": "chan-d", "trades": "chan-t", "journal": "chan-j", "wins": "chan-w", "losses": "chan-l", "reviews": "chan-r"}
    assert post_calls == []  # nothing created - everything already existed


def test_ensure_channels_result_is_cached_across_calls():
    _reset_cache()
    call_count = {"n": 0}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        call_count["n"] += 1
        return _fake_response(
            200,
            [
                {"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"},
            ],
        )

    with (
        mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
        mock.patch.object(discord_post, "GUILD_ID", "123"),
        mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
    ):
        discord_post.ensure_channels()
        discord_post.ensure_channels()

    assert call_count["n"] == 1


def test_post_message_sends_real_content_to_the_right_channel():
    _reset_cache()
    sent = {}

    def fake_request(method, url, headers=None, json=None, timeout=None):
        if method == "GET":
            return _fake_response(
                200,
                [
                    {"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                    {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"},
                ],
            )
        sent["url"] = url
        sent["json"] = json
        return _fake_response(200, {"id": "msg-1"})

    with (
        mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
        mock.patch.object(discord_post, "GUILD_ID", "123"),
        mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
    ):
        result = discord_post.post_message("trades", "SPY_EVOLVE opened a real position")

    assert result == {"id": "msg-1"}
    assert sent["url"].endswith("/channels/chan-t/messages")
    assert sent["json"]["content"] == "SPY_EVOLVE opened a real position"


def test_post_file_uploads_a_real_png_with_multipart():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        png_path = Path(temp) / "chart.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngdata")

        def fake_request(method, url, headers=None, json=None, timeout=None):
            return _fake_response(
                200,
                [
                    {"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                    {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                    {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"},
                ],
            )

        captured = {}

        def fake_post(url, headers=None, data=None, files=None, timeout=None):
            captured["url"] = url
            captured["files"] = files
            return _fake_response(200, {"id": "msg-file-1"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
            mock.patch.object(discord_post.requests, "post", side_effect=fake_post),
        ):
            result = discord_post.post_file("dashboard", png_path, content="today's dashboard")

        assert result == {"id": "msg-file-1"}
        assert captured["url"].endswith("/channels/chan-d/messages")
        assert "files[0]" in captured["files"]


def test_upsert_message_posts_fresh_with_no_prior_tracked_message():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        posted = []

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            posted.append((method, url))
            return _fake_response(200, {"id": "msg-1"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            result = discord_post.upsert_message("trades", "held-position", "current P/L: +$10")

        assert result == {"id": "msg-1"}
        assert not any(method == "DELETE" for method, _ in posted)  # nothing to delete yet
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["trades:held-position"] == "msg-1"


def test_upsert_message_sends_a_real_embed_instead_of_plain_content_when_given_one():
    """Owner: "they dont have the background around each message?" -
    plain content never renders with Discord's colored-border card look;
    only a real embeds payload does."""
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        payloads = []

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            payloads.append(json)
            return _fake_response(200, {"id": "msg-1"})

        embed = {"title": "SPY_EVOLVE #1", "color": 0x2ECC71, "fields": [{"name": "Position", "value": "BUY 1 SPY 778 CALL", "inline": False}]}
        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            discord_post.upsert_message("trades", "held-position", "plain fallback text", embed=embed)

        assert payloads[0]["embeds"] == [embed]
        assert payloads[0].get("content", "") == ""  # embed replaces plain content, doesn't sit alongside it


def test_upsert_message_patches_the_existing_card_in_place():
    """The whole point: Discord push-notifies on a new message but not
    on an edit, so a repeat upsert must PATCH the existing tracked
    message (keeping its id) rather than delete-then-repost (a fresh id
    every time) - owner: "it's spamming the fuck out of me... it simply
    needs to update per trade.\""""
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        state_path.write_text(json.dumps({"trades:held-position": "old-msg-1"}), encoding="utf-8")
        calls = []

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            calls.append((method, url))
            return _fake_response(200, {"id": "old-msg-1"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            result = discord_post.upsert_message("trades", "held-position", "current P/L: +$20")

        assert result == {"id": "old-msg-1"}
        assert not any(method == "DELETE" for method, _ in calls)
        assert ("PATCH", f"{discord_post.API_BASE}/channels/chan-t/messages/old-msg-1") in calls
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["trades:held-position"] == "old-msg-1"  # same id, never churned


def test_upsert_message_patches_with_an_embed_when_one_already_exists():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        state_path.write_text(json.dumps({"trades:held-position": "old-msg-1"}), encoding="utf-8")
        payloads = []

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            payloads.append((method, json))
            return _fake_response(200, {"id": "old-msg-1"})

        embed = {"title": "SPY_EVOLVE #1", "color": 0xF1C40F}
        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            discord_post.upsert_message("trades", "held-position", "plain fallback", embed=embed)

        patch_payloads = [j for m, j in payloads if m == "PATCH"]
        assert patch_payloads == [{"content": "", "embeds": [embed], "allowed_mentions": {"parse": []}}]


def test_upsert_message_falls_back_to_a_fresh_post_when_the_tracked_message_is_gone():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        state_path.write_text(json.dumps({"trades:held-position": "already-gone"}), encoding="utf-8")

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            if method == "PATCH":
                raise discord_post.DiscordPostError("Discord HTTP 404 for /channels/chan-t/messages/already-gone: not found")
            return _fake_response(200, {"id": "new-msg-3"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            result = discord_post.upsert_message("trades", "held-position", "current P/L: +$30")

        assert result == {"id": "new-msg-3"}  # a 404 on the edit doesn't block a fresh post
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["trades:held-position"] == "new-msg-3"


def test_upsert_file_keeps_one_card_per_card_key():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        png_path = Path(temp) / "chart.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngdata")

        def fake_request(method, url, headers=None, json=None, timeout=None):
            return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                         {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])

        def fake_post(url, headers=None, data=None, files=None, timeout=None):
            return _fake_response(200, {"id": "file-msg-1"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
            mock.patch.object(discord_post.requests, "post", side_effect=fake_post),
        ):
            discord_post.upsert_file("dashboard", "stats_card", png_path, content="stats")

        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["dashboard:stats_card"] == "file-msg-1"


def test_upsert_file_patches_the_existing_card_in_place():
    """Same PATCH-in-place fix as upsert_message, for the file-attached
    dashboard cards specifically - these are exactly the cards the owner
    was seeing spam from. attachments: [] in the PATCH payload is what
    actually replaces the old image instead of Discord keeping both."""
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        state_path.write_text(json.dumps({"dashboard:stats_card": "old-file-msg"}), encoding="utf-8")
        png_path = Path(temp) / "chart.png"
        png_path.write_bytes(b"\x89PNG\r\n\x1a\nfakepngdata")
        calls = []

        def fake_request(method, url, headers=None, json=None, data=None, files=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            calls.append((method, url, data))
            return _fake_response(200, {"id": "old-file-msg"})

        def fake_post(url, headers=None, data=None, files=None, timeout=None):
            raise AssertionError("must not fall back to a fresh post when the tracked message still exists")

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
            mock.patch.object(discord_post.requests, "post", side_effect=fake_post),
        ):
            result = discord_post.upsert_file("dashboard", "stats_card", png_path, content="stats")

        assert result == {"id": "old-file-msg"}
        patch_calls = [c for c in calls if c[0] == "PATCH"]
        assert len(patch_calls) == 1
        assert patch_calls[0][1] == f"{discord_post.API_BASE}/channels/chan-d/messages/old-file-msg"
        payload = json.loads(patch_calls[0][2]["payload_json"])
        assert payload["attachments"] == []  # clears the old image so it's replaced, not duplicated
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["dashboard:stats_card"] == "old-file-msg"  # same id, never churned


def test_post_journal_entry_posts_to_the_journal_channel_and_remembers_the_id():
    """Owner: "i said to have its own journal not more spam on the
    trade wall" - the journal is a real, separate channel (#evolve-
    journal), not a thread hanging off a trade card."""
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        calls = []

        def fake_request(method, url, headers=None, json=None, timeout=None):
            if method == "GET":
                return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                             {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                             {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])
            calls.append((method, url, json))
            return _fake_response(200, {"id": "journal-msg-1"})

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            link = discord_post.post_journal_entry("EVOLVE-1", "**Thesis:** bullish breakout")

        assert any(
            method == "POST" and url == f"{discord_post.API_BASE}/channels/chan-j/messages"
            for method, url, _ in calls
        )
        assert link == "https://discord.com/channels/123/chan-j/journal-msg-1"
        saved_state = json.loads(state_path.read_text(encoding="utf-8"))
        assert saved_state["journal:open:EVOLVE-1"] == "journal-msg-1"


def test_post_journal_entry_returns_empty_string_when_disabled():
    with mock.patch.object(discord_post, "BOT_TOKEN", ""), mock.patch.object(discord_post, "GUILD_ID", ""):
        assert discord_post.post_journal_entry("EVOLVE-1", "text") == ""


def test_get_journal_link_reads_back_what_post_journal_entry_stored():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        state_path.write_text(json.dumps({"journal:open:EVOLVE-1": "journal-msg-9"}), encoding="utf-8")

        def fake_request(method, url, headers=None, json=None, timeout=None):
            return _fake_response(200, [{"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
                                         {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-j", "name": "evolve-journal", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-w", "name": "evolve-wins", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-l", "name": "evolve-losses", "type": 0, "parent_id": "cat-1"},
                                         {"id": "chan-r", "name": "evolve-reviews", "type": 0, "parent_id": "cat-1"}])

        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
            mock.patch.object(discord_post.requests, "request", side_effect=fake_request),
        ):
            assert discord_post.get_journal_link("EVOLVE-1") == "https://discord.com/channels/123/chan-j/journal-msg-9"


def test_get_journal_link_returns_empty_string_with_no_entry_yet():
    _reset_cache()
    with tempfile.TemporaryDirectory() as temp:
        state_path = Path(temp) / "discord_message_state.json"
        with (
            mock.patch.object(discord_post, "BOT_TOKEN", "tok"),
            mock.patch.object(discord_post, "GUILD_ID", "123"),
            mock.patch.object(discord_post, "MESSAGE_STATE_PATH", state_path),
        ):
            assert discord_post.get_journal_link("EVOLVE-1") == ""


def test_get_journal_link_never_touches_disk_when_disabled():
    """A test (or any caller) without real credentials must never read
    real production state off disk just by asking for a journal link -
    matches the same enabled()-gates-everything contract every other
    function in this module already follows."""
    with mock.patch.object(discord_post, "BOT_TOKEN", ""), mock.patch.object(discord_post, "GUILD_ID", ""):
        with mock.patch.object(discord_post, "_load_message_state") as fake_load:
            assert discord_post.get_journal_link("EVOLVE-1") == ""
        fake_load.assert_not_called()
