from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradysquid.operations.credential_migration import (
    CANONICAL_KEYS,
    CredentialMigrationError,
    canonicalize,
    infer_tradier_environment,
    migrate,
    parse_env,
)


def legacy_values() -> dict[str, str]:
    return {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "12345",
        "DISCORD_ALLOWED_USER_ID": "67890",
        "TRADIER_TOKEN": "tradier-token",
        "TRADIER_BASE_URL": "https://api.tradier.com/v1",
    }


def test_parse_env_ignores_comments_and_blank_lines() -> None:
    parsed = parse_env("\n# comment\nA=1\n B = two \n")
    assert parsed == {"A": "1", "B": "two"}


def test_legacy_names_become_canonical_without_losing_values() -> None:
    canonical, sources = canonicalize(legacy_values(), allow_owner_lookup=False)
    assert canonical == {
        "DISCORD_BOT_TOKEN": "discord-token",
        "DISCORD_GUILD_ID": "12345",
        "DISCORD_OWNER_USER_ID": "67890",
        "TRADIER_ACCESS_TOKEN": "tradier-token",
        "TRADIER_ENVIRONMENT": "production",
    }
    assert sources["DISCORD_OWNER_USER_ID"] == "DISCORD_ALLOWED_USER_ID"
    assert sources["TRADIER_ACCESS_TOKEN"] == "TRADIER_TOKEN"


def test_sandbox_url_infers_paper_environment() -> None:
    assert infer_tradier_environment(
        {"TRADIER_BASE_URL": "https://sandbox.tradier.com/v1"}
    ) == "paper"


def test_invalid_explicit_environment_is_rejected() -> None:
    with pytest.raises(CredentialMigrationError):
        infer_tradier_environment({"TRADIER_ENVIRONMENT": "somewhere"})


def test_missing_owner_is_reported_when_lookup_is_disabled() -> None:
    values = legacy_values()
    values.pop("DISCORD_ALLOWED_USER_ID")
    with pytest.raises(CredentialMigrationError, match="DISCORD_OWNER_USER_ID"):
        canonicalize(values, allow_owner_lookup=False)


def test_migrate_adds_canonical_names_and_preserves_complete_env(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    values = {
        **legacy_values(),
        "DISCORD_APPLICATION_ID": "app-id",
        "DISCORD_PUBLIC_KEY": "public-key",
        "OPENAI_API_KEY": "openai-token",
        "OPENAI_MODEL": "gpt-test",
        "GITHUB_UPGRADE_TOKEN": "github-token",
        "GITHUB_REPOSITORY": "owner/repository",
        "SEC_USER_AGENT": "agent@example.com",
        "NGROK_AUTHTOKEN": "ngrok-token",
        "COMMAND_BOT_HOST": "127.0.0.1",
        "COMMAND_BOT_PORT": "8080",
        "LOCAL_FULL_SCAN_ENABLED": "true",
        "TRADINGVIEW_WEBHOOK_SECRET": "webhook-token",
    }
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in values.items()) + "\n",
        encoding="utf-8",
    )

    receipt = migrate(tmp_path, allow_owner_lookup=False)
    migrated = parse_env(env_path.read_text(encoding="utf-8"))

    for name in CANONICAL_KEYS:
        assert migrated[name]
    for name, value in values.items():
        assert migrated[name] == value
    assert migrated["TRADIER_ACCESS_TOKEN"] == "tradier-token"
    assert migrated["DISCORD_OWNER_USER_ID"] == "67890"
    assert receipt["status"] == "PASS"
    assert "OPENAI_API_KEY" in receipt["preserved_names"]
    assert "TRADINGVIEW_WEBHOOK_SECRET" in receipt["preserved_names"]

    receipt_text = (tmp_path / "state" / "credential-migration.json").read_text(
        encoding="utf-8"
    )
    for secret in (
        "discord-token",
        "tradier-token",
        "openai-token",
        "github-token",
        "ngrok-token",
        "webhook-token",
    ):
        assert secret not in receipt_text
    assert json.loads(receipt_text)["secret_values_written"] is False
