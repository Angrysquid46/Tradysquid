"""Fail-closed launch readiness checks for BLACKTIDE only."""

from __future__ import annotations

import json
import socket
import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .env_bootstrap import ROOT, bootstrap

bootstrap()

import market_api_budget
import market_data
import scoreboard

INSTANCE_PORT = 8892


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, timeout=15, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def instance_port_free(port: int = INSTANCE_PORT) -> bool:
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        probe.close()


def run(*, session_date: date, require_clean_start: bool = True) -> list[Check]:
    state_path = ROOT / "state" / "supervisor-state.json"
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    head = _head()
    deployed = str(state.get("deployed_sha") or "")
    checks = [Check(
        "deployed-main", bool(head != "unknown" and deployed and head.startswith(deployed)
                              and state.get("last_update_status") == "DEPLOYED"),
        f"head={head[:12]} deployed={deployed[:12]} status={state.get('last_update_status')}",
    ), Check("single-instance", instance_port_free(), "BLACKTIDE instance port must be free")]

    connection = scoreboard.connect_db()
    try:
        generation = scoreboard.current_generation(connection, "BLACKTIDE")
        bankroll = scoreboard.current_bankroll(connection, "BLACKTIDE")
        trades = scoreboard.trade_count(connection, "BLACKTIDE")
        flat = scoreboard.current_position_status(connection, "BLACKTIDE") is None
    finally:
        connection.close()
    clean = generation == 1 and abs(bankroll - 1000.0) < .01 and trades == 0 and flat
    checks.append(Check("official-state", clean if require_clean_start else generation >= 1,
                        f"generation={generation} bankroll={bankroll:.2f} trades={trades} flat={flat}"))

    try:
        quote = market_data.get_quote(
            "SPY", priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT,
        )
        checks.append(Check("tradier-quote", bool(quote), "live SPY quote available"))
        expirations = market_data.get_expirations(
            "SPY", priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT,
        )
        checks.append(Check("target-expiration", session_date.isoformat() in expirations,
                            f"target={session_date.isoformat()} listed={session_date.isoformat() in expirations}"))
    except Exception as exc:
        checks.extend((Check("tradier-quote", False, f"{type(exc).__name__}: {exc}"),
                       Check("target-expiration", False, "provider check failed")))
    return checks


def require_ready(*, session_date: date, require_clean_start: bool = True) -> list[Check]:
    checks = run(session_date=session_date, require_clean_start=require_clean_start)
    failed = [check for check in checks if not check.passed]
    if failed:
        raise RuntimeError("; ".join(f"{item.name}: {item.detail}" for item in failed))
    return checks
