"""Load repository environment before shared modules bind env constants."""

from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


def bootstrap() -> None:
    load_dotenv(ROOT / ".env", override=False)
