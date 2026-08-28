"""Load local runtime configuration before shared imports bind environment."""

from pathlib import Path

from run_with_env import load_env

ROOT = Path(__file__).resolve().parents[2]


def bootstrap() -> None:
    load_env()
