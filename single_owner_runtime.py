"""Enforce one supervisor owner without restarting the healthy owner.

This helper replaces the broad legacy startup cleanup only for
run_supervisor_simple.py. After the process has acquired port 8876, it removes
other simple-supervisor Python processes and their launcher CMD processes while
preserving the current process and its parent chain.
"""

from __future__ import annotations

import os
import subprocess
import time
from typing import Any

_INSTALLED = False


def _powershell_script(current_pid: int) -> str:
    return rf"""
$all = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue)
$keep = [System.Collections.Generic.HashSet[int]]::new()
$current = {current_pid}
while ($current -gt 0 -and $keep.Add([int]$current)) {{
    $item = $all | Where-Object {{ $_.ProcessId -eq $current }} | Select-Object -First 1
    if (-not $item) {{ break }}
    $current = [int]$item.ParentProcessId
}}
# Same bug found and fixed live in stop_tradysquid_processes.ps1 (2026-08-11):
# walking only UP the ancestor chain leaves this process's own already- or
# soon-to-be-spawned children (command-bot/information-engine) unprotected,
# so this script would kill its own legitimate services as "stale" matches.
# Walk DOWN from the current PID too, protecting its whole descendant tree.
$frontier = [System.Collections.Generic.Queue[int]]::new()
$frontier.Enqueue({current_pid})
while ($frontier.Count -gt 0) {{
    $parentId = $frontier.Dequeue()
    foreach ($child in ($all | Where-Object {{ [int]$_.ParentProcessId -eq $parentId }})) {{
        if ($keep.Add([int]$child.ProcessId)) {{
            $frontier.Enqueue([int]$child.ProcessId)
        }}
    }}
}}
$supervisorPattern = '(?i)(^|[\\/"\s])run_supervisor_simple\.py(["\s]|$)'
$launcherPattern = '(?i)(^|[\\/"\s])START-SUPERVISOR\.cmd(["\s]|$)'
$servicePattern = 'discord_command_bot(_public)?\.py|local_information_engine(_public|_bootstrap)?\.py|run_ngrok\.py|ngrok(\.exe)?\s+http\s+8080'
foreach ($process in $all) {{
    if ($keep.Contains([int]$process.ProcessId) -or -not $process.CommandLine) {{ continue }}
    $isSupervisor = $process.Name -match '^python(w)?\.exe$' -and $process.CommandLine -match $supervisorPattern
    $isLauncher = $process.Name -eq 'cmd.exe' -and $process.CommandLine -match $launcherPattern
    $isManagedService = $process.CommandLine -match $servicePattern
    if ($isSupervisor -or $isLauncher -or $isManagedService) {{
        Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
    }}
}}
"""


def take_single_owner() -> None:
    """Remove stale launchers and processes after this supervisor owns the lock."""
    if os.name != "nt":
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            _powershell_script(os.getpid()),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    time.sleep(2)


def install(supervisor: Any | None = None) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if supervisor is None:
        import tradysquid_supervisor as supervisor
    supervisor.take_process_ownership = take_single_owner
    _INSTALLED = True


def validate() -> dict[str, Any]:
    script = _powershell_script(123)
    return {
        "current_pid_preserved": "$keep.Add" in script,
        "ancestor_chain_preserved": "ParentProcessId" in script,
        "stale_supervisors_removed": "run_supervisor_simple" in script,
        "stale_launchers_removed": "START-SUPERVISOR" in script,
        "managed_services_reowned": "local_information_engine" in script,
    }
