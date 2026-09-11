"""Load local runtime configuration before shared imports bind environment."""

from run_with_env import load_env


def bootstrap() -> None:
    load_env()
