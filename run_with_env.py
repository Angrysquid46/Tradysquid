"""Load the ignored local .env file, install runtime overrides, then run a script."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import Any, Callable

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

# These were temporary migration, acceptance, or reporting jobs. They are not
# part of the bot, scanner, information engine, updater, or rollback path.
RETIRED_RUNTIME_JOBS = {
    "upgrade-request-migration",
    "upgrade-batch-44-acceptance",
    "upgrade-lifecycle-dashboard",
    "applied-upgrades-dashboard",
    "market-hours-upgrade-review",
}
RECOVERED_DIAGNOSTIC_STATES = {"RECOVERED", "RESOLVED", "VERIFIED"}


def load_env() -> None:
    if not ENV_PATH.exists():
        raise SystemExit("Missing .env. Copy .env.example to .env and fill it in.")
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def _dedupe_and_retire_jobs(engine: Any) -> None:
    """Keep exactly one copy of each current job and remove completed verifiers."""
    rebuilt = []
    seen: set[str] = set()
    for job in engine.JOBS:
        if job.name in RETIRED_RUNTIME_JOBS or job.name in seen:
            continue
        rebuilt.append(job)
        seen.add(job.name)
    engine.JOBS = rebuilt


def _install_recovery_aware_github_bridge(bridge: Any) -> None:
    """Make recovered automatic incidents factual and close empty repair batches."""
    original_body: Callable[[dict[str, Any], int], str] = bridge._diagnostic_body
    original_add: Callable[[dict[str, Any]], dict[str, Any]] = bridge.add_or_update_diagnostic

    if getattr(bridge, "_tradysquid_recovery_patch", False):
        return

    def diagnostic_body(report: dict[str, Any], sequence: int) -> str:
        body = original_body(report, sequence)
        status = str(report.get("status") or "").upper()
        if status not in RECOVERED_DIAGNOSTIC_STATES:
            return body
        body = body.replace(
            "**Status:** PENDING BATCH REVIEW",
            f"**Status:** {status}",
        )
        body = body.replace(
            "**Next action:** Owner marks the shared batch upgrade-ready; maintainer reviews and implements the repair.",
            "**Next action:** No owner action. The incident recovered and remains in history.",
        )
        return body

    def close_if_recovered() -> None:
        try:
            issue = bridge._find_open_batch()
            if not issue:
                return
            issue_number = int(issue["number"])
            comments = bridge._request_comments(issue_number)
            if not comments:
                return
            automatic = 0
            for comment in comments:
                body = str(comment.get("body") or "")
                source = bridge._field(body, "Source", "OWNER REQUEST").upper()
                if source != "AUTOMATIC DIAGNOSTIC":
                    return
                automatic += 1
                status = bridge._field(
                    body, "Status", "PENDING BATCH REVIEW"
                ).strip("*").upper()
                if status not in RECOVERED_DIAGNOSTIC_STATES:
                    return
            if not automatic:
                return
            bridge._request(
                "POST",
                f"/issues/{issue_number}/comments",
                payload={
                    "body": (
                        "## Automatic diagnostic batch recovered\n\n"
                        "Every automatic request is recovered, resolved, or verified. "
                        "No owner request was present, so this batch closed automatically."
                    )
                },
            )
            bridge._request(
                "PATCH",
                f"/issues/{issue_number}",
                payload={
                    "state": "closed",
                    "title": f"[Tradysquids Upgrade Batch] RECOVERED · #{issue_number}",
                },
            )
        except Exception:
            # GitHub is external. A failed cleanup must never block the engine.
            return

    def add_or_update_diagnostic(report: dict[str, Any]) -> dict[str, Any]:
        result = original_add(report)
        close_if_recovered()
        return result

    bridge._diagnostic_body = diagnostic_body
    bridge.add_or_update_diagnostic = add_or_update_diagnostic
    bridge.REQUEST_TIMEOUT_SECONDS = 12
    bridge._tradysquid_recovery_patch = True


def install_runtime_overrides(
    *,
    include_discord_upgrade_commands: bool = False,
    include_upgrade_batch_engine: bool = False,
) -> None:
    """Install shared behavior, optional Discord commands, and current jobs."""
    import network_compat

    network_compat.install()

    import github_upgrade_bridge
    import github_upgrade_bridge_runtime
    import journal_contract
    import openai_discord_patch
    import performance_scorecards
    import shared_upgrade_lifecycle
    import upgrade_batch_44

    _install_recovery_aware_github_bridge(github_upgrade_bridge)
    github_upgrade_bridge_runtime.install()
    journal_contract.install()
    performance_scorecards.install()
    upgrade_batch_44.install_universe_policy()
    upgrade_batch_44.install_learning_extensions()
    shared_upgrade_lifecycle.install()
    openai_discord_patch.install()

    if include_upgrade_batch_engine:
        import diagnostic_review_runtime
        import diagnostic_upgrade_system
        import market_calendar_runtime
        import outbound_connectivity_runtime
        import scheduler_diagnostic_runtime
        import supervisor_diagnostic_runtime

        # Install the actual market-information feature jobs from the completed
        # upgrade, then only the diagnostics needed to protect the core runtime.
        upgrade_batch_44.install_engine()
        diagnostic_upgrade_system.install()
        market_calendar_runtime.install()
        supervisor_diagnostic_runtime.install()
        scheduler_diagnostic_runtime.install()
        diagnostic_review_runtime.install()
        outbound_connectivity_runtime.install()
        _dedupe_and_retire_jobs(upgrade_batch_44._engine())

    if include_discord_upgrade_commands:
        import github_upgrade_patch

        github_upgrade_patch.install()


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python run_with_env.py <script.py> [arguments...]")
    load_env()
    requested = str(sys.argv[1])
    requested = SCRIPT_OVERRIDES.get(Path(requested).name.casefold(), requested)
    target = (ROOT / requested).resolve()
    if target.parent != ROOT or not target.is_file() or target.suffix != ".py":
        raise SystemExit("Target must be a Python file in this repository.")

    install_runtime_overrides(
        include_discord_upgrade_commands=(
            target.name.casefold() == "discord_command_bot_public.py"
        ),
        include_upgrade_batch_engine=(
            target.name.casefold() == "local_information_engine_bootstrap.py"
        ),
    )
    sys.argv = [str(target), *sys.argv[2:]]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()
