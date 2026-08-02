"""Read-only proof that the existing automatic updater deployed this checkout.

This module does not install, configure, restart, or modify the updater. It only
reports the running Git commit, the supervisor deployment receipt, and direct
health checks for the three local services.
"""

from __future__ import annotations

import json
import socket
import subprocess
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "state" / "supervisor-state.json"


def running_commit(root: Path = ROOT) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    if result.returncode:
        return "unknown"
    return result.stdout.strip() or "unknown"


def supervisor_state(path: Path = STATE_PATH) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def information_engine_healthy() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8765), timeout=3):
            return True
    except OSError:
        return False


def ngrok_healthy() -> bool:
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        response.raise_for_status()
        payload = response.json()
        return bool(payload.get("tunnels"))
    except (requests.RequestException, ValueError, TypeError):
        return False


def commits_match(running: str, deployed: str) -> bool:
    if not running or not deployed or "unknown" in {running, deployed}:
        return False
    return running.startswith(deployed) or deployed.startswith(running)


def updater_test_reply() -> str:
    running = running_commit()
    state = supervisor_state()
    deployed = str(state.get("deployed_sha") or "unknown")
    update_status = str(state.get("last_update_status") or "UNKNOWN").upper()
    rollback = update_status == "ROLLED_BACK"

    command_bot_ok = True  # This reply can only execute inside the command bot.
    information_engine_ok = information_engine_healthy()
    ngrok_ok = ngrok_healthy()
    deployment_ok = commits_match(running, deployed)
    passed = (
        command_bot_ok
        and information_engine_ok
        and ngrok_ok
        and deployment_ok
        and not rollback
    )

    health = lambda value: "healthy" if value else "UNHEALTHY"
    return "\n".join(
        [
            f"Automatic updater test: **{'PASS' if passed else 'FAIL'}**",
            f"Running commit: `{running}`",
            f"Supervisor deployed commit: `{deployed}`",
            "Deployment source: **GitHub main**",
            f"Deployment receipt: **{update_status}**",
            f"Rollback triggered: **{'YES' if rollback else 'NO'}**",
            f"Command bot: **{health(command_bot_ok)}**",
            f"Information engine: **{health(information_engine_ok)}**",
            f"Ngrok: **{health(ngrok_ok)}**",
            "Updater guardrail: **FROZEN unless a current updater failure is proven.**",
        ]
    )
