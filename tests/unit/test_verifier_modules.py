from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.verify_live import run_live_verification


ROOT = Path(__file__).resolve().parents[2]


def test_packaging_includes_the_scripts_package() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert 'include = ["scripts*"]' in pyproject
    assert (ROOT / "scripts" / "__init__.py").is_file()


def test_setup_installs_project_and_runs_verifiers_as_modules() -> None:
    setup = (ROOT / "scripts" / "setup.ps1").read_text(encoding="utf-8")
    assert "-m pip install --editable ." in setup
    assert "-m scripts.verify_installation" in setup
    assert "-m scripts.verify_live" in setup
    assert "verify_installation.py')" not in setup
    assert "verify_live.py')" not in setup
    assert "Push-Location $Root" in setup
    assert ".venv-tradysquid" in setup
    assert "'.venv\\Scripts\\python.exe'" not in setup


def test_installation_verifier_runs_from_external_working_directory(tmp_path: Path) -> None:
    expected_venv = (ROOT / ".venv-tradysquid").resolve()
    assert Path(sys.prefix).resolve() == expected_venv

    environment = os.environ.copy()
    environment.update(
        {
            "DISCORD_BOT_TOKEN": "test-discord-secret-not-for-output",
            "DISCORD_GUILD_ID": "123456789",
            "DISCORD_OWNER_USER_ID": "987654321",
            "TRADIER_ACCESS_TOKEN": "test-tradier-secret-not-for-output",
            "TRADIER_ENVIRONMENT": "production",
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "scripts.verify_installation"],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    output = result.stdout + result.stderr
    assert "test-discord-secret-not-for-output" not in output
    assert "test-tradier-secret-not-for-output" not in output
    receipt = json.loads([line for line in result.stdout.splitlines() if line.strip()][-1])
    assert receipt["status"] == "PASS"
    assert Path(receipt["python_executable"]).resolve() == Path(sys.executable).resolve()
    assert Path(receipt["virtual_environment"]).resolve() == expected_venv
    assert Path(receipt["scanner_path"]).resolve().is_relative_to(ROOT)


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.status_code = 200
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _FakeProvider:
    def market_clock(self) -> dict[str, Any]:
        return {"clock": {"state": "closed"}}


class _FakeRegistry:
    def all(self) -> list[dict[str, str]]:
        return [{"strategy": str(index)} for index in range(15)]


class _FakeUniverse:
    def active(self) -> list[dict[str, str]]:
        return [{"symbol": "TEST"}]


class _FakeScanner:
    def scan_symbol(self, symbol: str, trigger: str) -> list[dict[str, str]]:
        raise AssertionError(
            f"Live verification must not scan {symbol!r} with trigger {trigger!r}"
        )


class _FakeApplication:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.provider = _FakeProvider()
        self.registry = _FakeRegistry()
        self.universe = _FakeUniverse()
        self.scanner = _FakeScanner()

    def initialize_universe(self) -> list[str]:
        raise AssertionError("Live verification must not refresh the universe")


def test_live_verifier_module_uses_mocked_read_only_services(monkeypatch, tmp_path: Path) -> None:
    values = {
        "DISCORD_BOT_TOKEN": "mock-discord-token",
        "DISCORD_GUILD_ID": "123456789",
        "DISCORD_OWNER_USER_ID": "987654321",
        "TRADIER_ACCESS_TOKEN": "mock-tradier-token",
        "TRADIER_ENVIRONMENT": "production",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    def fake_get(url: str, **_: Any) -> _FakeResponse:
        if url.endswith("/users/@me"):
            return _FakeResponse({"id": "bot-id"})
        return _FakeResponse({"id": "123456789", "owner_id": "987654321"})

    receipt = run_live_verification(
        tmp_path,
        application_factory=_FakeApplication,
        http_get=fake_get,
        load_environment=False,
    )
    rendered = json.dumps(receipt, sort_keys=True)
    assert receipt["status"] == "PASS"
    assert receipt["strategy_decisions"] == 15
    assert receipt["tradier_read_only"] is True
    assert receipt["market_state"] == "closed"
    assert receipt["controlled_scan_performed"] is False
    assert receipt["option_chain_required"] is False
    assert receipt["market_open_required"] is False
    assert receipt["brokerage_write_request"] is False
    assert receipt["second_computer_request"] is False
    assert receipt["lan_service_dependency"] is False
    assert "mock-discord-token" not in rendered
    assert "mock-tradier-token" not in rendered
