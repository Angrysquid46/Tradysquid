"""Phase 15: AXIOM's pre-market readiness gate - mirrors Codex's 15.2
checklist for BLACKTIDE, adapted to what AXIOM actually has. Every check
is real (git state, a live Tradier call, the actual scoreboard row, the
actual instance-lock port, the actual market clock) - nothing here is
assumed. Any failed check means "do not launch," full stop; this script
never changes bankroll, generation, or any other state - it only reads.

Usage:
    ./.venv-tradysquid/Scripts/python.exe -m bots.claude.preflight
"""

from __future__ import annotations

# Must run before any module that reads an env var as a module-level
# constant at import time (market_data.TRADIER_TOKEN, etc.) - see
# env_bootstrap.py's own docstring for why this has to be first, ahead of
# the imports below.
from bots.claude.env_bootstrap import load_env

load_env()

import socket
import subprocess
import sys
from pathlib import Path

import market_data
import scoreboard

from bots.claude.scheduler import LOCK_HOST, LOCK_PORT

ROOT = Path(__file__).resolve().parent.parent.parent
BOT = "AXIOM"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        self.rows.append((name, ok, detail))

    def render(self) -> int:
        width = max(len(n) for n, _, _ in self.rows)
        for name, ok, detail in self.rows:
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {name.ljust(width)}  {detail}")
        failed = [n for n, ok, _ in self.rows if not ok]
        print()
        if failed:
            print(f"  NOT READY - {len(failed)} check(s) failed: {', '.join(failed)}")
            return 1
        print("  READY - AXIOM may be launched")
        return 0


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def _port_is_free(host: str, port: int) -> bool:
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def main() -> int:
    r = Report()

    # 1. deployed == origin/main
    _git("fetch", "origin", "main", "-q")
    local = _git("rev-parse", "HEAD")
    origin = _git("rev-parse", "origin/main")
    r.check("deployed == origin/main", bool(origin) and local == origin,
             f"local={local[:7]} origin={origin[:7]}")

    # 2. no already-running AXIOM instance
    port_free = _port_is_free(LOCK_HOST, LOCK_PORT)
    r.check("instance lock port free", port_free, f"{LOCK_HOST}:{LOCK_PORT}")

    # 3. live Tradier connectivity
    try:
        quote = market_data.get_quote("SPY")
        r.check("live Tradier connectivity", quote is not None,
                f"last={quote.get('last') if quote else None}")
    except market_data.TradierError as exc:
        r.check("live Tradier connectivity", False, str(exc)[:60])

    # 4. today's 0DTE expiration exists
    try:
        today = market_data.now_ct().date().isoformat()
        expirations = market_data.get_expirations("SPY")
        r.check("today's 0DTE expiration listed", today in expirations,
                f"today={today}, found={today in expirations}")
    except market_data.TradierError as exc:
        r.check("today's 0DTE expiration listed", False, str(exc)[:60])

    # 5. AXIOM starts clean: Generation 1, $1,000, 0 trades, FLAT
    # scoreboard_snapshot()'s current_position_status is the redacted
    # "OPEN"/"FLAT" string (Section 14 privacy), not the raw row - that
    # raw shape is still what scoreboard.current_position_status() itself
    # returns for internal use, unchanged.
    try:
        sb = scoreboard.connect_db()
        snapshot = scoreboard.scoreboard_snapshot(sb, BOT)
        clean = (
            snapshot["generation"] == 1
            and snapshot["current_bankroll"] == scoreboard.STARTING_BANKROLL_USD
            and snapshot["trade_count_lifetime"] == 0
            and snapshot["current_position_status"] == "FLAT"
        )
        r.check(
            "AXIOM clean state (Gen 1, $1,000, 0 trades, FLAT)", clean,
            f"generation={snapshot['generation']} bankroll={snapshot['current_bankroll']} "
            f"trades={snapshot['trade_count_lifetime']} "
            f"position={snapshot['current_position_status']}",
        )
    except Exception as exc:  # noqa: BLE001 - report, don't crash the gate
        r.check("AXIOM clean state (Gen 1, $1,000, 0 trades, FLAT)", False, str(exc)[:60])

    # 6. market actually open
    open_now, now = market_data.market_is_open_now()
    r.check("market currently open", open_now, f"now={now.isoformat(timespec='seconds')}")

    return r.render()


if __name__ == "__main__":
    raise SystemExit(main())
