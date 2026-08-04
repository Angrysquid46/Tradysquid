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


def test_setup_launcher_supplies_required_attempt_and_commit_parameters() -> None:
    launcher = read("SETUP-AND-START.cmd")
    assert "scripts\\setup_entry.ps1" in launcher
    assert "-AttemptId" in launcher
    assert "-ExpectedCleanCommit" in launcher
    assert "[guid]::NewGuid().ToString()" in launcher
    assert "git -C" in launcher


def test_start_and_update_use_the_same_isolated_environment() -> None:
    start = read("scripts/start.ps1")
    update = read("scripts/update.ps1")
    expected = ".venv-tradysquid\\Scripts\\python.exe"
    assert expected in start
    assert expected in update


def test_start_requires_discord_and_publishing_readiness() -> None:
    start = read("START-TRADYSQUID.cmd")
    assert "discord-readiness.json" in start
    assert "discord-publishing-bootstrap.json" in start
    assert "slash_commands_synchronized" in start
    assert "persistent_cards.failed" in start
    assert "TRADYSQUID IS RUNNING" in start


def test_ordinary_startup_is_direct_and_has_no_maintenance_side_effects() -> None:
    start = read("START-TRADYSQUID.cmd")
    assert "\'-m\',\'tradysquid.app\'" in start
    forbidden = (
        "git ", "pytest", "pip install", "worktree", "rollback",
        "schtasks", "setup.ps1", "update.ps1", "robocopy",
    )
    for value in forbidden:
        assert value not in start.lower()


def test_ordinary_startup_handles_environment_and_process_states() -> None:
    start = read("START-TRADYSQUID.cmd")
    assert 'if not exist "%ROOT%.env"' in start
    assert ".venv-tradysquid\\Scripts\\python.exe" in start
    assert "tradysquid.pid.json" in start
    assert "TRADYSQUID IS ALREADY RUNNING" in start
    assert "Remove-Item -LiteralPath $p -Force" in start
    assert "timed out after 300 seconds" in start


def test_isolated_environment_is_not_tracked() -> None:
    gitignore = read(".gitignore")
    assert ".venv-tradysquid/" in gitignore.splitlines()
