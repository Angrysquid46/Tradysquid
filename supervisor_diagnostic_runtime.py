"""Windows ownership checks for the one active simple supervisor tree."""

from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Callable

import diagnostic_upgrade_system as diagnostics

_INSTALLED = False
_BASE_COLLECT: Callable[[Any], tuple[list[diagnostics.HealthCheck], dict[str, dict[str, Any]]]] | None = None
TASK_RESULT_RUNNING = 0x41301


def supervisor_process_check() -> diagnostics.HealthCheck:
    if os.name != "nt":
        return diagnostics.HealthCheck(
            "supervisor-process-ownership",
            True,
            "supervisor",
            "single supervisor ownership tree",
            "Windows process ownership check is not applicable on this platform.",
            severity="INFO",
            runtime_target="run_supervisor_simple.py",
        )
    script = r"""
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$items = @($all |
  Where-Object {
    $_.Name -match '^python(w)?\.exe$' -and $_.CommandLine -and
    $_.CommandLine -match 'run_supervisor_simple\.py'
  } |
  Select-Object ProcessId, ParentProcessId, CommandLine)
$listener = Get-NetTCPConnection -State Listen -LocalPort 8876 -ErrorAction SilentlyContinue |
  Select-Object -First 1
$owner = if ($listener) { [int]$listener.OwningProcess } else { 0 }
$ownerTree = [System.Collections.Generic.HashSet[int]]::new()
$current = $owner
while ($current -gt 0 -and $ownerTree.Add([int]$current)) {
  $item = $all | Where-Object { $_.ProcessId -eq $current } | Select-Object -First 1
  if (-not $item) { break }
  $current = [int]$item.ParentProcessId
}
[pscustomobject]@{
  Processes = $items
  PortOwner = $owner
  OwnerTreeIds = @($ownerTree)
} | ConvertTo-Json -Compress -Depth 6
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return diagnostics.HealthCheck(
            "supervisor-process-ownership",
            False,
            "supervisor",
            "single supervisor ownership tree",
            f"Process inspection failed: {type(exc).__name__}: {exc}",
            severity="WARNING",
            runtime_target="run_supervisor_simple.py and port 8876",
        )
    raw = (result.stdout or "").strip()
    try:
        payload = json.loads(raw) if raw else {}
    except (ValueError, TypeError, json.JSONDecodeError):
        payload = {}
    processes = payload.get("Processes") if isinstance(payload, dict) else []
    if isinstance(processes, dict):
        processes = [processes]
    items = [item for item in processes if isinstance(item, dict)] if isinstance(processes, list) else []
    pids = [int(item.get("ProcessId") or 0) for item in items]
    port_owner = int(payload.get("PortOwner") or 0) if isinstance(payload, dict) else 0
    raw_tree = payload.get("OwnerTreeIds") if isinstance(payload, dict) else []
    if isinstance(raw_tree, (int, str)):
        raw_tree = [raw_tree]
    owner_tree = sorted(
        {
            int(value or 0)
            for value in (raw_tree if isinstance(raw_tree, list) else [])
            if int(value or 0) > 0
        }
    )
    foreign = sorted(pid for pid in pids if pid not in owner_tree)
    passed = (
        result.returncode == 0
        and port_owner > 0
        and port_owner in pids
        and not foreign
    )
    return diagnostics.HealthCheck(
        "supervisor-process-ownership",
        passed,
        "supervisor",
        "single supervisor ownership tree",
        (
            f"matched supervisor processes={len(pids)}; matched PIDs={pids}; "
            f"owner tree PIDs={owner_tree}; foreign supervisor PIDs={foreign}; "
            f"port 8876 owner={port_owner or 'none'}"
        ),
        runtime_target="run_supervisor_simple.py ownership tree and port 8876",
        automatic_retry="watchdog preserves the healthy owner tree and removes only foreign supervisor trees",
        healthy_services="managed services remain independent during supervisor ownership repair",
        repair_objective="Leave exactly one supervisor ownership tree with its active interpreter owning port 8876.",
        acceptance_tests="One ownership tree contains the port-8876 owner and every matched supervisor process for at least two health intervals.",
        force_upgrade=False,
    )


def stop_flag_check() -> diagnostics.HealthCheck:
    path = diagnostics.ROOT / "state" / "supervisor-stop.flag"
    exists = path.exists()
    return diagnostics.HealthCheck(
        "supervisor-stop-flag",
        not exists,
        "supervisor",
        "stale stop flag",
        f"Unexpected stop flag exists at {path}." if exists else "No supervisor stop flag is present.",
        runtime_target="state/supervisor-stop.flag",
        automatic_retry="owner restart removes an unintended stale flag",
        repair_objective="Remove unintended stale stop state without creating duplicate supervisors.",
        acceptance_tests="The stop flag is absent while the supervisor is expected to run.",
        force_upgrade=False,
    )


def _watchdog_row_healthy(item: dict[str, Any]) -> bool:
    state = str(item.get("State") or "").casefold()
    result = int(item.get("LastTaskResult") or 0)
    if state in {"disabled", "unknown"}:
        return False
    if result == 0:
        return True
    return state == "running" and result == TASK_RESULT_RUNNING


def watchdog_check() -> diagnostics.HealthCheck:
    if os.name != "nt":
        return diagnostics.HealthCheck(
            "watchdog-task",
            True,
            "watchdog",
            "scheduled watchdog health",
            "Windows watchdog validation is not applicable on this platform.",
            severity="INFO",
            runtime_target="ENSURE-SUPERVISOR.ps1",
        )
    script = r"""
$tasks = @(Get-ScheduledTask -ErrorAction SilentlyContinue |
  Where-Object {$_.TaskName -match 'Tradysquid'})
if (-not $tasks) { exit 2 }
$rows = @($tasks | ForEach-Object {
  $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue
  [pscustomobject]@{
    TaskName = $_.TaskName
    State = [string]$_.State
    LastTaskResult = [int64]$info.LastTaskResult
    LastRunTime = [string]$info.LastRunTime
    NextRunTime = [string]$info.NextRunTime
  }
})
$rows | ConvertTo-Json -Compress
"""
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return diagnostics.HealthCheck(
            "watchdog-task",
            False,
            "watchdog",
            "scheduled watchdog health",
            f"Watchdog inspection failed: {type(exc).__name__}: {exc}",
            severity="WARNING",
            runtime_target="ENSURE-SUPERVISOR.ps1",
        )
    raw = (result.stdout or "").strip()
    try:
        payload = json.loads(raw) if raw else []
    except (ValueError, TypeError, json.JSONDecodeError):
        payload = []
    if isinstance(payload, dict):
        payload = [payload]
    rows = [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []
    healthy = [item for item in rows if _watchdog_row_healthy(item)]
    passed = result.returncode == 0 and bool(rows) and bool(healthy)
    return diagnostics.HealthCheck(
        "watchdog-task",
        passed,
        "watchdog",
        "scheduled watchdog health",
        (
            "; ".join(
                f"{item.get('TaskName')}: state={item.get('State')}, last_result={item.get('LastTaskResult')}, last={item.get('LastRunTime')}, next={item.get('NextRunTime')}"
                for item in rows
            )
            or "No Tradysquid watchdog task was found."
        ),
        severity="ERROR" if not rows else "WARNING",
        runtime_target="ENSURE-SUPERVISOR.ps1 scheduled task",
        automatic_retry="Windows Task Scheduler runs the watchdog on its configured cadence",
        repair_objective="Restore one enabled watchdog task that is either running normally or completed successfully.",
        acceptance_tests="The watchdog task exists, is enabled, and is either currently running with 0x41301 or has LastTaskResult 0.",
        force_upgrade=not rows,
    )


def collect_health_checks(engine_connection: Any):
    if _BASE_COLLECT is None:
        raise RuntimeError("Supervisor diagnostic runtime was not installed")
    checks, channels = _BASE_COLLECT(engine_connection)
    checks.extend([supervisor_process_check(), stop_flag_check()])
    return checks, channels


def install() -> None:
    global _INSTALLED, _BASE_COLLECT
    if _INSTALLED:
        return
    _BASE_COLLECT = diagnostics.collect_health_checks
    diagnostics._watchdog_check = watchdog_check
    diagnostics.collect_health_checks = collect_health_checks
    _INSTALLED = True
