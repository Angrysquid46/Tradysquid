"""Create a strong ignored local TradingView webhook secret when missing."""

from __future__ import annotations

import secrets
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"
KEY = "TRADINGVIEW_WEBHOOK_SECRET"


def ensure_secret(path: Path = ENV_PATH) -> bool:
    if not path.exists():
        raise FileNotFoundError("Missing .env; complete local setup first.")
    lines = path.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if line.strip().startswith(f"{KEY}=") and line.split("=", 1)[1].strip():
            return False
    value = secrets.token_urlsafe(48)
    replaced = False
    updated: list[str] = []
    for line in lines:
        if line.strip().startswith(f"{KEY}="):
            updated.append(f"{KEY}={value}")
            replaced = True
        else:
            updated.append(line)
    if not replaced:
        updated.extend(["", f"{KEY}={value}"])
    temporary = path.with_suffix(".env.tmp")
    temporary.write_text("\n".join(updated) + "\n", encoding="utf-8")
    temporary.replace(path)
    return True


def main() -> int:
    created = ensure_secret()
    print(
        "TradingView webhook secret created locally."
        if created
        else "TradingView webhook secret already exists."
    )
    print("The secret was not displayed and .env remains excluded from Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
