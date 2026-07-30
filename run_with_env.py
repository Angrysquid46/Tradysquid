"""Load the ignored local .env file, then run another Python script."""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"


def load_env() -> None:
    if not ENV_PATH.exists():
        raise SystemExit("Missing .env. Copy .env.example to .env and fill it in.")
    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python run_with_env.py <script.py>")
    load_env()
    target = (ROOT / sys.argv[1]).resolve()
    if target.parent != ROOT or not target.is_file() or target.suffix != ".py":
        raise SystemExit("Target must be a Python file in this repository.")
    sys.argv = [str(target)]
    runpy.run_path(str(target), run_name="__main__")


if __name__ == "__main__":
    main()

