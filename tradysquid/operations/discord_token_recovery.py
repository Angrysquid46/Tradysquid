from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tradysquid.operations.credential_migration import parse_env


TOKEN_KEYS = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_TOKEN",
    "BOT_TOKEN",
    "TRADEBOT_DISCORD_TOKEN",
    "DISCORD_AUTH_TOKEN",
)

EXCLUDED_PATH_PARTS = {
    ".git",
    ".venv",
    ".venv-tradysquid",
    "site-packages",
    "node_modules",
}


class DiscordTokenRecoveryError(RuntimeError):
    """Local Discord-token recovery could not produce a working token."""


class DiscordTokenRejected(DiscordTokenRecoveryError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"Discord rejected the bot token with HTTP {status_code}")
        self.status_code = status_code


class DiscordTokenNetworkError(DiscordTokenRecoveryError):
    pass


@dataclass(frozen=True)
class TokenCandidate:
    token: str
    source_path: Path
    source_key: str
    source_kind: str
    normalization_applied: bool


@dataclass(frozen=True)
class DiscordIdentity:
    bot_id: str
    guild_id: str
    guild_owner_id: str


def normalize_discord_token(value: str) -> str:
    token = str(value or "").strip()
    for _ in range(3):
        if len(token) >= 2 and token[0] == token[-1] and token[0] in {"'", '"'}:
            token = token[1:-1].strip()
            continue
        break
    if token.casefold().startswith("bot "):
        token = token[4:].strip()
    return token


def _token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _request_json(url: str, token: str, timeout: int = 20) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Authorization": f"Bot {token}",
            "User-Agent": "Tradysquid/0.1 local token recovery",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            status = int(getattr(response, "status", 200))
            if status != 200:
                raise DiscordTokenRejected(status)
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise DiscordTokenRejected(exc.code) from exc
        raise DiscordTokenNetworkError(f"Discord returned HTTP {exc.code}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise DiscordTokenNetworkError(
            f"Discord could not be reached: {type(exc).__name__}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise DiscordTokenNetworkError("Discord returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise DiscordTokenNetworkError("Discord returned an invalid payload")
    return payload


def validate_discord_token(token: str, guild_id: str, timeout: int = 20) -> DiscordIdentity:
    user = _request_json("https://discord.com/api/v10/users/@me", token, timeout)
    bot_id = str(user.get("id") or "").strip()
    if not bot_id:
        raise DiscordTokenRejected(401)

    guild = _request_json(
        f"https://discord.com/api/v10/guilds/{guild_id}", token, timeout
    )
    returned_guild_id = str(guild.get("id") or "").strip()
    if returned_guild_id != guild_id:
        raise DiscordTokenRecoveryError(
            "Discord authenticated the token but returned a different guild identity"
        )
    return DiscordIdentity(
        bot_id=bot_id,
        guild_id=returned_guild_id,
        guild_owner_id=str(guild.get("owner_id") or "").strip(),
    )


def _path_allowed(path: Path) -> bool:
    return not any(part.casefold() in EXCLUDED_PATH_PARTS for part in path.parts)


def discover_env_files(root: Path, search_root: Path) -> list[Path]:
    root = root.resolve()
    search_root = search_root.resolve()
    current = root / ".env"
    discovered: dict[Path, float] = {}

    if current.is_file():
        discovered[current.resolve()] = float("inf")

    try:
        candidates: Iterable[Path] = search_root.rglob(".env")
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
                if resolved == current.resolve() or not candidate.is_file():
                    continue
                if not _path_allowed(resolved):
                    continue
                discovered[resolved] = candidate.stat().st_mtime
            except (OSError, RuntimeError):
                continue
    except (OSError, RuntimeError):
        pass

    return [path for path, _ in sorted(discovered.items(), key=lambda item: item[1], reverse=True)]


def collect_candidates(root: Path, search_root: Path) -> tuple[list[TokenCandidate], str]:
    env_files = discover_env_files(root, search_root)
    current_path = (root / ".env").resolve()
    current_values = parse_env(current_path.read_text(encoding="utf-8-sig"))
    guild_id = str(current_values.get("DISCORD_GUILD_ID") or "").strip()
    if not guild_id:
        raise DiscordTokenRecoveryError("DISCORD_GUILD_ID is missing from the canonical .env")

    seen: set[str] = set()
    candidates: list[TokenCandidate] = []
    for env_path in env_files:
        try:
            values = parse_env(env_path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError):
            continue
        source_kind = "current" if env_path == current_path else "backup"
        for key in TOKEN_KEYS:
            raw = str(values.get(key) or "")
            normalized = normalize_discord_token(raw)
            if not normalized:
                continue
            fingerprint = _token_fingerprint(normalized)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            candidates.append(
                TokenCandidate(
                    token=normalized,
                    source_path=env_path,
                    source_key=key,
                    source_kind=source_kind,
                    normalization_applied=normalized != raw.strip(),
                )
            )
    return candidates, guild_id


def write_canonical_token(env_path: Path, token: str) -> None:
    original = env_path.read_text(encoding="utf-8-sig")
    output: list[str] = []
    replaced = False
    for raw_line in original.splitlines():
        stripped = raw_line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            name = stripped.split("=", 1)[0].strip()
            if name == "DISCORD_BOT_TOKEN":
                if not replaced:
                    output.append(f"DISCORD_BOT_TOKEN={token}")
                    replaced = True
                continue
        output.append(raw_line)
    if not replaced:
        output.append(f"DISCORD_BOT_TOKEN={token}")
    env_path.write_text("\n".join(output).rstrip("\n") + "\n", encoding="utf-8")


def _write_receipt(root: Path, payload: dict[str, object]) -> Path:
    receipt_path = root / "state" / "discord-token-recovery.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["observed_at"] = datetime.now(timezone.utc).isoformat()
    payload["secret_values_written"] = False
    receipt_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return receipt_path


def recover_discord_token(
    root: Path,
    search_root: Path,
    *,
    validator: Callable[[str, str], DiscordIdentity] = validate_discord_token,
) -> dict[str, object]:
    root = root.resolve()
    search_root = search_root.resolve()
    env_path = root / ".env"
    if not env_path.is_file():
        raise DiscordTokenRecoveryError(f"Canonical environment file is missing: {env_path}")

    candidates, guild_id = collect_candidates(root, search_root)
    rejected_statuses: list[int] = []
    network_errors = 0
    tested = 0

    for candidate in candidates[:50]:
        tested += 1
        try:
            identity = validator(candidate.token, guild_id)
        except DiscordTokenRejected as exc:
            rejected_statuses.append(exc.status_code)
            continue
        except DiscordTokenNetworkError:
            network_errors += 1
            continue

        current_values = parse_env(env_path.read_text(encoding="utf-8-sig"))
        current_token = normalize_discord_token(
            str(current_values.get("DISCORD_BOT_TOKEN") or "")
        )
        changed = current_token != candidate.token or candidate.normalization_applied
        if changed:
            write_canonical_token(env_path, candidate.token)

        receipt = {
            "status": "PASS",
            "result": "RECOVERED" if changed else "ALREADY_VALID",
            "candidate_count": len(candidates),
            "tested_count": tested,
            "selected_source_kind": candidate.source_kind,
            "selected_source_key": candidate.source_key,
            "normalization_applied": candidate.normalization_applied,
            "canonical_env_updated": changed,
            "discord_bot_id": identity.bot_id,
            "discord_guild_id": identity.guild_id,
            "discord_owner_id": identity.guild_owner_id,
        }
        _write_receipt(root, receipt)
        return receipt

    if network_errors and not rejected_statuses:
        message = (
            "Discord could not be reached while validating locally preserved bot tokens. "
            "No credential was changed."
        )
        action = "RETRY_WHEN_DISCORD_IS_REACHABLE"
    else:
        message = (
            "No locally preserved Discord bot token authenticated. Discord rejected every "
            "candidate with HTTP 401 or 403. Reset the bot token in the Discord Developer "
            "Portal, replace DISCORD_BOT_TOKEN in C:\\Tradysquid\\app\\.env, and rerun."
        )
        action = "RESET_DISCORD_BOT_TOKEN"

    receipt = {
        "status": "FAILED",
        "result": "NO_VALID_LOCAL_TOKEN",
        "required_action": action,
        "error": message,
        "candidate_count": len(candidates),
        "tested_count": tested,
        "rejected_http_statuses": sorted(set(rejected_statuses)),
        "network_error_count": network_errors,
        "canonical_env_updated": False,
    }
    _write_receipt(root, receipt)
    raise DiscordTokenRecoveryError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--search-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        receipt = recover_discord_token(args.root, args.search_root)
    except DiscordTokenRecoveryError as exc:
        print(f"FAILED: {exc}")
        return 1
    print(
        "PASS: Discord token status "
        + str(receipt.get("result") or "UNKNOWN")
        + "; source="
        + str(receipt.get("selected_source_kind") or "unknown")
        + "/"
        + str(receipt.get("selected_source_key") or "unknown")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
