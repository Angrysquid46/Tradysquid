from __future__ import annotations

import csv
import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..core.models import utc_now


IMPORT_SETTING_KEY = "migration.legacy-closed-trades-v1"


def _number(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _percent(value: Any) -> float:
    number = _number(value)
    return number / 100.0 if abs(number) > 2 else number


def _strategy_id(row: dict[str, str]) -> str:
    play = str(row.get("play_type") or "").casefold().replace("_", " ")
    side = str(row.get("call_or_put") or "").casefold()
    if "bull" in play and "put" in play:
        return "bull-put-spread"
    if "bear" in play and "call" in play:
        return "bear-call-spread"
    if "swing" in play:
        return "swing-put" if "put" in side else "swing-call"
    return "regular-put" if "put" in side else "regular-call"


def _outcome(row: dict[str, str], pnl: float) -> str | None:
    raw = str(row.get("outcome") or "").strip().upper()
    closed_at = str(row.get("closed_at") or "").strip()
    if not raw and not closed_at:
        return None
    if "WIN" in raw or pnl > 0:
        return "CLOSED_WIN"
    if "LOSS" in raw or pnl < 0:
        return "CLOSED_LOSS"
    if "EXPIRED" in raw:
        return "CLOSED_EXPIRED"
    return "CLOSED_BREAKEVEN"


def _stable_id(trade_id: str) -> str:
    digest = hashlib.sha256(trade_id.encode("utf-8")).hexdigest()[:24]
    return f"legacy-{digest}"


def import_legacy_closed_trades(
    database,
    csv_path: Path,
    strategy_configs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Import completed legacy paper trades into the canonical SQLite ledger."""

    result = {
        "status": "SKIPPED",
        "source": str(csv_path),
        "imported": 0,
        "already_present": 0,
        "skipped_open_or_ambiguous": 0,
        "errors": [],
        "observed_at": utc_now(),
    }
    if not csv_path.exists():
        return result

    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))

    for index, row in enumerate(rows, 1):
        trade_id = str(row.get("trade_id") or f"row-{index}").strip()
        position_id = _stable_id(trade_id)
        pnl = _number(
            row.get("realized_pl_dollars"),
            _number(row.get("current_pl_dollars")),
        )
        outcome = _outcome(row, pnl)
        if outcome is None:
            result["skipped_open_or_ambiguous"] += 1
            continue
        if database.query("SELECT 1 FROM paper_positions WHERE id=?", (position_id,)):
            result["already_present"] += 1
            continue

        try:
            strategy_id = _strategy_id(row)
            strategy = deepcopy(strategy_configs[strategy_id])
            strategy["_legacy_import"] = {
                "source": "state/ford-plays-log.csv",
                "trade_id": trade_id,
                "historical_configuration_exact": False,
            }
            opened_at = (
                str(row.get("timestamp") or "").strip()
                or str(row.get("last_evaluated_at") or "").strip()
                or utc_now()
            )
            closed_at = (
                str(row.get("closed_at") or "").strip()
                or str(row.get("last_evaluated_at") or "").strip()
                or opened_at
            )
            entry_value = _number(
                row.get("entry_contract_value"),
                _number(row.get("cost_or_credit")) * 100.0,
            )
            if entry_value <= 0:
                entry_value = max(_number(row.get("entry_price")) * 100.0, 0.01)
            maximum_risk = max(_number(row.get("max_risk"), entry_value), 0.01)
            pnl_pct = _percent(row.get("pct_gain_loss"))
            if pnl_pct == 0 and entry_value:
                pnl_pct = pnl / entry_value
            mfe = _percent(row.get("max_favorable_pct"))
            mae = _percent(row.get("max_adverse_pct"))
            current_value = max(entry_value + pnl, 0.0)
            direction = (
                "put"
                if "put" in str(row.get("call_or_put") or "").casefold()
                else "call"
            )
            structure = (
                "credit-spread"
                if strategy_id in {"bull-put-spread", "bear-call-spread"}
                else "long-option"
            )
            cycle_id = f"{position_id}-cycle"
            candidate_id = f"{position_id}-candidate"

            with database.transaction() as connection:
                connection.execute(
                    "INSERT INTO trade_cycles("
                    "id,candidate_id,strategy_id,started_at,completed_at,status"
                    ") VALUES (?,?,?,?,?,?)",
                    (cycle_id, candidate_id, strategy_id, opened_at, closed_at, "CLOSED"),
                )
                connection.execute(
                    "INSERT INTO paper_positions("
                    "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,"
                    "strategy_hash,symbol,direction,structure,state,opened_at,"
                    "closed_at,entry_value,current_value,maximum_risk,pnl_dollars,"
                    "pnl_pct,mfe_pct,mae_pct,config_json"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        position_id,
                        cycle_id,
                        candidate_id,
                        strategy_id,
                        str(strategy.get("version", "legacy")),
                        str(strategy.get("configuration_hash", "legacy")),
                        str(row.get("ticker") or "UNKNOWN").upper(),
                        direction,
                        structure,
                        outcome,
                        opened_at,
                        closed_at,
                        entry_value,
                        current_value,
                        maximum_risk,
                        pnl,
                        pnl_pct,
                        mfe,
                        mae,
                        json.dumps(strategy, sort_keys=True),
                    ),
                )
                connection.execute(
                    "INSERT INTO closed_outcomes("
                    "position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at"
                    ") VALUES (?,?,?,?,?,?)",
                    (
                        position_id,
                        outcome,
                        str(row.get("last_signal") or row.get("discord_status") or "legacy-close"),
                        pnl,
                        pnl_pct,
                        closed_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO lifecycle_events("
                    "id,position_id,previous_state,new_state,trigger,reason,"
                    "details_json,observed_at"
                    ") VALUES (?,?,?,?,?,?,?,?)",
                    (
                        f"{position_id}-open",
                        position_id,
                        None,
                        "OPEN",
                        "legacy-import",
                        "Imported historical paper entry",
                        "{}",
                        opened_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO lifecycle_events("
                    "id,position_id,previous_state,new_state,trigger,reason,"
                    "details_json,observed_at"
                    ") VALUES (?,?,?,?,?,?,?,?)",
                    (
                        f"{position_id}-close",
                        position_id,
                        "OPEN",
                        outcome,
                        "legacy-import",
                        "Imported historical paper close",
                        "{}",
                        closed_at,
                    ),
                )
            result["imported"] += 1
        except Exception as exc:
            result["errors"].append(
                {"trade_id": trade_id, "error": f"{type(exc).__name__}: {exc}"}
            )

    result["status"] = "PASS" if not result["errors"] else "DEGRADED"
    result["observed_at"] = utc_now()
    database.execute(
        "INSERT OR REPLACE INTO settings(key,value_json,updated_at) VALUES (?,?,?)",
        (
            IMPORT_SETTING_KEY,
            json.dumps(result, sort_keys=True),
            result["observed_at"],
        ),
    )
    return result
