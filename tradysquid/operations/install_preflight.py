from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Mapping

from .credential_migration import CANONICAL_KEYS, parse_env


class InstallPreflightError(RuntimeError):
    """Raised when the local ignored environment cannot support installation."""


def _present(values: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = values.get(name, "").strip()
        if value:
            return name
    return ""


def validate_migration_sources(values: Mapping[str, str]) -> dict[str, object]:
    """Validate only the source material needed by credential migration.

    Canonical names are deliberately not required here. Legacy aliases and the
    documented Tradier environment default remain valid before migration.
    """

    sources: dict[str, str] = {}
    missing: list[str] = []

    discord_token = _present(values, "DISCORD_BOT_TOKEN")
    if discord_token:
        sources["DISCORD_BOT_TOKEN"] = discord_token
    else:
        missing.append("DISCORD_BOT_TOKEN")

    discord_guild = _present(values, "DISCORD_GUILD_ID")
    if discord_guild:
        sources["DISCORD_GUILD_ID"] = discord_guild
    else:
        missing.append("DISCORD_GUILD_ID")

    discord_owner = _present(
        values,
        "DISCORD_OWNER_USER_ID",
        "DISCORD_ALLOWED_USER_ID",
    )
    if discord_owner:
        sources["DISCORD_OWNER_USER_ID"] = discord_owner
    elif discord_token and discord_guild:
        sources["DISCORD_OWNER_USER_ID"] = "Discord guild owner_id lookup"
    else:
        missing.append("DISCORD_OWNER_USER_ID source")

    tradier_token = _present(values, "TRADIER_ACCESS_TOKEN", "TRADIER_TOKEN")
    if tradier_token:
        sources["TRADIER_ACCESS_TOKEN"] = tradier_token
    else:
        missing.append("TRADIER_ACCESS_TOKEN or TRADIER_TOKEN")

    tradier_environment = _present(values, "TRADIER_ENVIRONMENT", "TRADIER_BASE_URL")
    sources["TRADIER_ENVIRONMENT"] = tradier_environment or "migration default"

    if missing:
        raise InstallPreflightError(
            "Migration source credentials are incomplete: " + ", ".join(missing)
        )

    return {
        "status": "PASS",
        "phase": "pre-migration",
        "sources": sources,
        "secret_values_written": False,
    }


def validate_canonical_credentials(values: Mapping[str, str]) -> dict[str, object]:
    """Require the five canonical names after migration has completed."""

    missing = [name for name in CANONICAL_KEYS if not values.get(name, "").strip()]
    if missing:
        raise InstallPreflightError(
            "Canonical credentials are incomplete after migration: "
            + ", ".join(missing)
        )
    return {
        "status": "PASS",
        "phase": "post-migration",
        "canonical_names": list(CANONICAL_KEYS),
        "secret_values_written": False,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def restore_file_exact(source: Path, destination: Path) -> str:
    """Restore a file byte-for-byte and return its verified SHA-256 hash."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    source_hash = sha256_file(source)
    destination_hash = sha256_file(destination)
    if source_hash != destination_hash:
        raise InstallPreflightError("Restored file hash does not match the backup.")
    return destination_hash


def load_env(path: Path) -> dict[str, str]:
    if not path.exists():
        raise InstallPreflightError(f"Environment file was not found: {path}")
    return parse_env(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env", type=Path, required=True)
    parser.add_argument("--phase", choices=("source", "canonical"), required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    try:
        values = load_env(args.env.resolve())
        if args.phase == "source":
            receipt = validate_migration_sources(values)
        else:
            receipt = validate_canonical_credentials(values)
    except InstallPreflightError as exc:
        receipt = {
            "status": "FAILED",
            "phase": args.phase,
            "reason": str(exc),
            "secret_values_written": False,
        }
        if args.receipt:
            args.receipt.parent.mkdir(parents=True, exist_ok=True)
            args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(f"FAILED: {exc}")
        return 1

    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print("PASS: " + args.phase + " credential validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
