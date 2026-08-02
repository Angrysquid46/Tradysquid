"""Make the supervisor own the real ngrok process.

The previous command launched ``run_ngrok.py``, which could exit while the ngrok
tunnel remained healthy. The supervisor then saw a dead wrapper and started a new
copy every health cycle. This runtime replaces only the ngrok service command so
``PROCESSES['ngrok']`` tracks the long-running executable itself.
"""

from __future__ import annotations

from typing import Any

_INSTALLED = False


def direct_ngrok_command(supervisor: Any) -> list[str]:
    executable = supervisor.find_ngrok()
    if not executable:
        raise RuntimeError("ngrok.exe could not be found")
    return [executable, "http", "8080"]


def install(supervisor: Any | None = None) -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    if supervisor is None:
        import tradysquid_supervisor as supervisor

    def command() -> list[str]:
        return direct_ngrok_command(supervisor)

    supervisor.ngrok_command = command
    supervisor.SERVICES = [
        supervisor.Service(
            service.name,
            command if service.name == "ngrok" else service.command,
            service.healthy,
        )
        for service in supervisor.SERVICES
    ]
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
        "uses_python_wrapper": any("python" in item.lower() for item in command),
        "uses_run_ngrok_wrapper": any("run_ngrok.py" in item.lower() for item in command),
    }
