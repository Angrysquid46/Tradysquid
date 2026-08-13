from __future__ import annotations

import tempfile
from pathlib import Path
from unittest import mock

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

    assert set(channels.keys()) == {"dashboard", "trades", "reviews"}
    # category created once, then 3 channels - 4 POST calls total
    assert len(created) == 4
    assert created[0]["name"] == discord_post.CATEGORY_NAME


def test_ensure_channels_reuses_existing_category_and_channels_without_duplicating():
    _reset_cache()
    existing = [
        {"id": "cat-1", "name": discord_post.CATEGORY_NAME, "type": 4},
        {"id": "chan-d", "name": "evolve-dashboard", "type": 0, "parent_id": "cat-1"},
        {"id": "chan-t", "name": "evolve-trades", "type": 0, "parent_id": "cat-1"},
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

    assert channels == {"dashboard": "chan-d", "trades": "chan-t", "reviews": "chan-r"}
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
