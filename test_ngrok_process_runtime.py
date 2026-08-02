from __future__ import annotations

import unittest
from types import SimpleNamespace

import ngrok_process_runtime


class FakeService:
    def __init__(self, name, command, healthy):
        self.name = name
        self.command = command
        self.healthy = healthy


class FakeProcess:
    def __init__(self, returncode=None):
        self.returncode = returncode

    def poll(self):
        return self.returncode


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
        self.assertTrue(result["healthy_endpoint_is_authoritative"])
        self.assertFalse(result["uses_python_wrapper"])
        self.assertFalse(result["uses_run_ngrok_wrapper"])

    def test_missing_executable_fails_without_spawning_a_wrapper(self) -> None:
        supervisor = SimpleNamespace(find_ngrok=lambda: "")
        with self.assertRaisesRegex(RuntimeError, "ngrok.exe could not be found"):
            ngrok_process_runtime.direct_ngrok_command(supervisor)

    def test_healthy_ngrok_without_a_tracked_process_is_not_started_again(self) -> None:
        starts = []
        posts = []
        service = FakeService("ngrok", lambda: ["ngrok"], lambda: True)
        supervisor = SimpleNamespace(
            SERVICES=[service],
            PROCESSES={},
            LAST_HEALTH={"ngrok": True},
            start_service=lambda item: starts.append(item.name) or True,
            stop_process=lambda name: None,
            discord_post=posts.append,
        )
        ngrok_process_runtime.ensure_services(supervisor)
        self.assertEqual(starts, [])
        self.assertEqual(posts, [])
        self.assertTrue(supervisor.LAST_HEALTH["ngrok"])

    def test_unhealthy_ngrok_starts_once_and_becomes_healthy(self) -> None:
        health = iter((False, True))
        starts = []
        service = FakeService("ngrok", lambda: ["ngrok"], lambda: next(health))
        supervisor = SimpleNamespace(
            SERVICES=[service],
            PROCESSES={},
            LAST_HEALTH={"ngrok": False},
            start_service=lambda item: starts.append(item.name) or True,
            stop_process=lambda name: None,
            discord_post=lambda message: None,
        )
        ngrok_process_runtime.ensure_services(supervisor)
        self.assertEqual(starts, ["ngrok"])
        self.assertTrue(supervisor.LAST_HEALTH["ngrok"])

    def test_non_ngrok_service_still_requires_a_live_tracked_process(self) -> None:
        starts = []
        service = FakeService("command-bot", lambda: ["bot"], lambda: True)
        supervisor = SimpleNamespace(
            SERVICES=[service],
            PROCESSES={},
            LAST_HEALTH={"command-bot": True},
            start_service=lambda item: starts.append(item.name) or True,
            stop_process=lambda name: None,
            discord_post=lambda message: None,
        )
        ngrok_process_runtime.ensure_services(supervisor)
        self.assertEqual(starts, ["command-bot"])

    def test_install_replaces_only_ngrok_command_and_health_loop(self) -> None:
        command_bot = lambda: ["command-bot"]
        information_engine = lambda: ["information-engine"]
        old_ngrok = lambda: ["python", "run_ngrok.py"]
        healthy = lambda: True
        old_loop = lambda: None
        supervisor = SimpleNamespace(
            find_ngrok=lambda: r"C:\tools\ngrok.exe",
            Service=FakeService,
            SERVICES=[
                FakeService("command-bot", command_bot, healthy),
                FakeService("information-engine", information_engine, healthy),
                FakeService("ngrok", old_ngrok, healthy),
            ],
            ngrok_command=old_ngrok,
            ensure_services=old_loop,
            PROCESSES={},
            LAST_HEALTH={},
            start_service=lambda service: True,
            stop_process=lambda name: None,
            discord_post=lambda message: None,
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
            self.assertIsNot(supervisor.ensure_services, old_loop)
        finally:
            ngrok_process_runtime._INSTALLED = original


if __name__ == "__main__":
    unittest.main()
