from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

CANONICAL_KEYS = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_OWNER_USER_ID",
    "TRADIER_ACCESS_TOKEN",
    "TRADIER_ENVIRONMENT",
)

ALIASES = {
    "DISCORD_BOT_TOKEN": ("DISCORD_BOT_TOKEN",),
    "DISCORD_GUILD_ID": ("DISCORD_GUILD_ID",),
    "DISCORD_OWNER_USER_ID": (
        "DISCORD_OWNER_USER_ID",
        "DISCORD_ALLOWED_USER_ID",
    ),
    "TRADIER_ACCESS_TOKEN": (
        "TRADIER_ACCESS_TOKEN",
        "TRADIER_TOKEN",
    ),
    "TRADIER_ENVIRONMENT": ("TRADIER_ENVIRONMENT",),
}


class CredentialMigrationError(RuntimeError):
    pass


def parse_env(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name:
            values[name] = value.strip()
    return values


def infer_tradier_environment(values: Mapping[str, str]) -> str:
    explicit = values.get("TRADIER_ENVIRONMENT", "").strip().lower()
    if explicit:
        if explicit in {"paper", "sandbox"}:
            return "paper"
        if explicit in {"production", "live", "market-data"}:
            return "production"
        raise CredentialMigrationError(
            "TRADIER_ENVIRONMENT must be paper, sandbox, production, live, or market-data."
        )

    base_url = values.get("TRADIER_BASE_URL", "").strip().lower()
    if "sandbox.tradier.com" in base_url:
        return "paper"
    if "api.tradier.com" in base_url:
        return "production"

    return "production"


def _first_value(values: Mapping[str, str], names: tuple[str, ...]) -> tuple[str, str]:
    for name in names:
        value = values.get(name, "").strip()
        if value:
            return value, name
    return "", ""


def discord_guild_owner(bot_token: str, guild_id: str, timeout: int = 20) -> str:
    request = Request(
        f"https://discord.com/api/v10/guilds/{guild_id}",
        headers={
            "Authorization": f"Bot {bot_token}",
            "User-Agent": "Tradysquid/0.1 credential migration",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CredentialMigrationError(
            "DISCORD_OWNER_USER_ID was not stored and Discord guild-owner lookup failed."
        ) from exc
    owner_id = str(payload.get("owner_id") or "").strip()
    if not owner_id:
        raise CredentialMigrationError(
            "Discord guild response did not include an owner_id."
        )
    return owner_id


def canonicalize(
    values: Mapping[str, str],
    *,
    allow_owner_lookup: bool = True,
) -> tuple[dict[str, str], dict[str, str]]:
    canonical: dict[str, str] = {}
    sources: dict[str, str] = {}

    for canonical_name, aliases in ALIASES.items():
        if canonical_name == "TRADIER_ENVIRONMENT":
            continue
        value, source = _first_value(values, aliases)
        if value:
            canonical[canonical_name] = value
            sources[canonical_name] = source

    canonical["TRADIER_ENVIRONMENT"] = infer_tradier_environment(values)
    sources["TRADIER_ENVIRONMENT"] = (
        "TRADIER_ENVIRONMENT"
        if values.get("TRADIER_ENVIRONMENT", "").strip()
        else "TRADIER_BASE_URL/default"
    )

    if not canonical.get("DISCORD_OWNER_USER_ID") and allow_owner_lookup:
        token = canonical.get("DISCORD_BOT_TOKEN", "")
        guild_id = canonical.get("DISCORD_GUILD_ID", "")
        if token and guild_id:
            canonical["DISCORD_OWNER_USER_ID"] = discord_guild_owner(token, guild_id)
            sources["DISCORD_OWNER_USER_ID"] = "Discord guild owner_id"

    missing = [name for name in CANONICAL_KEYS if not canonical.get(name, "").strip()]
    if missing:
        raise CredentialMigrationError(
            "Required local credential variables are missing after legacy-name migration: "
            + ", ".join(missing)
        )
    return canonical, sources


def migrate(root: Path, *, allow_owner_lookup: bool = True) -> dict[str, object]:
    env_path = root / ".env"
    receipt_path = root / "state" / "credential-migration.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)

    if not env_path.exists():
        receipt = {
            "status": "FAILED",
            "reason": ".env was not found",
            "canonical_keys": list(CANONICAL_KEYS),
        }
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        raise CredentialMigrationError("Local .env was not found.")

    values = parse_env(env_path.read_text(encoding="utf-8-sig"))
    try:
        canonical, sources = canonicalize(
            values,
            allow_owner_lookup=allow_owner_lookup,
        )
    except CredentialMigrationError as exc:
        receipt = {
            "status": "FAILED",
            "reason": str(exc),
            "present_names": sorted(values),
            "secret_values_written": False,
        }
        receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        raise

    # Preserve every unrelated local integration setting. Canonical names are
    # added or updated without deleting legacy aliases still consumed by older
    # local components.
    merged = dict(values)
    merged.update(canonical)
    ordered_names = list(values)
    ordered_names.extend(name for name in CANONICAL_KEYS if name not in ordered_names)
    lines = [f"{name}={merged[name]}" for name in ordered_names]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    receipt = {
        "status": "PASS",
        "canonical_keys": list(CANONICAL_KEYS),
        "sources": sources,
        "preserved_names": sorted(name for name in values if name not in CANONICAL_KEYS),
        "secret_values_written": False,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--no-owner-lookup", action="store_true")
    args = parser.parse_args()
    try:
        receipt = migrate(
            args.root.resolve(),
            allow_owner_lookup=not args.no_owner_lookup,
        )
    except CredentialMigrationError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(
        "PASS: canonical credential names prepared from "
        + ", ".join(sorted(receipt["sources"].values()))
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
