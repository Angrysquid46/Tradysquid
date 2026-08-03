from __future__ import annotations
import json, os
from pathlib import Path

class ProcessLockError(RuntimeError): pass

class ProcessLock:
    def __init__(self, path: Path):
        self.path = path
        self.acquired = False

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        if os.name == 'nt':
            # os.kill(pid, 0) is not a harmless existence probe on Windows. Use
            # a query-only process handle so duplicate detection cannot deliver
            # a console control signal to the process being checked.
            import ctypes
            process_query_limited_information = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                process_query_limited_information,
                False,
                int(pid),
            )
            if not handle:
                return False
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding='utf-8'))
                pid = int(data.get('pid', 0))
            except (ValueError, TypeError, json.JSONDecodeError):
                pid = 0
            if self._pid_alive(pid):
                raise ProcessLockError(f'Tradysquid is already running with PID {pid}')
            self.path.unlink(missing_ok=True)
        payload = {'pid': os.getpid(), 'repository': str(Path.cwd().resolve())}
        fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle)
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *args):
        self.release()
