from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_runtime_cleanup_only_terminates_repository_python_processes() -> None:
    cleanup = read("scripts/clean_previous_runtime.ps1")
    assert "@('python.exe', 'pythonw.exe')" in cleanup
    assert "@('python.exe','pythonw.exe','powershell.exe','cmd.exe')" not in cleanup
    assert "installer itself or its parent wrapper" in cleanup


def test_setup_uses_an_isolated_virtual_environment() -> None:
    setup = read("scripts/setup.ps1")
    assert ".venv-tradysquid" in setup
    assert "isolated-virtual-environment" in setup
    assert "py -3.12 -m venv $VenvPath" in setup
    assert "Remove-IncompleteVenv" in setup


def test_start_and_update_use_the_same_isolated_environment() -> None:
    start = read("scripts/start.ps1")
    update = read("scripts/update.ps1")
    expected = ".venv-tradysquid\\Scripts\\python.exe"
    assert expected in start
    assert expected in update


def test_start_requires_discord_and_publishing_readiness() -> None:
    start = read("scripts/start.ps1")
    assert "discord-readiness.json" in start
    assert "discord-publishing-bootstrap.json" in start
    assert "discord_publishing_ready" in start
    assert "slash_commands_synchronized" in start


def test_isolated_environment_is_not_tracked() -> None:
    gitignore = read(".gitignore")
    assert ".venv-tradysquid/" in gitignore.splitlines()
