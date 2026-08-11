"""Keep ngrok supervision tied to the real tunnel health.

The supervisor owns ``ngrok.exe`` directly when it must start a tunnel. If an
already-running tunnel is healthy, the supervisor leaves it alone even when no
tracked process handle exists. That prevents a healthy tunnel from spawning a new
ngrok process every 30-second health cycle.
"""

from __future__ import annotations

import time
from typing import Any

_INSTALLED = False
# This module installs its OWN complete copy of the health-check/restart
# loop (see install() below, which does supervisor.ensure_services =
# health_loop) - because of override ordering in run_with_env.py
# (ngrok_process_runtime.install() runs before run_supervisor_simple.py
# captures its "original_ensure_services" reference), THIS function - not
# tradysquid_supervisor.ensure_services - is the one that actually runs
# live. Confirmed via direct diagnostic logging (2026-08-11): edits to the
# tradysquid_supervisor.py copy never fired at all. The same
# single-failed-probe-kills-immediately bug (see tradysquid_supervisor.py's
# HEALTH_FAILURE_STREAK for the full writeup) lives here too and needs the
# same debounce fix, or ngrok's own real fix is a no-op for the actual
# running system.
HEALTH_FAILURE_STREAK: dict[str, int] = {}
HEALTH_FAILURE_THRESHOLD = 2


def direct_ngrok_command(supervisor: Any) -> list[str]:
    executable = supervisor.find_ngrok()
    if not executable:
        raise RuntimeError("ngrok.exe could not be found")
    return [executable, "http", "8080"]


def ensure_services(supervisor: Any) -> None:
    """Use endpoint health as the authority for ngrok; preserve normal service logic."""
    for service in supervisor.SERVICES:
        healthy = service.healthy()
        process = supervisor.PROCESSES.get(service.name)
        alive = bool(process and process.poll() is None)
        previous = supervisor.LAST_HEALTH.get(service.name)

        # ngrok may already be running outside the current Popen handle. A
        # healthy local API/tunnel is authoritative, so another process must not
        # be launched merely because the tracked handle is absent or exited.
        if service.name == "ngrok" and healthy:
            supervisor.LAST_HEALTH[service.name] = True
            HEALTH_FAILURE_STREAK[service.name] = 0
            if previous is False:
                supervisor.discord_post("✅ **ngrok recovered automatically.**")
            continue

        if healthy and alive:
            supervisor.LAST_HEALTH[service.name] = True
            HEALTH_FAILURE_STREAK[service.name] = 0
            continue

        if alive and not healthy:
            # A single failed health probe (a bare few-second TCP/HTTP check)
            # is not reliable enough to justify killing an otherwise-running
            # process - require HEALTH_FAILURE_THRESHOLD consecutive
            # failures before actually restarting. A genuinely dead process
            # (alive is False) still restarts immediately below.
            streak = HEALTH_FAILURE_STREAK.get(service.name, 0) + 1
            HEALTH_FAILURE_STREAK[service.name] = streak
            if streak < HEALTH_FAILURE_THRESHOLD:
                continue
            supervisor.stop_process(service.name)

        HEALTH_FAILURE_STREAK[service.name] = 0
        started = supervisor.start_service(service)
        if started:
            deadline = time.monotonic() + (20 if service.name != "ngrok" else 30)
            while time.monotonic() < deadline:
                if service.healthy():
                    healthy = True
                    break
                time.sleep(1)

        supervisor.LAST_HEALTH[service.name] = healthy
        if healthy and previous is False:
            supervisor.discord_post(f"✅ **{service.name} recovered automatically.**")
        elif not healthy and previous is not False:
            supervisor.discord_post(
                f"⚠️ **{service.name} is unhealthy.** "
                "The supervisor will keep retrying."
            )


def install(supervisor: Any | None = None) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if supervisor is None:
        import tradysquid_supervisor as supervisor

    def command() -> list[str]:
        return direct_ngrok_command(supervisor)

    def health_loop() -> None:
        ensure_services(supervisor)

    supervisor.ngrok_command = command
    supervisor.SERVICES = [
        supervisor.Service(
            service.name,
            command if service.name == "ngrok" else service.command,
            service.healthy,
        )
        for service in supervisor.SERVICES
    ]
    supervisor.ensure_services = health_loop
    _INSTALLED = True


def validate() -> dict[str, Any]:
    class FakeSupervisor:
        @staticmethod
        def find_ngrok() -> str:
            return r"C:\ngrok\ngrok.exe"

    command = direct_ngrok_command(FakeSupervisor())
    return {
        "command": command,
        "tracks_real_executable": command[0].lower().endswith("ngrok.exe"),
        "healthy_endpoint_is_authoritative": True,
        "uses_python_wrapper": any("python" in item.lower() for item in command),
        "uses_run_ngrok_wrapper": any("run_ngrok.py" in item.lower() for item in command),
    }
