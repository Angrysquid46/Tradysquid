"""Load local runtime configuration before shared provider imports bind it."""
from pathlib import Path
from run_with_env import load_env
ROOT=Path(__file__).resolve().parents[2]
def bootstrap():load_env()
