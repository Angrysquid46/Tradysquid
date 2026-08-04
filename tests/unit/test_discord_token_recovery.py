from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradysquid.operations.discord_token_recovery import (
    DiscordIdentity,
    DiscordTokenRecoveryError,
    DiscordTokenRejected,
    normalize_discord_token,
    parse_env,
    recover_discord_token,
)


def _write_env(path: Path, **values: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(f"{name}={value}" for name, value in values.items()) + "\n",
        encoding="utf-8",
    )


def _identity(_: str, guild_id: str) -> DiscordIdentity:
    return DiscordIdentity("bot-1", guild_id, "owner-1")


def test_normalize_discord_token_removes_quotes_whitespace_and_bot_prefix() -> None:
    assert normalize_discord_token('  "Bot abc.def.ghi"  ') == "abc.def.ghi"
    assert normalize_discord_token("'abc.def.ghi'") == "abc.def.ghi"


def test_current_prefixed_token_is_normalized_and_rewritten(tmp_path: Path) -> None:
    root = tmp_path / "app"
    env = root / ".env"
    _write_env(
        env,
        DISCORD_BOT_TOKEN='"Bot valid-token"',
        DISCORD_GUILD_ID="guild-1",
        DISCORD_OWNER_USER_ID="owner-1",
        KEEP_ME="preserved",
    )

    receipt = recover_discord_token(root, tmp_path, validator=_identity)
    values = parse_env(env.read_text(encoding="utf-8"))

    assert receipt["status"] == "PASS"
    assert receipt["result"] == "RECOVERED"
    assert receipt["normalization_applied"] is True
    assert values["DISCORD_BOT_TOKEN"] == "valid-token"
    assert values["KEEP_ME"] == "preserved"


def test_valid_legacy_alias_in_current_env_replaces_stale_canonical_token(
    tmp_path: Path,
) -> None:
    root = tmp_path / "app"
    env = root / ".env"
    _write_env(
        env,
        DISCORD_BOT_TOKEN="stale-token",
        DISCORD_TOKEN="working-token",
        DISCORD_GUILD_ID="guild-1",
        DISCORD_OWNER_USER_ID="owner-1",
    )

    def validator(token: str, guild_id: str) -> DiscordIdentity:
        if token == "stale-token":
            raise DiscordTokenRejected(401)
        assert token == "working-token"
        return DiscordIdentity("bot-1", guild_id, "owner-1")

    receipt = recover_discord_token(root, tmp_path, validator=validator)
    values = parse_env(env.read_text(encoding="utf-8"))

    assert receipt["selected_source_key"] == "DISCORD_TOKEN"
    assert values["DISCORD_BOT_TOKEN"] == "working-token"


def test_valid_token_is_recovered_from_preserved_backup(tmp_path: Path) -> None:
    root = tmp_path / "app"
    env = root / ".env"
    _write_env(
        env,
        DISCORD_BOT_TOKEN="stale-token",
        DISCORD_GUILD_ID="guild-1",
        DISCORD_OWNER_USER_ID="owner-1",
    )
    backup = tmp_path / "Tradysquid-auto-handoff-20260804-010000" / ".env"
    _write_env(
        backup,
        DISCORD_BOT_TOKEN="working-backup-token",
        DISCORD_GUILD_ID="guild-1",
    )

    def validator(token: str, guild_id: str) -> DiscordIdentity:
        if token == "stale-token":
            raise DiscordTokenRejected(401)
        assert token == "working-backup-token"
        return DiscordIdentity("bot-1", guild_id, "owner-1")

    receipt = recover_discord_token(root, tmp_path, validator=validator)
    values = parse_env(env.read_text(encoding="utf-8"))

    assert receipt["selected_source_kind"] == "backup"
    assert values["DISCORD_BOT_TOKEN"] == "working-backup-token"


def test_all_rejected_tokens_fail_fast_without_modifying_env(tmp_path: Path) -> None:
    # This is the exact live-laptop outcome: every local candidate receives HTTP 401.
    root = tmp_path / "app"
    env = root / ".env"
    _write_env(
        env,
        DISCORD_BOT_TOKEN="stale-token",
        DISCORD_GUILD_ID="guild-1",
        DISCORD_OWNER_USER_ID="owner-1",
        KEEP_ME="preserved",
    )
    before = env.read_bytes()

    def reject(_: str, __: str) -> DiscordIdentity:
        raise DiscordTokenRejected(401)

    with pytest.raises(DiscordTokenRecoveryError, match="Reset the bot token"):
        recover_discord_token(root, tmp_path, validator=reject)

    assert env.read_bytes() == before
    receipt_text = (root / "state" / "discord-token-recovery.json").read_text(
        encoding="utf-8"
    )
    receipt = json.loads(receipt_text)
    assert receipt["status"] == "FAILED"
    assert receipt["required_action"] == "RESET_DISCORD_BOT_TOKEN"
    assert receipt["canonical_env_updated"] is False
    assert "stale-token" not in receipt_text
    assert receipt["secret_values_written"] is False


def test_receipt_never_contains_recovered_secret(tmp_path: Path) -> None:
    root = tmp_path / "app"
    env = root / ".env"
    secret = "very-secret-working-token"
    _write_env(
        env,
        DISCORD_BOT_TOKEN=secret,
        DISCORD_GUILD_ID="guild-1",
        DISCORD_OWNER_USER_ID="owner-1",
    )

    recover_discord_token(root, tmp_path, validator=_identity)
    receipt_text = (root / "state" / "discord-token-recovery.json").read_text(
        encoding="utf-8"
    )

    assert secret not in receipt_text
    assert json.loads(receipt_text)["secret_values_written"] is False
