from __future__ import annotations

import json
from pathlib import Path

import pytest

from tradysquid.operations.credential_migration import (
    canonicalize,
    migrate,
    parse_env,
)
from tradysquid.operations.install_preflight import (
    InstallPreflightError,
    restore_file_exact,
    sha256_file,
    validate_canonical_credentials,
    validate_migration_sources,
)


PRODUCTION_SHAPED_ENV = {
    "DISCORD_BOT_TOKEN": "test-discord-token",
    "DISCORD_GUILD_ID": "123456789",
    "DISCORD_ALLOWED_USER_ID": "987654321",
    "TRADIER_ACCESS_TOKEN": "test-tradier-token",
    "TRADIER_BASE_URL": "https://api.tradier.com/v1",
}


def test_production_shaped_legacy_env_passes_source_preflight() -> None:
    receipt = validate_migration_sources(PRODUCTION_SHAPED_ENV)
    assert receipt["status"] == "PASS"
    assert receipt["phase"] == "pre-migration"
    assert receipt["sources"] == {
        "DISCORD_BOT_TOKEN": "DISCORD_BOT_TOKEN",
        "DISCORD_GUILD_ID": "DISCORD_GUILD_ID",
        "DISCORD_OWNER_USER_ID": "DISCORD_ALLOWED_USER_ID",
        "TRADIER_ACCESS_TOKEN": "TRADIER_ACCESS_TOKEN",
        "TRADIER_ENVIRONMENT": "TRADIER_BASE_URL",
    }


def test_missing_canonical_owner_does_not_fail_source_preflight() -> None:
    values = dict(PRODUCTION_SHAPED_ENV)
    values.pop("DISCORD_ALLOWED_USER_ID")
    receipt = validate_migration_sources(values)
    assert receipt["sources"]["DISCORD_OWNER_USER_ID"] == (
        "Discord guild owner_id lookup"
    )


def test_missing_tradier_environment_and_url_uses_migration_default() -> None:
    values = dict(PRODUCTION_SHAPED_ENV)
    values.pop("TRADIER_BASE_URL")
    receipt = validate_migration_sources(values)
    assert receipt["sources"]["TRADIER_ENVIRONMENT"] == "migration default"


def test_legacy_tradier_token_is_accepted_before_migration() -> None:
    values = dict(PRODUCTION_SHAPED_ENV)
    values["TRADIER_TOKEN"] = values.pop("TRADIER_ACCESS_TOKEN")
    receipt = validate_migration_sources(values)
    assert receipt["sources"]["TRADIER_ACCESS_TOKEN"] == "TRADIER_TOKEN"


def test_missing_tradier_token_fails_source_preflight() -> None:
    values = dict(PRODUCTION_SHAPED_ENV)
    values.pop("TRADIER_ACCESS_TOKEN")
    with pytest.raises(InstallPreflightError, match="TRADIER_ACCESS_TOKEN"):
        validate_migration_sources(values)


def test_canonical_validation_runs_only_after_migration() -> None:
    with pytest.raises(InstallPreflightError, match="DISCORD_OWNER_USER_ID"):
        validate_canonical_credentials(PRODUCTION_SHAPED_ENV)

    canonical, _ = canonicalize(PRODUCTION_SHAPED_ENV, allow_owner_lookup=False)
    receipt = validate_canonical_credentials(canonical)
    assert receipt["status"] == "PASS"
    assert receipt["phase"] == "post-migration"


def test_production_shaped_fixture_adds_canonical_names_without_deleting_legacy(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in PRODUCTION_SHAPED_ENV.items())
        + "\n",
        encoding="utf-8",
    )

    migrate(tmp_path, allow_owner_lookup=False)
    migrated = parse_env(env_path.read_text(encoding="utf-8"))
    for name, value in PRODUCTION_SHAPED_ENV.items():
        assert migrated[name] == value
    assert migrated["DISCORD_OWNER_USER_ID"] == "987654321"
    assert migrated["TRADIER_ACCESS_TOKEN"] == "test-tradier-token"
    assert migrated["TRADIER_ENVIRONMENT"] == "production"


def test_owner_lookup_and_environment_default_are_applied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        "DISCORD_BOT_TOKEN": "test-discord-token",
        "DISCORD_GUILD_ID": "123456789",
        "TRADIER_ACCESS_TOKEN": "test-tradier-token",
    }
    monkeypatch.setattr(
        "tradysquid.operations.credential_migration.discord_guild_owner",
        lambda bot_token, guild_id: "guild-owner-123",
    )
    canonical, sources = canonicalize(values, allow_owner_lookup=True)
    assert canonical["DISCORD_OWNER_USER_ID"] == "guild-owner-123"
    assert canonical["TRADIER_ENVIRONMENT"] == "production"
    assert sources["DISCORD_OWNER_USER_ID"] == "Discord guild owner_id"
    assert sources["TRADIER_ENVIRONMENT"] == "TRADIER_BASE_URL/default"


def test_existing_access_token_remains_unchanged() -> None:
    canonical, sources = canonicalize(PRODUCTION_SHAPED_ENV, allow_owner_lookup=False)
    assert canonical["TRADIER_ACCESS_TOKEN"] == "test-tradier-token"
    assert sources["TRADIER_ACCESS_TOKEN"] == "TRADIER_ACCESS_TOKEN"


def test_receipts_never_contain_secret_values(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(f"{key}={value}" for key, value in PRODUCTION_SHAPED_ENV.items())
        + "\n",
        encoding="utf-8",
    )
    migrate(tmp_path, allow_owner_lookup=False)
    receipt_text = (tmp_path / "state" / "credential-migration.json").read_text(
        encoding="utf-8"
    )
    assert "test-discord-token" not in receipt_text
    assert "test-tradier-token" not in receipt_text
    assert json.loads(receipt_text)["secret_values_written"] is False


def test_restore_file_exact_restores_original_env_bytes(tmp_path: Path) -> None:
    original = tmp_path / "backup" / ".env"
    destination = tmp_path / "app" / ".env"
    original.parent.mkdir(parents=True)
    destination.parent.mkdir(parents=True)
    original_bytes = b"DISCORD_BOT_TOKEN=abc\r\nTRADIER_TOKEN=xyz\r\n"
    original.write_bytes(original_bytes)
    destination.write_text("corrupted=true\n", encoding="utf-8")

    restored_hash = restore_file_exact(original, destination)
    assert destination.read_bytes() == original_bytes
    assert restored_hash == sha256_file(original) == sha256_file(destination)
