"""Start ngrok using its secure per-user configuration."""

from __future__ import annotations

import os
import subprocess
import sys

from run_with_env import load_env


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python run_ngrok.py <path-to-ngrok.exe>")
        return 1
    load_env()
    command = [sys.argv[1], "http", "8080"]
    domain = os.environ.get("NGROK_DOMAIN", "").strip()
    if domain:
        # A reserved static domain keeps the public URL identical across
        # every restart, so Discord's Interactions Endpoint URL only ever
        # needs to be set once instead of drifting out of sync.
        command.append(f"--domain={domain}")
    return subprocess.call(command)


if __name__ == "__main__":
    raise SystemExit(main())
