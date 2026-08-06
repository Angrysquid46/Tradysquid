from __future__ import annotations

import asyncio
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tradysquid.app import Application


ROOT = Path(__file__).resolve().parents[2]


def test_discord_readiness_timeout_exceeds_old_two_minute_cutoff() -> None:
    signature = inspect.signature(Application._wait_for_discord_readiness)
    assert signature.parameters["timeout"].default == 270


def test_start_script_returns_instead_of_exiting_parent_setup_host() -> None:
    source = (ROOT / "scripts" / "start.ps1").read_text(encoding="utf-8")
    assert "$ReadinessTimeoutSeconds = 285" in source
    assert "return\n" in source
    assert "exit 0" not in source


def test_setup_entry_guarantees_fallback_receipt_and_captures_body_streams() -> None:
    source = (ROOT / "scripts" / "setup_entry.ps1").read_text(encoding="utf-8")
    assert "setup-body-stdout.log" in source
    assert "setup-body-stderr.log" in source
    assert "Test-CurrentBodyReceipt" in source
    assert "Get-FallbackFailureDetails" in source
    assert "Write-EarlyFailureReceipt" in source
    assert "Setup body exited with code" in source


def test_application_fails_immediately_from_discord_failure_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "test-token")
    state = tmp_path / "state"
    state.mkdir(parents=True)
    (state / "discord-readiness.json").write_text(
        json.dumps({"status": "FAILED", "error": "card channel missing"}),
        encoding="utf-8",
    )

    app = Application.__new__(Application)
    app.root = tmp_path
    app.publisher = SimpleNamespace(ready=False)
    app.discord = SimpleNamespace(ready=False, start=_sleeping_discord)
    app.discord_task = None

    with pytest.raises(RuntimeError, match="card channel missing"):
        asyncio.run(app._wait_for_discord_readiness(timeout=2))


async def _sleeping_discord(_token: str) -> None:
    await asyncio.sleep(60)
