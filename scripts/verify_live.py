from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

from tradysquid.app import Application
from tradysquid.core.config import redact


REQUIRED_NAMES = (
    "DISCORD_BOT_TOKEN",
    "DISCORD_GUILD_ID",
    "DISCORD_OWNER_USER_ID",
    "TRADIER_ACCESS_TOKEN",
    "TRADIER_ENVIRONMENT",
)

FORBIDDEN_PROVIDER_METHODS = (
    "place_order",
    "submit_order",
    "preview_order",
    "cancel_order",
    "replace_order",
    "modify_order",
    "account_balances",
    "account_positions",
)


class LiveVerificationFailure(RuntimeError):
    """A categorized live acceptance check failed."""

    def __init__(self, category: str, check: str, message: str) -> None:
        super().__init__(message)
        self.category = category
        self.check = check


def _http_json(response: Any, category: str, check: str) -> dict[str, Any]:
    status_code = int(getattr(response, "status_code", 0))
    if status_code != 200:
        failure_category = "AUTHENTICATION" if status_code in {401, 403} else category
        raise LiveVerificationFailure(
            failure_category,
            check,
            f"{check} returned HTTP {status_code}",
        )
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise LiveVerificationFailure(category, check, f"{check} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise LiveVerificationFailure(category, check, f"{check} returned an invalid payload")
    return payload


def _classify_application_error(exc: Exception) -> str:
    text = str(exc).lower()
    if "authentication" in text or "401" in text or "403" in text:
        return "AUTHENTICATION"
    if "network" in text or isinstance(exc, requests.RequestException):
        return "NETWORK"
    if "tradier" in text or "provider" in text or "rate limit" in text:
        return "PROVIDER"
    return "APPLICATION"


def _strategy_count(app: Any) -> int:
    registry = getattr(app, "registry", None)
    all_strategies = getattr(registry, "all", None)
    if not callable(all_strategies):
        raise LiveVerificationFailure(
            "APPLICATION",
            "strategy-registry",
            "Application strategy registry is unavailable",
        )
    strategies = list(all_strategies())
    if len(strategies) != 6:
        raise LiveVerificationFailure(
            "APPLICATION",
            "strategy-registry",
            f"Expected six registered strategies, got {len(strategies)}",
        )
    return len(strategies)


def _local_universe(app: Any) -> list[str]:
    universe = getattr(app, "universe", None)
    active = getattr(universe, "active", None)
    if not callable(active):
        return []
    rows = active()
    symbols: list[str] = []
    for row in rows or []:
        if isinstance(row, dict):
            symbol = row.get("symbol")
        else:
            symbol = row
        if symbol:
            symbols.append(str(symbol).upper())
    return symbols


def _market_state(clock: dict[str, Any]) -> str:
    payload = clock.get("clock", clock)
    if not isinstance(payload, dict):
        return "unknown"
    return str(
        payload.get("state")
        or payload.get("status")
        or payload.get("market_state")
        or "unknown"
    ).casefold()


def _assert_read_only_provider(provider: Any) -> list[str]:
    forbidden = sorted(
        name
        for name in FORBIDDEN_PROVIDER_METHODS
        if callable(getattr(provider, name, None))
    )
    if forbidden:
        raise LiveVerificationFailure(
            "APPLICATION",
            "read-only-provider-boundary",
            "Provider exposes brokerage-write methods: " + ", ".join(forbidden),
        )
    return forbidden


def run_live_verification(
    root: Path,
    *,
    application_factory: Callable[[Path], Any] = Application,
    http_get: Callable[..., Any] = requests.get,
    load_environment: bool = True,
) -> dict[str, Any]:
    if load_environment:
        load_dotenv(root / ".env", override=True)
    missing = [name for name in REQUIRED_NAMES if not os.environ.get(name)]
    if missing:
        raise LiveVerificationFailure(
            "CONFIGURATION",
            "canonical-credentials",
            "Missing required variable names: " + ", ".join(missing),
        )

    try:
        app = application_factory(root)
        provider = app.provider
        _assert_read_only_provider(provider)

        # The market clock is authenticated, read-only, and available whether the
        # market is open or closed. Installation must not depend on an option chain,
        # universe refresh, or a full strategy scan at midnight or on weekends.
        clock = provider.market_clock()
        if not isinstance(clock, dict) or not clock:
            raise LiveVerificationFailure(
                "PROVIDER",
                "tradier-market-clock",
                "Tradier market clock returned no data",
            )

        strategy_count = _strategy_count(app)
        active_symbols = _local_universe(app)
    except LiveVerificationFailure:
        raise
    except Exception as exc:
        raise LiveVerificationFailure(
            _classify_application_error(exc),
            "tradier-read-only-verification",
            f"{type(exc).__name__}: {exc}",
        ) from exc

    headers = {
        "Authorization": "Bot " + os.environ["DISCORD_BOT_TOKEN"],
        "User-Agent": "Tradysquid/0.1",
    }
    try:
        user_payload = _http_json(
            http_get(
                "https://discord.com/api/v10/users/@me",
                headers=headers,
                timeout=(5, 20),
            ),
            "DISCORD",
            "discord-bot-authentication",
        )
        guild_payload = _http_json(
            http_get(
                "https://discord.com/api/v10/guilds/" + os.environ["DISCORD_GUILD_ID"],
                headers=headers,
                timeout=(5, 20),
            ),
            "DISCORD",
            "discord-guild-access",
        )
    except LiveVerificationFailure:
        raise
    except requests.RequestException as exc:
        raise LiveVerificationFailure(
            "NETWORK",
            "discord-network",
            f"Discord network failure: {type(exc).__name__}",
        ) from exc

    configured_guild = os.environ["DISCORD_GUILD_ID"]
    configured_owner = os.environ["DISCORD_OWNER_USER_ID"]
    if str(guild_payload.get("id")) != configured_guild:
        raise LiveVerificationFailure(
            "DISCORD", "discord-guild-identity", "Discord returned a different guild identity"
        )
    if str(guild_payload.get("owner_id")) != configured_owner:
        raise LiveVerificationFailure(
            "DISCORD", "discord-owner-identity", "Configured owner does not match guild owner_id"
        )

    return {
        "status": "PASS",
        "tradier_read_only": True,
        "tradier_clock": True,
        "market_state": _market_state(clock),
        "universe_count": len(active_symbols),
        "controlled_symbol": active_symbols[0] if active_symbols else None,
        "strategy_decisions": strategy_count,
        "strategy_registry_count": strategy_count,
        "controlled_scan_performed": False,
        "option_chain_required": False,
        "market_open_required": False,
        "provider_write_methods": [],
        "discord_bot_id": user_payload.get("id"),
        "discord_guild_id": guild_payload.get("id"),
        "discord_owner_id": guild_payload.get("owner_id"),
        "brokerage_write_request": False,
        "second_computer_request": False,
        "lan_service_dependency": False,
        "secret_values_written": False,
    }


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    state_path = root / "state" / "live-preflight.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        receipt = run_live_verification(root)
        state_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(receipt, sort_keys=True))
        return 0
    except LiveVerificationFailure as exc:
        receipt = {
            "status": "FAILED",
            "category": exc.category,
            "failed_check": exc.check,
            "error": redact(str(exc)),
            "secret_values_written": False,
        }
    except Exception as exc:  # production boundary: always create a sanitized receipt
        receipt = {
            "status": "FAILED",
            "category": "APPLICATION",
            "failed_check": "unexpected-error",
            "error": redact(f"{type(exc).__name__}: {exc}"),
            "secret_values_written": False,
        }
    state_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
