"""Tradysquids local supervisor and automatic GitHub deployment service.

This is the one long-running local process. It owns the Discord command bot,
local information engine, and ngrok tunnel; restarts unhealthy services; checks
origin/main for approved repository updates; validates updates; applies the
Discord layout/command configuration; and rolls back failed deployments.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import requests

from run_with_env import load_env


load_env()

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
LOG_DIR = STATE_DIR / "supervisor-logs"
DEPLOY_STATE_PATH = STATE_DIR / "supervisor-state.json"
LOCK_HOST = "127.0.0.1"
LOCK_PORT = int(os.environ.get("SUPERVISOR_LOCK_PORT", "8876"))
HEALTH_SECONDS = max(10, int(os.environ.get("SUPERVISOR_HEALTH_SECONDS", "30")))
UPDATE_SECONDS = max(
    60, int(os.environ.get("SUPERVISOR_UPDATE_MINUTES", "2")) * 60
)
AUTO_UPDATE = os.environ.get("SUPERVISOR_AUTO_UPDATE", "true").lower() == "true"
AUTO_DISCORD_SYNC = (
    os.environ.get("SUPERVISOR_AUTO_DISCORD_SYNC", "true").lower() == "true"
)
AUTO_REGISTER_COMMANDS = (
    os.environ.get("SUPERVISOR_AUTO_REGISTER_COMMANDS", "true").lower() == "true"
)
PREVENT_SLEEP = os.environ.get("SUPERVISOR_PREVENT_SLEEP", "true").lower() == "true"

CREATE_FLAGS = 0
if os.name == "nt":
    CREATE_FLAGS = (
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )


@dataclass(frozen=True)
class Service:
    name: str
    command: Callable[[], list[str]]
    healthy: Callable[[], bool]


PROCESSES: dict[str, subprocess.Popen[str]] = {}
LOG_HANDLES: dict[str, object] = {}
LAST_HEALTH: dict[str, bool] = {}
DISCORD_CHANNEL_CACHE: dict[str, str] = {}

RUNTIME_MUTABLE_FILES = {
    "config/scanner.json",
    "docs/index.html",
    "docs/ford-market-chart.svg",
    "docs/ford-market-chart.png",
}
RUNTIME_MUTABLE_PREFIXES = ("state/", "docs/trade-snapshots/", "docs/tickers/")
RUNTIME_BACKUP_DIR = STATE_DIR / "supervisor-runtime-backup"


def state_payload() -> dict[str, object]:
    if not DEPLOY_STATE_PATH.exists():
        return {}
    try:
        value = json.loads(DEPLOY_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(**updates: object) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = state_payload()
    payload.update(updates)
    payload["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    temporary = DEPLOY_STATE_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    # Windows can transiently deny this replace if antivirus or a sync
    # client (this project lives in a OneDrive-synced folder) has the
    # target briefly open for its own read. That's normally gone within a
    # fraction of a second - a short retry survives it instead of crashing
    # the whole supervisor over a lock that was never really contested.
    last_error: PermissionError | None = None
    for attempt in range(5):
        try:
            temporary.replace(DEPLOY_STATE_PATH)
            return
        except PermissionError as exc:
            last_error = exc
            if attempt < 4:
                time.sleep(0.3)
    raise last_error


def run(
    command: list[str],
    *,
    timeout: int = 180,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
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
        raise RuntimeError(f"{' '.join(command)}: {detail[:1500]}")
    return result


def git(*arguments: str, timeout: int = 180, check: bool = False) -> subprocess.CompletedProcess[str]:
    return run(["git", *arguments], timeout=timeout, check=check)


def current_sha() -> str:
    result = git("rev-parse", "--short=12", "HEAD")
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def dirty_tracked_paths() -> list[str]:
    result = git("status", "--porcelain", "--untracked-files=no")
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "git status failed")[-1000:])
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        if path:
            paths.append(path.replace("\\", "/"))
    return paths


def runtime_mutable(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in RUNTIME_MUTABLE_FILES or normalized.startswith(
        RUNTIME_MUTABLE_PREFIXES
    )


def backup_runtime_changes(paths: list[str]) -> list[str]:
    if RUNTIME_BACKUP_DIR.exists():
        shutil.rmtree(RUNTIME_BACKUP_DIR)
    saved: list[str] = []
    for relative in paths:
        source = ROOT / relative
        if not source.exists() or not source.is_file():
            continue
        target = RUNTIME_BACKUP_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        saved.append(relative)
    if paths:
        checkout = git("checkout", "--", *paths, timeout=120)
        if checkout.returncode:
            raise RuntimeError(
                (checkout.stderr or checkout.stdout or "could not clean runtime files")[-1200:]
            )
    return saved


def restore_runtime_changes(paths: list[str]) -> None:
    for relative in paths:
        source = RUNTIME_BACKUP_DIR / relative
        if not source.exists():
            continue
        target = ROOT / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    if RUNTIME_BACKUP_DIR.exists():
        shutil.rmtree(RUNTIME_BACKUP_DIR, ignore_errors=True)


def http_healthy(url: str) -> bool:
    try:
        response = requests.get(url, timeout=3)
        return response.ok
    except requests.RequestException:
        return False


def port_healthy(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
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


def find_ngrok() -> str:
    candidates = [
        shutil.which("ngrok.exe"),
        shutil.which("ngrok"),
    ]
    local = os.environ.get("LOCALAPPDATA", "")
    user = os.environ.get("USERPROFILE", "")
    candidates.extend(
        [
            str(Path(local) / "Microsoft" / "WinGet" / "Links" / "ngrok.exe")
            if local
            else "",
            str(Path(local) / "ngrok" / "ngrok.exe") if local else "",
            str(Path(user) / "Downloads" / "ngrok.exe") if user else "",
            str(ROOT / "ngrok.exe"),
        ]
    )
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(Path(candidate))
    return ""


def command_bot_command() -> list[str]:
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "discord_command_bot.py"),
    ]


def information_engine_command() -> list[str]:
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "local_information_engine.py"),
    ]


def ngrok_command() -> list[str]:
    executable = find_ngrok()
    if not executable:
        raise RuntimeError("ngrok.exe could not be found")
    return [
        sys.executable,
        str(ROOT / "run_with_env.py"),
        str(ROOT / "run_ngrok.py"),
        executable,
    ]


SERVICES = [
    Service(
        "command-bot",
        command_bot_command,
        lambda: http_healthy("http://127.0.0.1:8080/health"),
    ),
    Service(
        "information-engine",
        information_engine_command,
        lambda: port_healthy("127.0.0.1", 8765),
    ),
    Service("ngrok", ngrok_command, ngrok_healthy),
]


def open_log(name: str):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handle = (LOG_DIR / f"{name}.log").open(
        "a",
        encoding="utf-8",
        buffering=1,
    )
    LOG_HANDLES[name] = handle
    return handle


def start_service(service: Service) -> bool:
    existing = PROCESSES.get(service.name)
    if existing and existing.poll() is None:
        return True
    try:
        command = service.command()
        handle = LOG_HANDLES.get(service.name) or open_log(service.name)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            creationflags=CREATE_FLAGS,
        )
        PROCESSES[service.name] = process
        return True
    except (OSError, RuntimeError) as exc:
        supervisor_log(f"Could not start {service.name}: {exc}")
        return False


def stop_process(name: str) -> None:
    process = PROCESSES.pop(name, None)
    if not process or process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=20,
                check=False,
            )
        else:
            process.terminate()
            process.wait(timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        try:
            process.kill()
        except OSError:
            pass


def stop_all_services() -> None:
    for service in reversed(SERVICES):
        stop_process(service.name)
    time.sleep(2)


def take_process_ownership() -> None:
    """Stop old manually launched copies before the supervisor starts its own."""
    if os.name != "nt":
        return
    own_pid = os.getpid()
    script = rf"""
$patterns = @(
  'discord_command_bot\.py',
  'local_information_engine\.py',
  'run_ngrok\.py',
  'ngrok(\.exe)?\s+http\s+8080'
)
Get-CimInstance Win32_Process |
  Where-Object {{
    $process = $_
    $process.ProcessId -ne {own_pid} -and
    $process.CommandLine -and
    ($patterns | Where-Object {{ $process.CommandLine -match $_ }}).Count -gt 0
  }} |
  ForEach-Object {{
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }}
"""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        cwd=ROOT,
        capture_output=True,
        timeout=30,
        check=False,
    )
    time.sleep(2)


def supervisor_log(message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamped = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {message}"
    # Scheduled tasks inherit the legacy Windows console encoding. Keep rich
    # Unicode in the UTF-8 log while making console output incapable of
    # crashing the supervisor during an automatic deployment.
    console_encoding = getattr(sys.stdout, "encoding", None) or "ascii"
    console_text = stamped.encode(console_encoding, errors="backslashreplace").decode(
        console_encoding
    )
    print(console_text, flush=True)
    with (LOG_DIR / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write(stamped + "\n")


def discord_channel_id(name: str) -> str:
    cached = DISCORD_CHANNEL_CACHE.get(name)
    if cached:
        return cached
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    guild = os.environ.get("DISCORD_GUILD_ID", "").strip()
    if not token or not guild:
        return ""
    headers = {
        "Authorization": f"Bot {token}",
        "User-Agent": "DiscordBot (Tradysquids Supervisor, 1.0)",
    }
    try:
        response = requests.get(
            f"https://discord.com/api/v10/guilds/{guild}/channels",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        channels = response.json()
    except (requests.RequestException, ValueError, TypeError):
        return ""
    for channel in channels if isinstance(channels, list) else []:
        if str(channel.get("name") or "").casefold() == name.casefold():
            channel_id = str(channel.get("id") or "")
            if channel_id:
                DISCORD_CHANNEL_CACHE[name] = channel_id
                return channel_id
    return ""


def discord_post(message: str, channel_name: str = "system-health") -> None:
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    channel_id = discord_channel_id(channel_name)
    if not token or not channel_id:
        return
    headers = {
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (Tradysquids Supervisor, 1.0)",
    }
    payload = {
        "content": message[:1900],
        "allowed_mentions": {"parse": []},
    }
    try:
        title = message.splitlines()[0].strip()
        history = requests.get(
            f"https://discord.com/api/v10/channels/{channel_id}/messages?limit=100",
            headers=headers,
            timeout=15,
        )
        history.raise_for_status()
        matches = [
            item
            for item in history.json()
            if str(item.get("content") or "").splitlines()[:1] == [title]
            and (item.get("author") or {}).get("bot")
        ]
        if matches:
            requests.patch(
                f"https://discord.com/api/v10/channels/{channel_id}/messages/{matches[0]['id']}",
                headers=headers,
                json=payload,
                timeout=15,
            ).raise_for_status()
            for duplicate in matches[1:]:
                requests.delete(
                    f"https://discord.com/api/v10/channels/{channel_id}/messages/{duplicate['id']}",
                    headers=headers,
                    timeout=15,
                ).raise_for_status()
        else:
            requests.post(
                f"https://discord.com/api/v10/channels/{channel_id}/messages",
                headers=headers,
                json=payload,
                timeout=15,
            ).raise_for_status()
    except (requests.RequestException, ValueError, TypeError) as exc:
        supervisor_log(f"Discord status post failed: {exc}")


def validate_checkout() -> tuple[bool, str]:
    compile_files = [
        "ford_scan.py",
        "local_information_engine.py",
        "discord_command_bot.py",
        "register_discord_commands.py",
        "sync_discord_structure.py",
        "tradysquid_supervisor.py",
        "trade_intelligence.py",
        "upgrade_impact.py",
    ]
    compile_result = run(
        [sys.executable, "-m", "py_compile", *compile_files],
        timeout=120,
    )
    if compile_result.returncode:
        return False, (compile_result.stderr or compile_result.stdout)[-1500:]
    impact = run([sys.executable, "upgrade_impact.py", "--check"], timeout=60)
    if impact.returncode:
        return False, (impact.stderr or impact.stdout)[-1500:]
    tests = run(
        [
            sys.executable,
            "-m",
            "unittest",
            "-q",
            "test_local_information_engine.py",
        ],
        timeout=240,
    )
    if tests.returncode:
        return False, (tests.stderr or tests.stdout)[-1500:]
    return True, "Python compilation and focused tests passed"


def run_discord_configuration() -> list[str]:
    results: list[str] = []
    if AUTO_REGISTER_COMMANDS:
        command_result = run(
            [
                sys.executable,
                str(ROOT / "run_with_env.py"),
                str(ROOT / "register_discord_commands.py"),
            ],
            timeout=120,
        )
        if command_result.returncode:
            results.append(
                "command registration failed: "
                + (command_result.stderr or command_result.stdout)[-500:]
            )
        else:
            results.append("Discord slash commands synchronized")
    if AUTO_DISCORD_SYNC:
        structure_result = run(
            [
                sys.executable,
                str(ROOT / "run_with_env.py"),
                str(ROOT / "sync_discord_structure.py"),
                "--apply",
            ],
            timeout=240,
        )
        if structure_result.returncode:
            results.append(
                "Discord structure sync failed: "
                + (structure_result.stderr or structure_result.stdout)[-500:]
            )
        else:
            results.append("Discord channels, guides, and permissions synchronized")
    return results


def fetch_remote_sha() -> str:
    result = git("fetch", "--quiet", "origin", "main", timeout=180)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout or "git fetch failed")[-1000:])
    remote = git("rev-parse", "origin/main", check=True)
    return remote.stdout.strip()


def deploy_if_needed(*, force: bool = False) -> bool:
    """Return True when the supervisor should restart itself."""
    branch_result = git("rev-parse", "--abbrev-ref", "HEAD")
    branch = branch_result.stdout.strip() if branch_result.returncode == 0 else ""
    if branch != "main":
        detail = f"Automatic deployment requires the laptop checkout to be on main, not {branch or 'unknown'}"
        supervisor_log(detail)
        previous = str(state_payload().get("last_update_detail") or "")
        write_state(last_update_status="WRONG_BRANCH", last_update_detail=detail)
        if previous != detail:
            discord_post(f"⚠️ **Tradysquids update paused**\n{detail}")
        return False

    local = git("rev-parse", "HEAD", check=True).stdout.strip()
    try:
        remote = fetch_remote_sha()
    except RuntimeError as exc:
        supervisor_log(f"Update check failed: {exc}")
        write_state(last_update_status="FETCH_FAILED", last_update_detail=str(exc))
        return False

    if remote == local and not force:
        return False
    try:
        dirty_paths = dirty_tracked_paths()
    except RuntimeError as exc:
        supervisor_log(f"Could not inspect local changes: {exc}")
        return False
    blocked_paths = [path for path in dirty_paths if not runtime_mutable(path)]
    if blocked_paths:
        detail = (
            "Local code/configuration changes block automatic deployment: "
            + ", ".join(blocked_paths[:12])
        )
        supervisor_log(detail)
        previous = str(state_payload().get("last_update_detail") or "")
        write_state(last_update_status="DIRTY", last_update_detail=detail)
        if previous != detail:
            discord_post(f"⚠️ **Tradysquids update paused**\n{detail}")
        return False

    ancestor = git("merge-base", "--is-ancestor", local, remote)
    if ancestor.returncode:
        detail = "origin/main is not a fast-forward from the laptop checkout"
        supervisor_log(detail)
        write_state(last_update_status="NON_FAST_FORWARD", last_update_detail=detail)
        discord_post(f"⚠️ **Tradysquids update blocked**\n{detail}")
        return False

    supervisor_log(f"Deploying {local[:12]} → {remote[:12]}")
    discord_post(
        f"🔄 **Tradysquids deployment started**\n"
        f"`{local[:12]}` → `{remote[:12]}`"
    )
    stop_all_services()
    saved_runtime: list[str] = []
    try:
        saved_runtime = backup_runtime_changes(
            [path for path in dirty_paths if runtime_mutable(path)]
        )
    except RuntimeError as exc:
        detail = f"Could not protect local runtime data: {exc}"
        supervisor_log(detail)
        write_state(last_update_status="BACKUP_FAILED", last_update_detail=detail)
        discord_post(f"❌ **Tradysquids deployment stopped**\n{detail}")
        return True

    merge = git("merge", "--ff-only", "origin/main", timeout=180)
    if merge.returncode:
        detail = (merge.stderr or merge.stdout or "git merge failed")[-1200:]
        restore_runtime_changes(saved_runtime)
        supervisor_log(f"Deployment failed before validation: {detail}")
        write_state(last_update_status="MERGE_FAILED", last_update_detail=detail)
        discord_post(f"❌ **Tradysquids deployment failed**\n```{detail[:1200]}```")
        return True

    valid, validation_detail = validate_checkout()
    if not valid:
        git("reset", "--hard", local, timeout=120)
        restore_runtime_changes(saved_runtime)
        supervisor_log(f"Validation failed; rolled back to {local[:12]}")
        write_state(
            last_update_status="ROLLED_BACK",
            last_update_detail=validation_detail,
            deployed_sha=local,
        )
        discord_post(
            "↩️ **Tradysquids update rolled back**\n"
            f"Restored `{local[:12]}` after validation failed.\n"
            f"```{validation_detail[:1100]}```"
        )
        return True

    restore_runtime_changes(saved_runtime)
    DISCORD_CHANNEL_CACHE.clear()
    discord_results = run_discord_configuration()
    DISCORD_CHANNEL_CACHE.clear()
    write_state(
        last_update_status="DEPLOYED",
        last_update_detail=validation_detail,
        deployed_sha=remote,
        discord_results=discord_results,
    )
    lines = [
        "✅ **Tradysquids update validated**",
        f"Now deploying `{remote[:12]}`.",
        validation_detail,
    ]
    lines.extend(f"• {item}" for item in discord_results)
    lines.append("The supervisor is restarting all local services.")
    discord_post("\n".join(lines), "workflow-log")
    supervisor_log("; ".join(lines))
    return True


def ensure_services() -> None:
    for service in SERVICES:
        healthy = service.healthy()
        process = PROCESSES.get(service.name)
        alive = bool(process and process.poll() is None)
        previous = LAST_HEALTH.get(service.name)

        if healthy and alive:
            LAST_HEALTH[service.name] = True
            continue

        if alive and not healthy:
            stop_process(service.name)
        started = start_service(service)
        if started:
            deadline = time.monotonic() + (20 if service.name != "ngrok" else 30)
            while time.monotonic() < deadline:
                if service.healthy():
                    healthy = True
                    break
                time.sleep(1)

        LAST_HEALTH[service.name] = healthy
        if healthy and previous is False:
            discord_post(f"✅ **{service.name} recovered automatically.**")
        elif not healthy and previous is not False:
            discord_post(
                f"⚠️ **{service.name} is unhealthy.** "
                "The supervisor will keep retrying."
            )


def prevent_windows_sleep() -> None:
    if os.name != "nt" or not PREVENT_SLEEP:
        return
    try:
        import ctypes

        # ES_CONTINUOUS | ES_SYSTEM_REQUIRED. The display may turn off, but the
        # laptop will not suspend while the supervisor is active.
        ctypes.windll.kernel32.SetThreadExecutionState(0x80000001)
    except (AttributeError, OSError):
        supervisor_log("Windows sleep prevention could not be enabled")


def _log_port_kill_evidence(pid: str, command_line: str, parent_pid: str, parent_command: str) -> None:
    try:
        log_path = STATE_DIR / "port-kill-evidence.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            f"{stamp} | AUTO-CLEARED PID {pid} [supervisor self-heal on startup]",
            f"  CommandLine: {command_line}",
            f"  ParentProcessId: {parent_pid}",
            f"  ParentCommandLine: {parent_command}",
            "",
        ]
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(lines) + "\n")
    except OSError:
        pass


def _clear_stale_port_holder() -> bool:
    """A previous crashed run can leave a python.exe stuck holding the lock
    port even though it isn't doing anything useful anymore - this has been
    the single most common startup failure. Rather than a one-click launcher
    that silently waits forever for a human to run a separate cleanup
    script, find and clear whatever's actually squatting on the port, log
    what it was, and let startup proceed on its own."""
    script = (
        "$c = Get-NetTCPConnection -LocalPort " + str(LOCK_PORT) +
        " -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1; "
        "if (-not $c) { exit 0 }; "
        "$p = Get-CimInstance Win32_Process -Filter \"ProcessId=$($c.OwningProcess)\" "
        "-ErrorAction SilentlyContinue; "
        "if (-not $p) { exit 0 }; "
        "$parent = Get-CimInstance Win32_Process -Filter \"ProcessId=$($p.ParentProcessId)\" "
        "-ErrorAction SilentlyContinue; "
        "[PSCustomObject]@{ "
        "ProcessId = $p.ProcessId; CommandLine = $p.CommandLine; "
        "ParentProcessId = $p.ParentProcessId; "
        "ParentCommandLine = $(if ($parent) { $parent.CommandLine } else { 'unknown' }) "
        "} | ConvertTo-Json -Compress; "
        "Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    output = (result.stdout or "").strip()
    if not output:
        return False
    try:
        info = json.loads(output)
    except ValueError:
        return False
    _log_port_kill_evidence(
        str(info.get("ProcessId", "")),
        str(info.get("CommandLine", "")),
        str(info.get("ParentProcessId", "")),
        str(info.get("ParentCommandLine", "")),
    )
    time.sleep(1.5)
    return True


def acquire_instance_lock() -> socket.socket:
    def try_bind() -> socket.socket | None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            listener.bind((LOCK_HOST, LOCK_PORT))
            listener.listen(1)
            return listener
        except OSError:
            listener.close()
            return None

    listener = try_bind()
    if listener is not None:
        return listener

    # First attempt found the port held. Before giving up and asking a
    # human to run a separate script, try clearing it automatically once -
    # this is what "one click" is supposed to mean.
    if _clear_stale_port_holder():
        listener = try_bind()
        if listener is not None:
            print("Cleared a stale process holding the lock port; continuing startup.")
            return listener

    raise RuntimeError("Tradysquids Supervisor is already running")


def main() -> int:
    load_env()
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        instance_lock = acquire_instance_lock()
    except RuntimeError as exc:
        print(exc)
        return 0

    with instance_lock:
        prevent_windows_sleep()
        take_process_ownership()
        ensure_services()
        sha = current_sha()
        write_state(supervisor="ONLINE", deployed_sha=sha)
        discord_post(
            f"🟢 **Tradysquids Supervisor online**\n"
            f"Version `{sha}` · automatic updates "
            f"{'enabled' if AUTO_UPDATE else 'disabled'}."
        )
        supervisor_log(
            f"Supervisor online at {sha}; auto-update={AUTO_UPDATE}; "
            f"Discord sync={AUTO_DISCORD_SYNC}"
        )

        next_health = 0.0
        next_update = 0.0
        while True:
            now = time.monotonic()
            if now >= next_health:
                ensure_services()
                next_health = now + HEALTH_SECONDS
            if AUTO_UPDATE and now >= next_update:
                if deploy_if_needed():
                    stop_all_services()
                    return 75
                next_update = now + UPDATE_SECONDS
            time.sleep(2)


if __name__ == "__main__":
    raise SystemExit(main())
