"""Launch the supervisor with safe Windows process ownership handling."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import tradysquid_supervisor as supervisor


ROOT = Path(__file__).resolve().parent


def safe_take_process_ownership() -> None:
    if os.name != "nt":
        return
    helper = ROOT / "stop_tradysquid_processes.ps1"
    if not helper.exists():
        return
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper),
            "-KeepProcessId",
            str(os.getpid()),
        ],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    time.sleep(2)


supervisor.take_process_ownership = safe_take_process_ownership


if __name__ == "__main__":
    raise SystemExit(supervisor.main())
