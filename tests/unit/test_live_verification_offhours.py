from __future__ import annotations

from pathlib import Path

import pytest

from scripts.verify_live import LiveVerificationFailure, run_live_verification


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload


class ClosedMarketProvider:
    def market_clock(self) -> dict:
        return {"clock": {"state": "closed"}}


class OfflineProvider:
    def market_clock(self) -> dict:
        raise RuntimeError("Tradier authentication failed")


class SixStrategyRegistry:
    def all(self) -> list[object]:
        return [object() for _ in range(6)]


class EmptyLocalUniverse:
    def active(self) -> list[dict]:
        return []


class OffHoursApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.provider = ClosedMarketProvider()
        self.registry = SixStrategyRegistry()
        self.universe = EmptyLocalUniverse()


class DegradedProviderApplication(OffHoursApplication):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.provider = OfflineProvider()


class UnsafeProvider(ClosedMarketProvider):
    def place_order(self) -> None:
        raise AssertionError("The verifier must never call a write method")


class UnsafeApplication(OffHoursApplication):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.provider = UnsafeProvider()


def _configure_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    values = {
        "DISCORD_BOT_TOKEN": "test-token",
        "DISCORD_GUILD_ID": "guild-1",
        "DISCORD_OWNER_USER_ID": "owner-1",
        "TRADIER_ACCESS_TOKEN": "tradier-token",
        "TRADIER_ENVIRONMENT": "paper",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)


def _discord_get(url: str, **_: object) -> FakeResponse:
    if url.endswith("/users/@me"):
        return FakeResponse({"id": "bot-1"})
    if url.endswith("/guilds/guild-1"):
        return FakeResponse({"id": "guild-1", "owner_id": "owner-1"})
    raise AssertionError(f"Unexpected URL: {url}")


def test_closed_market_and_empty_universe_do_not_fail_installation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_environment(monkeypatch)

    result = run_live_verification(
        tmp_path,
        application_factory=OffHoursApplication,
        http_get=_discord_get,
        load_environment=False,
    )

    assert result["status"] == "PASS"
    assert result["tradier_live_status"] == "PASS"
    assert result["market_state"] == "closed"
    assert result["universe_count"] == 0
    assert result["strategy_registry_count"] == 6
    assert result["controlled_scan_performed"] is False
    assert result["option_chain_required"] is False
    assert result["market_open_required"] is False
    assert result["brokerage_write_request"] is False


def test_tradier_connectivity_failure_is_visible_but_does_not_erase_installation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_environment(monkeypatch)

    result = run_live_verification(
        tmp_path,
        application_factory=DegradedProviderApplication,
        http_get=_discord_get,
        load_environment=False,
    )

    assert result["status"] == "PASS"
    assert result["tradier_live_status"] == "DEGRADED"
    assert result["tradier_clock"] is False
    assert result["market_state"] == "unavailable"
    assert result["discord_live_status"] == "PASS"
    assert result["warnings"][0]["category"] == "AUTHENTICATION"
    assert result["warnings"][0]["check"] == "tradier-market-clock"
    assert "authentication failed" in result["warnings"][0]["error"].lower()


def test_live_verifier_rejects_provider_write_methods(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure_environment(monkeypatch)

    with pytest.raises(LiveVerificationFailure) as failure:
        run_live_verification(
            tmp_path,
            application_factory=UnsafeApplication,
            http_get=_discord_get,
            load_environment=False,
        )

    assert failure.value.category == "APPLICATION"
    assert failure.value.check == "read-only-provider-boundary"
    assert "place_order" in str(failure.value)
