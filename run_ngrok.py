"""Start ngrok with the auth token loaded privately from .env."""

from __future__ import annotations

import subprocess
import sys

from run_with_env import load_env


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python run_ngrok.py <path-to-ngrok.exe>")
        return 1
    load_env()
    return subprocess.call([sys.argv[1], "http", "8080"])


if __name__ == "__main__":
    raise SystemExit(main())

