"""Load the ignored local .env file, install runtime hooks, then run one script."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
SCRIPT_OVERRIDES = {
    "discord_command_bot.py": "discord_command_bot_public.py",
    "local_information_engine.py": "local_information_engine_bootstrap.py",
    "local_information_engine_public.py": "local_information_engine_bootstrap.py",
    "register_discord_commands.py": "register_discord_commands_public.py",
    "sync_discord_structure.py": "sync_discord_structure_reports.py",
    "sync_discord_structure_public.py": "sync_discord_structure_reports.py",
}


def load_env() -> None:
    if not ENV_PATH.exists():
        raise SystemExit("Missing .env. Copy .env.example to .env and fill it in.")
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def install_runtime_overrides(
    *,
    include_discord_upgrade_commands: bool = False,
    include_information_engine: bool = False,
) -> None:
    import ford_scan
    import github_upgrade_bridge
    import github_upgrade_bridge_runtime
    import journal_contract
    import network_compat
    import openai_discord_patch
    import performance_scorecards
    import runtime_contract
    import shared_upgrade_lifecycle
    import upgrade_batch_44

    network_compat.install()
    runtime_contract.install_safe_intraday_history(ford_scan)
    runtime_contract.install_recovery_bridge(github_upgrade_bridge)
    github_upgrade_bridge_runtime.install()
    journal_contract.install()
    performance_scorecards.install()
    upgrade_batch_44.install_universe_policy()
    upgrade_batch_44.install_learning_extensions()
    shared_upgrade_lifecycle.install()
    openai_discord_patch.install()

    if include_information_engine:
        runtime_contract.install_information_engine()

    if include_discord_upgrade_commands:
        import github_upgrade_patch

        github_upgrade_patch.install()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python run_with_env.py <script.py> [arguments...]")
    load_env()
    requested = SCRIPT_OVERRIDES.get(Path(sys.argv[1]).name.casefold(), sys.argv[1])
    target = (ROOT / requested).resolve()
    if target.parent != ROOT or not target.is_file() or target.suffix != ".py":
        raise SystemExit("Target must be a Python file in this repository.")

    install_runtime_overrides(
        include_discord_upgrade_commands=(target.name.casefold() == "discord_command_bot_public.py"),
        include_information_engine=(target.name.casefold() == "local_information_engine_bootstrap.py"),
    )
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
