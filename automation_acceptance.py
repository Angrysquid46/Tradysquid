"""Prove Tradysquids automation on the actual Windows laptop.

The installer calls this through run_with_env.py and fails unless every check
passes. The test deliberately stops the supervisor and launcher, triggers the
independent Windows watchdog, waits for the entire managed stack to recover,
then verifies Git state, service health, the local status command, Discord sync,
and the visible ascending Learning Center order.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

import discord_command_bot as command_bot
import dynamic_universe
import ford_scan
from learning_center_catalog import LEARNING_CHANNEL_ORDER
from strict_learning_order import category_and_children, normalized, ordered_children

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
STATE_PATH = STATE_DIR / "supervisor-state.json"
REPORT_PATH = STATE_DIR / "automation-acceptance.json"
TASK_NAME = "Tradysquids Supervisor Watchdog"
WATCHDOG_SCRIPT = ROOT / "ENSURE-SUPERVISOR.ps1"
SUPERVISOR_SCRIPT = ROOT / "run_supervisor.py"
LAUNCHER_CMD = ROOT / "START-SUPERVISOR.cmd"
LAUNCHER_VBS = ROOT / "start_supervisor_hidden.vbs"
RECOVERY_TIMEOUT_SECONDS = 210


class AcceptanceFailure(RuntimeError):
    pass


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def run(command: list[str], *, timeout: int = 180, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if check and result.returncode:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise AcceptanceFailure(f"{' '.join(command)}: {detail[-1800:]}")
    return result


def powershell(script: str, *, timeout: int = 120, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        timeout=timeout,
        check=check,
    )


def git_value(*arguments: str) -> str:
    return run(["git", *arguments], check=True).stdout.strip()


def verify_checkout_current() -> dict[str, str]:
    branch = git_value("rev-parse", "--abbrev-ref", "HEAD")
    if branch != "main":
        raise AcceptanceFailure(f"Laptop checkout is on {branch or 'unknown'}, not main.")
    run(["git", "fetch", "--quiet", "origin", "main"], timeout=180, check=True)
    local = git_value("rev-parse", "HEAD")
    remote = git_value("rev-parse", "origin/main")
    if local != remote:
        raise AcceptanceFailure(
            f"Laptop is behind GitHub after fetch: local {local[:12]}, remote {remote[:12]}."
        )
    return {"branch": branch, "local_sha": local, "remote_sha": remote}


def verify_watchdog_task() -> dict[str, Any]:
    xml = run(["schtasks.exe", "/Query", "/TN", TASK_NAME, "/XML"], timeout=60, check=True).stdout
    lowered = xml.casefold()
    if str(WATCHDOG_SCRIPT).casefold() not in lowered:
        raise AcceptanceFailure("The watchdog task points at the wrong repository or script.")
    if "pt5m" not in lowered:
        raise AcceptanceFailure("The watchdog task is not configured for a five-minute interval.")
    # Task Scheduler omits the Enabled element when it uses the schema default
    # of true. Only an explicit false value means the task is disabled.
    if "<enabled>false</enabled>" in lowered:
        raise AcceptanceFailure("The watchdog task is disabled.")
    return {"task_name": TASK_NAME, "interval": "PT5M", "enabled": True}


def supervisor_pids() -> list[int]:
    escaped = re.escape(str(SUPERVISOR_SCRIPT))
    result = powershell(
        rf"""
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {{ $_.CommandLine -and $_.CommandLine -match '{escaped}' -and $_.Name -match '^python(w)?\.exe$' }} |
  ForEach-Object {{ $_.ProcessId }}
""",
        timeout=45,
    )
    return [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]


def stop_supervisor_and_launcher() -> list[int]:
    patterns = [
        re.escape(str(SUPERVISOR_SCRIPT)),
        re.escape(str(LAUNCHER_CMD)),
        re.escape(str(LAUNCHER_VBS)),
    ]
    pattern_lines = ",\n".join(f"  '{item}'" for item in patterns)
    result = powershell(
        rf"""
$patterns = @(
{pattern_lines}
)
$matches = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
  Where-Object {{
    $_.ProcessId -ne {os.getpid()} -and $_.CommandLine -and
    ($patterns | Where-Object {{ $_.CommandLine -match $_ }}).Count -gt 0
  }}
$ids = @($matches | ForEach-Object {{ $_.ProcessId }})
$matches | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
$ids | ForEach-Object {{ $_ }}
""",
        timeout=60,
        check=True,
    )
    stopped = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        # The persistent launcher may replace the killed supervisor immediately.
        # Prove the original processes died without requiring an artificial
        # zero-process gap that treats fast automatic recovery as failure.
        running = set(supervisor_pids())
        if not running.intersection(stopped):
            return stopped
        time.sleep(1)
    raise AcceptanceFailure("The original supervisor processes remained alive after the deliberate stop.")


def trigger_watchdog() -> None:
    run(["schtasks.exe", "/Run", "/TN", TASK_NAME], timeout=60, check=True)


def port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=2):
            return True
    except OSError:
        return False


def command_bot_healthy() -> bool:
    try:
        return requests.get("http://127.0.0.1:8080/health", timeout=3).ok
    except requests.RequestException:
        return False


def ngrok_healthy() -> bool:
    try:
        response = requests.get("http://127.0.0.1:4040/api/tunnels", timeout=3)
        response.raise_for_status()
        return bool(response.json().get("tunnels"))
    except (requests.RequestException, ValueError, TypeError):
        return False


def read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def heartbeat_fresh(state: dict[str, Any], max_age_seconds: int = 120) -> bool:
    value = str(state.get("supervisor_heartbeat_at") or "")
    if not value:
        return False
    try:
        heartbeat = datetime.fromisoformat(value)
    except ValueError:
        return False
    if heartbeat.tzinfo is None:
        heartbeat = heartbeat.astimezone()
    return 0 <= (datetime.now().astimezone() - heartbeat).total_seconds() <= max_age_seconds


def service_health() -> dict[str, bool]:
    return {
        "command-bot": command_bot_healthy(),
        "information-engine": port_open("127.0.0.1", 8765),
        "ngrok": ngrok_healthy(),
    }


def wait_for_full_recovery(expected_sha: str) -> dict[str, Any]:
    deadline = time.monotonic() + RECOVERY_TIMEOUT_SECONDS
    latest_health = service_health()
    latest_state: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest_health = service_health()
        latest_state = read_state()
        local_state_sha = str(latest_state.get("local_sha") or latest_state.get("deployed_sha") or "")
        if (
            supervisor_pids()
            and all(latest_health.values())
            and heartbeat_fresh(latest_state)
            and local_state_sha.startswith(expected_sha[:12])
        ):
            return {
                "supervisor_pids": supervisor_pids(),
                "service_health": latest_health,
                "heartbeat": latest_state.get("supervisor_heartbeat_at"),
                "version": local_state_sha,
                "recovered": True,
            }
        time.sleep(3)
    raise AcceptanceFailure(
        "Full recovery did not occur within the timeout. "
        f"Last health={latest_health}; state={latest_state}."
    )


def run_discord_sync() -> str:
    result = run(
        [sys.executable, str(ROOT / "run_with_env.py"), str(ROOT / "sync_discord_structure_public.py"), "--apply"],
        timeout=1200,
        check=True,
    )
    output = (result.stdout or "").strip()
    if "strictly ordered" not in output.casefold():
        raise AcceptanceFailure("Discord sync returned success without strict order verification.")
    return output[-3500:]


def verify_visible_learning_order() -> dict[str, Any]:
    tracker = ford_scan.DiscordTracker(ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID)
    if not tracker.enabled:
        raise AcceptanceFailure("Discord bot token and guild ID are required for order verification.")
    _, children = category_and_children(tracker)
    visible = [normalized(item.get("name") or "") for item in ordered_children(children)]
    expected = list(LEARNING_CHANNEL_ORDER)
    actual = visible[: len(expected)]
    if actual != expected:
        raise AcceptanceFailure(
            "Discord returned the wrong Learning Center order. "
            f"Expected: {', '.join(expected)}. Actual: {', '.join(actual)}."
        )
    numbers = [int(match.group(1)) for name in actual if (match := re.match(r"^(\d{2})-", name))]
    if numbers != list(range(1, 28)):
        raise AcceptanceFailure(f"Discord returned lesson numbers {numbers}, not 1 through 27.")
    return {"actual": actual, "numbers": numbers, "extras_after_official_channels": max(0, len(visible) - len(expected))}


def verify_status_logic() -> dict[str, str]:
    active = dynamic_universe.initialize()
    ticker = active[0] if active else "F"
    text = command_bot.status_reply(ticker)
    if "Command service: **ONLINE**" not in text or "Tradysquids status" not in text:
        raise AcceptanceFailure("The local /status command logic did not return a valid status response.")
    return {"ticker": ticker, "result": "status reply generated"}


def post_report(message: str) -> None:
    try:
        tracker = ford_scan.DiscordTracker(
            ford_scan.DISCORD_BOT_TOKEN, ford_scan.DISCORD_GUILD_ID
        )
        channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
        channel = next((item for item in channels if str(item.get("name") or "").casefold() == "system-health"), None)
        if channel and channel.get("id"):
            title = message.splitlines()[0].strip("# *✅❌ ")
            tracker.upsert_singleton_message(
                str(channel["id"]), message[:1900], title
            )
    except (ford_scan.DiscordError, ValueError, TypeError):
        pass


def write_report(report: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    temporary = REPORT_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(REPORT_PATH)


def run_acceptance() -> dict[str, Any]:
    if os.name != "nt":
        raise AcceptanceFailure("Automation acceptance must run on the Windows laptop.")
    report: dict[str, Any] = {"version": 1, "status": "RUNNING", "started_at": now_iso(), "checks": {}}
    write_report(report)
    checkout = verify_checkout_current()
    report["checks"]["checkout"] = checkout
    report["checks"]["watchdog"] = verify_watchdog_task()
    report["checks"]["discord_sync"] = run_discord_sync()
    report["checks"]["discord_order"] = verify_visible_learning_order()
    report["checks"]["status_before_recovery"] = verify_status_logic()
    report["checks"]["stopped_process_ids"] = stop_supervisor_and_launcher()
    trigger_watchdog()
    report["checks"]["recovery"] = wait_for_full_recovery(checkout["local_sha"])
    report["checks"]["checkout_after_recovery"] = verify_checkout_current()
    report["checks"]["discord_order_after_recovery"] = verify_visible_learning_order()
    report["checks"]["status_after_recovery"] = verify_status_logic()
    report["status"] = "PASSED"
    report["completed_at"] = now_iso()
    write_report(report)
    post_report(
        "✅ **Tradysquids automation acceptance PASSED**\n"
        f"Version `{checkout['local_sha'][:12]}`\n"
        "• Watchdog installed and enabled\n"
        "• Supervisor deliberately stopped and automatically restored\n"
        "• command-bot, information-engine, and ngrok verified healthy\n"
        "• local status response verified\n"
        "• Discord Learning Center verified in ascending 01 → 27 order"
    )
    return report


def main() -> int:
    try:
        report = run_acceptance()
    except Exception as exc:
        report = {
            "version": 1,
            "status": "FAILED",
            "completed_at": now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
        }
        write_report(report)
        post_report(
            "❌ **Tradysquids automation acceptance FAILED**\n"
            f"```{str(exc)[:1400]}```\n"
            "Installation is not considered complete."
        )
        print(report["error"], file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
