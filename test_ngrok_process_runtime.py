from __future__ import annotations

import unittest
from types import SimpleNamespace

import ngrok_process_runtime


class FakeService:
    def __init__(self, name, command, healthy):
        self.name = name
        self.command = command
        self.healthy = healthy


class NgrokProcessRuntimeTests(unittest.TestCase):
    def test_direct_command_tracks_the_real_executable(self) -> None:
        supervisor = SimpleNamespace(find_ngrok=lambda: r"C:\tools\ngrok.exe")
        self.assertEqual(
            ngrok_process_runtime.direct_ngrok_command(supervisor),
            [r"C:\tools\ngrok.exe", "http", "8080"],
        )

    def test_direct_command_contains_no_python_wrapper(self) -> None:
        result = ngrok_process_runtime.validate()
        self.assertTrue(result["tracks_real_executable"])
        self.assertFalse(result["uses_python_wrapper"])
        self.assertFalse(result["uses_run_ngrok_wrapper"])

    def test_missing_executable_fails_without_spawning_a_wrapper(self) -> None:
        supervisor = SimpleNamespace(find_ngrok=lambda: "")
        with self.assertRaisesRegex(RuntimeError, "ngrok.exe could not be found"):
            ngrok_process_runtime.direct_ngrok_command(supervisor)

    def test_install_replaces_only_the_ngrok_service_command(self) -> None:
        command_bot = lambda: ["command-bot"]
        information_engine = lambda: ["information-engine"]
        old_ngrok = lambda: ["python", "run_ngrok.py"]
        healthy = lambda: True
        supervisor = SimpleNamespace(
            find_ngrok=lambda: r"C:\tools\ngrok.exe",
            Service=FakeService,
            SERVICES=[
                FakeService("command-bot", command_bot, healthy),
                FakeService("information-engine", information_engine, healthy),
                FakeService("ngrok", old_ngrok, healthy),
            ],
            ngrok_command=old_ngrok,
        )
        original = ngrok_process_runtime._INSTALLED
        try:
            ngrok_process_runtime._INSTALLED = False
            ngrok_process_runtime.install(supervisor)
            services = {service.name: service for service in supervisor.SERVICES}
            self.assertIs(services["command-bot"].command, command_bot)
            self.assertIs(services["information-engine"].command, information_engine)
            self.assertEqual(
                services["ngrok"].command(),
                [r"C:\tools\ngrok.exe", "http", "8080"],
            )
            self.assertEqual(
                supervisor.ngrok_command(),
                [r"C:\tools\ngrok.exe", "http", "8080"],
            )
        finally:
            ngrok_process_runtime._INSTALLED = original


if __name__ == "__main__":
    unittest.main()
