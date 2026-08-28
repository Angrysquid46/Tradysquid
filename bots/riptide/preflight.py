"""Fail-closed launch readiness checks for RIPTIDE's paper process."""

from __future__ import annotations

import json
import socket
import subprocess
from dataclasses import dataclass
from datetime import date

from .env_bootstrap import ROOT, bootstrap

bootstrap()

import market_api_budget
import market_data
import scoreboard


INSTANCE_PORT = 8893


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str


def _head() -> str:
    result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=15, check=False)
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
    try:
        state = json.loads((ROOT / "state" / "supervisor-state.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    head, deployed = _head(), str(state.get("deployed_sha") or "")
    checks = [Check("deployed-main", bool(head != "unknown" and deployed and head.startswith(deployed) and state.get("last_update_status") in {"DEPLOYED", "UP_TO_DATE"}), f"head={head[:12]} deployed={deployed[:12]} status={state.get('last_update_status')}"), Check("single-instance", instance_port_free(), "RIPTIDE instance port must be free")]
    connection = scoreboard.connect_db()
    try:
        generation, bankroll, trades = scoreboard.current_generation(connection, "RIPTIDE"), scoreboard.current_bankroll(connection, "RIPTIDE"), scoreboard.trade_count(connection, "RIPTIDE")
        flat = scoreboard.current_position_status(connection, "RIPTIDE") is None
    finally:
        connection.close()
    checks.append(Check("official-state", (generation == 1 and abs(bankroll - 1000) < .01 and trades == 0 and flat) if require_clean_start else generation >= 1, f"generation={generation} bankroll={bankroll:.2f} trades={trades} flat={flat}"))
    try:
        checks.append(Check("tradier-quote", bool(market_data.get_quote("SPY", priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT)), "live SPY quote available"))
        expirations = market_data.get_expirations("SPY", priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT)
        checks.append(Check("target-expiration", session_date.isoformat() in expirations, f"target={session_date.isoformat()} listed={session_date.isoformat() in expirations}"))
    except Exception as exc:
        checks.extend((Check("tradier-quote", False, f"{type(exc).__name__}: {exc}"), Check("target-expiration", False, "provider check failed")))
    return checks


def require_ready(*, session_date: date, require_clean_start: bool = True) -> list[Check]:
    checks = run(session_date=session_date, require_clean_start=require_clean_start)
    if failed := [check for check in checks if not check.passed]:
        raise RuntimeError("; ".join(f"{check.name}: {check.detail}" for check in failed))
    return checks
