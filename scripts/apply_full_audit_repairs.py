from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(
            f"{path}: expected one replacement, found {count}: {old[:100]!r}"
        )
    write(path, content.replace(old, new, 1))


def remove_once(path: str, old: str) -> None:
    replace_once(path, old, "")


write(
    "tradysquid/core/enums.py",
    '''from enum import StrEnum


class Regime(StrEnum):
    BULLISH_CONTROLLED = "BULLISH_CONTROLLED"
    BEARISH_CONTROLLED = "BEARISH_CONTROLLED"
    NEUTRAL_RANGE = "NEUTRAL_RANGE"
    NO_TRADE = "NO_TRADE"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"


class CandidateStatus(StrEnum):
    EVALUATED = "EVALUATED"
    REJECTED = "REJECTED"
    ELIGIBLE = "ELIGIBLE"
    RANKED = "RANKED"
    SELECTED = "SELECTED"
    OPENED = "OPENED"
    EXPIRED_UNUSED = "EXPIRED_UNUSED"
    ERROR = "ERROR"


class PositionState(StrEnum):
    CREATED = "CREATED"
    ENTRY_PENDING = "ENTRY_PENDING"
    OPEN = "OPEN"
    HOLD = "HOLD"
    PROFIT_PROTECTED = "PROFIT_PROTECTED"
    EXIT_PENDING = "EXIT_PENDING"
    CLOSED_WIN = "CLOSED_WIN"
    CLOSED_LOSS = "CLOSED_LOSS"
    CLOSED_BREAKEVEN = "CLOSED_BREAKEVEN"
    CLOSED_EXPIRED = "CLOSED_EXPIRED"
    CLOSED_DATA_FAILURE = "CLOSED_DATA_FAILURE"
    CANCELLED = "CANCELLED"
    ERROR = "ERROR"


class Direction(StrEnum):
    CALL = "call"
    PUT = "put"


class Structure(StrEnum):
    LONG_OPTION = "long-option"
    CREDIT_SPREAD = "credit-spread"


class DiagnosticCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    NETWORK = "NETWORK"
    PROVIDER = "PROVIDER"
    DATABASE = "DATABASE"
    DISCORD = "DISCORD"
    UNIVERSE = "UNIVERSE"
    STRATEGY = "STRATEGY"
    SCANNER = "SCANNER"
    PAPER_TRADING = "PAPER_TRADING"
    LEARNING = "LEARNING"
    REPORTING = "REPORTING"
    SCHEDULER = "SCHEDULER"
    APPLICATION = "APPLICATION"
    DEPLOYMENT = "DEPLOYMENT"
''',
)

replace_once(
    "tradysquid/core/config.py",
    """    if config['structure'] not in {'long-option','credit-spread'}:
        raise ValueError('structure must be long-option or credit-spread')
""",
    """    if config['structure'] not in {'long-option','credit-spread'}:
        raise ValueError('structure must be long-option or credit-spread')
    selection_mode = str(config['entry'].get('selection_mode', 'record-only'))
    supported_modes = {
        'record-only',
        'owner-confirmed paper entry',
        'automatically open qualified paper trades',
        'ranked top-N paper entries',
    }
    if selection_mode not in supported_modes:
        raise ValueError(
            'selection_mode must be record-only, owner-confirmed paper entry, '
            'automatically open qualified paper trades, or ranked top-N paper entries'
        )
""",
)

write(
    "tradysquid/scanner/selection.py",
    '''from __future__ import annotations

from ..core.enums import CandidateStatus


MANUAL_SELECTION_MODES = {
    "record-only",
    "owner-confirmed paper entry",
}
AUTOMATIC_SELECTION_MODES = {
    "automatically open qualified paper trades",
    "ranked top-N paper entries",
}


class CandidateSelector:
    """Apply configured paper-entry selection after every evaluation is recorded."""

    def select(self, decisions):
        by_strategy = {}
        for decision in decisions:
            by_strategy.setdefault(decision.strategy_id, []).append(decision)

        selected = []
        for group in by_strategy.values():
            eligible = [
                decision
                for decision in group
                if decision.status == CandidateStatus.ELIGIBLE
            ]
            if not eligible:
                continue

            eligible.sort(
                key=lambda decision: (
                    -decision.ranking_score,
                    decision.maximum_risk,
                    decision.candidate_id,
                )
            )
            mode = str(
                eligible[0].configuration_snapshot["entry"]["selection_mode"]
            )
            maximum = int(
                eligible[0].configuration_snapshot["entry"]
                ["maximum_selections_per_scan"]
            )
            if mode in MANUAL_SELECTION_MODES:
                continue
            if mode not in AUTOMATIC_SELECTION_MODES:
                raise ValueError(f"Unsupported selection mode: {mode}")

            for decision in eligible[:maximum]:
                decision.status = CandidateStatus.SELECTED
                selected.append(decision)
        return selected
''',
)

write(
    "tradysquid/trading/paper_broker.py",
    '''from __future__ import annotations

import json
import uuid

from ..core.enums import CandidateStatus, PositionState, Structure
from ..core.models import CandidateDecision, PaperLeg, PaperPosition, utc_now
from .fills import long_entry, short_entry


ACTIVE_STATES = {
    str(PositionState.OPEN),
    str(PositionState.HOLD),
    str(PositionState.PROFIT_PROTECTED),
    str(PositionState.EXIT_PENDING),
}
CLOSED_STATES = {
    str(PositionState.CLOSED_WIN),
    str(PositionState.CLOSED_LOSS),
    str(PositionState.CLOSED_BREAKEVEN),
    str(PositionState.CLOSED_EXPIRED),
    str(PositionState.CLOSED_DATA_FAILURE),
}


class PaperBroker:
    def __init__(self, database):
        self.db = database

    def open(self, decision: CandidateDecision) -> PaperPosition:
        if decision.status not in {
            CandidateStatus.ELIGIBLE,
            CandidateStatus.SELECTED,
        }:
            raise ValueError(
                "Only eligible or selected candidates can become paper positions"
            )
        if not decision.legs:
            raise ValueError("Candidate has no option legs")

        position_id = str(uuid.uuid4())
        cycle_id = str(uuid.uuid4())
        legs = []
        for leg in decision.legs:
            fill = (
                long_entry(leg.contract)
                if leg.side == "buy"
                else short_entry(leg.contract)
            )
            legs.append(
                PaperLeg(
                    leg.contract.symbol,
                    leg.side,
                    leg.quantity,
                    leg.contract.option_type,
                    leg.contract.strike,
                    leg.contract.expiration,
                    leg.contract.multiplier,
                    leg.contract.bid,
                    leg.contract.ask,
                    fill.price,
                )
            )

        entry_value = (
            decision.total_debit
            if decision.structure == Structure.LONG_OPTION
            else decision.total_credit
        )
        position = PaperPosition(
            position_id,
            decision.candidate_id,
            decision.strategy_id,
            decision.strategy_version,
            decision.strategy_hash,
            decision.symbol,
            decision.direction,
            decision.structure,
            PositionState.OPEN,
            utc_now(),
            legs,
            entry_value,
            decision.maximum_risk,
            float(
                decision.configuration_snapshot["management"]["profit_target_pct"]
            ),
            float(decision.configuration_snapshot["management"]["hard_stop_pct"]),
            entry_value,
            configuration_snapshot=decision.configuration_snapshot,
        )

        with self.db.transaction() as connection:
            connection.execute(
                "INSERT INTO trade_cycles("
                "id,candidate_id,strategy_id,started_at,status"
                ") VALUES (?,?,?,?,?)",
                (
                    cycle_id,
                    decision.candidate_id,
                    decision.strategy_id,
                    position.opened_at,
                    "OPEN",
                ),
            )
            connection.execute(
                "INSERT INTO paper_positions("
                "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,"
                "strategy_hash,symbol,direction,structure,state,opened_at,"
                "entry_value,current_value,maximum_risk,pnl_dollars,pnl_pct,"
                "mfe_pct,mae_pct,config_json"
                ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    position.position_id,
                    cycle_id,
                    position.candidate_id,
                    position.strategy_id,
                    position.strategy_version,
                    position.strategy_hash,
                    position.symbol,
                    str(position.direction),
                    str(position.structure),
                    str(position.state),
                    position.opened_at,
                    position.entry_value,
                    position.current_value,
                    position.maximum_risk,
                    0,
                    0,
                    0,
                    0,
                    json.dumps(position.configuration_snapshot, sort_keys=True),
                ),
            )
            for leg in legs:
                connection.execute(
                    "INSERT INTO paper_legs("
                    "position_id,contract_symbol,side,quantity,option_type,"
                    "strike,expiration,multiplier,entry_bid,entry_ask,entry_fill,"
                    "current_bid,current_ask,current_mark"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        position.position_id,
                        leg.contract_symbol,
                        leg.side,
                        leg.quantity,
                        leg.option_type,
                        leg.strike,
                        leg.expiration,
                        leg.multiplier,
                        leg.entry_bid,
                        leg.entry_ask,
                        leg.entry_fill,
                        0,
                        0,
                        0,
                    ),
                )
            self._event(
                connection,
                position.position_id,
                None,
                PositionState.OPEN,
                "paper-entry",
                "eligible candidate opened",
            )
            connection.execute(
                "UPDATE candidates SET status=? WHERE id=?",
                (str(CandidateStatus.OPENED), decision.candidate_id),
            )
        return position

    def open_candidate(self, candidate_id: str):
        from ..core.enums import Direction, Regime, Structure
        from ..core.models import CandidateDecision, CandidateLeg, OptionContract

        rows = self.db.query(
            "SELECT * FROM candidates WHERE id=?",
            (candidate_id,),
        )
        if not rows:
            raise KeyError(candidate_id)
        row = rows[0]
        if row["status"] not in {"ELIGIBLE", "SELECTED"}:
            raise ValueError("Candidate is not eligible for a paper position")

        raw_legs = self.db.query(
            "SELECT * FROM candidate_legs WHERE candidate_id=? ORDER BY id",
            (candidate_id,),
        )
        legs = []
        for raw in raw_legs:
            details = json.loads(raw["details_json"])
            contract = OptionContract(**details)
            legs.append(CandidateLeg(contract, raw["side"], raw["quantity"]))

        decision = CandidateDecision(
            candidate_id=row["id"],
            scan_cycle_id=row["scan_cycle_id"],
            strategy_id=row["strategy_id"],
            strategy_version=row["strategy_version"],
            strategy_hash=row["strategy_hash"],
            preset=row["preset"],
            symbol=row["symbol"],
            direction=Direction(row["direction"]),
            structure=Structure(row["structure"]),
            regime=Regime(row["regime"]),
            observed_at=row["observed_at"],
            underlying_price=0.0,
            legs=legs,
            setup_score=row["setup_score"],
            ranking_score=row["ranking_score"],
            status=CandidateStatus(row["status"]),
            total_debit=row["total_debit"],
            total_credit=row["total_credit"],
            maximum_risk=row["maximum_risk"],
            configuration_snapshot=json.loads(row["config_json"]),
        )
        return self.open(decision)

    @staticmethod
    def _exit_fill(side: str, bid: float, ask: float, slippage: float) -> float:
        if side == "buy":
            return max(float(bid) - slippage, 0.0)
        return max(float(ask), 0.0) + slippage

    def mark(
        self,
        position_id: str,
        leg_quotes: dict[str, tuple[float, float]],
    ) -> dict:
        rows = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?",
            (position_id,),
        )
        if not rows:
            raise KeyError(position_id)
        position = rows[0]
        if position["state"] in CLOSED_STATES:
            return {
                "position_id": position_id,
                "current_value": position["current_value"],
                "pnl_dollars": position["pnl_dollars"],
                "pnl_pct": position["pnl_pct"],
                "mfe_pct": position["mfe_pct"],
                "mae_pct": position["mae_pct"],
                "state": position["state"],
                "trigger": None,
            }

        legs = self.db.query(
            "SELECT * FROM paper_legs WHERE position_id=?",
            (position_id,),
        )
        config = json.loads(position["config_json"])
        slippage = float(
            config.get("management", {}).get("paper_slippage_per_share", 0.01)
        )
        signed_liquidation_value = 0.0

        with self.db.transaction() as connection:
            for leg in legs:
                bid, ask = leg_quotes[leg["contract_symbol"]]
                mark = (float(bid) + float(ask)) / 2
                liquidation = self._exit_fill(
                    leg["side"], float(bid), float(ask), slippage
                )
                signed = -1 if leg["side"] == "sell" else 1
                signed_liquidation_value += (
                    signed
                    * liquidation
                    * int(leg["multiplier"])
                    * int(leg["quantity"])
                )
                connection.execute(
                    "UPDATE paper_legs SET current_bid=?,current_ask=?,"
                    "current_mark=? WHERE id=?",
                    (bid, ask, mark, leg["id"]),
                )

            if position["structure"] == str(Structure.CREDIT_SPREAD):
                current_value = -signed_liquidation_value
                pnl = float(position["entry_value"]) - current_value
                denominator = max(float(position["maximum_risk"]), 0.01)
            else:
                current_value = signed_liquidation_value
                pnl = current_value - float(position["entry_value"])
                denominator = max(float(position["entry_value"]), 0.01)

            pnl_pct = pnl / denominator
            mfe = max(float(position["mfe_pct"]), pnl_pct)
            mae = min(float(position["mae_pct"]), pnl_pct)
            state = str(position["state"])
            trigger = None
            management = config.get("management", {})
            if state in ACTIVE_STATES:
                if pnl_pct >= float(management.get("profit_target_pct", 1.0)):
                    state = str(PositionState.EXIT_PENDING)
                    trigger = "profit target"
                elif pnl_pct <= -abs(float(management.get("hard_stop_pct", 1.0))):
                    state = str(PositionState.EXIT_PENDING)
                    trigger = "hard stop"

            connection.execute(
                "UPDATE paper_positions SET current_value=?,pnl_dollars=?,"
                "pnl_pct=?,mfe_pct=?,mae_pct=?,state=? WHERE id=?",
                (current_value, pnl, pnl_pct, mfe, mae, state, position_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO mfe_mae("
                "position_id,mfe_pct,mae_pct,updated_at"
                ") VALUES (?,?,?,?)",
                (position_id, mfe, mae, utc_now()),
            )
            connection.execute(
                "INSERT INTO position_marks("
                "id,position_id,value,pnl_dollars,pnl_pct,observed_at"
                ") VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), position_id, current_value, pnl, pnl_pct, utc_now()),
            )
            if trigger and state != str(position["state"]):
                self._event(
                    connection,
                    position_id,
                    PositionState(position["state"]),
                    PositionState.EXIT_PENDING,
                    "management",
                    trigger,
                )

        return {
            "position_id": position_id,
            "current_value": current_value,
            "pnl_dollars": pnl,
            "pnl_pct": pnl_pct,
            "mfe_pct": mfe,
            "mae_pct": mae,
            "state": state,
            "trigger": trigger,
        }

    def close(
        self,
        position_id: str,
        leg_quotes: dict[str, tuple[float, float]],
        reason: str = "owner-close",
    ) -> dict:
        existing = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?", (position_id,)
        )
        if not existing:
            raise KeyError(position_id)
        if existing[0]["state"] in CLOSED_STATES:
            outcome = self.db.query(
                "SELECT * FROM closed_outcomes WHERE position_id=?", (position_id,)
            )
            return {
                "position_id": position_id,
                "state": existing[0]["state"],
                "pnl_dollars": existing[0]["pnl_dollars"],
                "pnl_pct": existing[0]["pnl_pct"],
                "reason": outcome[0]["exit_reason"] if outcome else reason,
                "already_closed": True,
            }

        mark = self.mark(position_id, leg_quotes)
        position = self.db.query(
            "SELECT * FROM paper_positions WHERE id=?", (position_id,)
        )[0]
        pnl = float(mark["pnl_dollars"])
        final = (
            PositionState.CLOSED_WIN
            if pnl > 0
            else PositionState.CLOSED_LOSS
            if pnl < 0
            else PositionState.CLOSED_BREAKEVEN
        )
        closed_at = utc_now()
        config = json.loads(position["config_json"])
        slippage = float(
            config.get("management", {}).get("paper_slippage_per_share", 0.01)
        )

        with self.db.transaction() as connection:
            for leg in self.db.query(
                "SELECT * FROM paper_legs WHERE position_id=?", (position_id,)
            ):
                bid, ask = leg_quotes[leg["contract_symbol"]]
                connection.execute(
                    "UPDATE paper_legs SET exit_fill=? WHERE id=?",
                    (
                        self._exit_fill(
                            leg["side"], float(bid), float(ask), slippage
                        ),
                        leg["id"],
                    ),
                )
            connection.execute(
                "UPDATE paper_positions SET state=?,closed_at=? WHERE id=?",
                (str(final), closed_at, position_id),
            )
            connection.execute(
                "INSERT OR REPLACE INTO closed_outcomes("
                "position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at"
                ") VALUES (?,?,?,?,?,?)",
                (position_id, str(final), reason, pnl, mark["pnl_pct"], closed_at),
            )
            connection.execute(
                "UPDATE trade_cycles SET status=?,completed_at=? WHERE id=?",
                ("CLOSED", closed_at, position["trade_cycle_id"]),
            )
            self._event(
                connection,
                position_id,
                PositionState(position["state"]),
                final,
                "paper-exit",
                reason,
            )

        return {**mark, "state": str(final), "reason": reason}

    def _event(self, connection, position_id, previous, new, trigger, reason):
        connection.execute(
            "INSERT INTO lifecycle_events("
            "id,position_id,previous_state,new_state,trigger,reason,"
            "details_json,observed_at"
            ") VALUES (?,?,?,?,?,?,?,?)",
            (
                str(uuid.uuid4()),
                position_id,
                str(previous) if previous else None,
                str(new),
                trigger,
                reason,
                "{}",
                utc_now(),
            ),
        )
''',
)

write(
    "tradysquid/data/legacy_import.py",
    '''from __future__ import annotations

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
''',
)

replace_once(
    "tradysquid/app.py",
    "from .core.config import AppConfig\n",
    "from .core.config import AppConfig\nfrom .core.enums import CandidateStatus\n",
)
replace_once(
    "tradysquid/app.py",
    "from .data.database import Database\n",
    "from .data.database import Database\nfrom .data.legacy_import import import_legacy_closed_trades\n",
)
replace_once(
    "tradysquid/app.py",
    """        active_configs = self.db.active_strategy_configs(self.config.strategies)
        self.manager = RequestManager(self.db)
""",
    """        active_configs = self.db.active_strategy_configs(self.config.strategies)
        self.legacy_import = import_legacy_closed_trades(
            self.db,
            root / "state" / "ford-plays-log.csv",
            active_configs,
        )
        self.manager = RequestManager(self.db)
""",
)
replace_once(
    "tradysquid/app.py",
    '            "scan": self.scanner.scan_symbol,\n',
    '            "scan": self.scan_symbol,\n',
)
replace_once(
    "tradysquid/app.py",
    '''    def scan_all(self):
        total = 0
        for symbol in self.universe.active():
            try:
                total += len(self.scanner.scan_symbol(symbol, "scheduled"))
            except Exception as exc:
                self.diagnostics.observe(
                    "SCANNER",
                    symbol,
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        result = {"decisions": total}
        self.publisher.notify("scan")
        return result

    def monitor_positions(self):
        results = []
        for row in self.db.query(
            "SELECT id FROM paper_positions WHERE state IN "
            "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
        ):
            try:
                results.append(
                    self.paper.mark(
                        row["id"],
                        self._position_quotes(row["id"]),
                    )
                )
            except Exception as exc:
                self.diagnostics.observe(
                    "PAPER_TRADING",
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        if results:
            self.publisher.notify("paper")
        return results
''',
    '''    def scan_symbol(
        self,
        symbol: str,
        trigger: str = "manual",
        *,
        publish: bool = True,
    ):
        decisions = self.scanner.scan_symbol(symbol, trigger)
        opened = []
        for decision in decisions:
            mode = str(
                decision.configuration_snapshot.get("entry", {}).get(
                    "selection_mode",
                    "record-only",
                )
            )
            if (
                decision.status == CandidateStatus.SELECTED
                and mode
                in {
                    "automatically open qualified paper trades",
                    "ranked top-N paper entries",
                }
            ):
                try:
                    opened.append(self.paper.open(decision).__dict__)
                except Exception as exc:
                    self.diagnostics.observe(
                        "PAPER_TRADING",
                        decision.candidate_id,
                        f"{type(exc).__name__}: {exc}",
                        healthy=False,
                    )
        if publish:
            self.publisher.notify("scan")
            if opened:
                self.publisher.notify("paper")
        return decisions

    def scan_all(self):
        total = 0
        opened_before = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        for symbol in self.universe.active():
            try:
                total += len(self.scan_symbol(symbol, "scheduled", publish=False))
            except Exception as exc:
                self.diagnostics.observe(
                    "SCANNER",
                    symbol,
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        opened_after = self.db.query(
            "SELECT COUNT(*) AS n FROM paper_positions"
        )[0]["n"]
        result = {
            "decisions": total,
            "paper_positions_opened": max(
                int(opened_after) - int(opened_before), 0
            ),
        }
        self.publisher.notify("scan")
        if result["paper_positions_opened"]:
            self.publisher.notify("paper")
        return result

    def monitor_positions(self):
        results = []
        for row in self.db.query(
            "SELECT id FROM paper_positions WHERE state IN "
            "('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING')"
        ):
            try:
                quotes = self._position_quotes(row["id"])
                marked = self.paper.mark(row["id"], quotes)
                if marked["state"] == "EXIT_PENDING":
                    marked = self.paper.close(
                        row["id"],
                        quotes,
                        marked.get("trigger") or "management exit",
                    )
                results.append(marked)
            except Exception as exc:
                self.diagnostics.observe(
                    "PAPER_TRADING",
                    row["id"],
                    f"{type(exc).__name__}: {exc}",
                    healthy=False,
                )
        if results:
            self.publisher.notify("paper")
        return results
''',
)

remove_once(
    "tradysquid/discord/publishing.py",
    '''    if stable_id == "shadow-candidates" and isinstance(cleaned, list):
        total = len(cleaned)
        open_count = sum(
            not row.get("closed_at")
            for row in cleaned
            if isinstance(row, dict)
        )
        outcomes = Counter(
            str(row.get("outcome"))
            for row in cleaned
            if isinstance(row, dict) and row.get("outcome")
        )
        lines = [
            f"**Total tracked:** {total}",
            f"**Still open:** {open_count}",
            f"**Closed:** {total - open_count}",
            "**Source:** Rejected candidates",
        ]
        lines.extend(f"• {name}: {count}" for name, count in outcomes.most_common())
        return lines
''',
)
remove_once(
    "tradysquid/discord/publishing.py",
    '''        if stable_id == "shadow-candidates":
            return self.db.query(
                "SELECT source_status,outcome,opened_at,closed_at "
                "FROM shadow_candidates ORDER BY opened_at DESC LIMIT 20"
            )
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''        if stable_id in {"wins", "losses"}:
            operator = "=" if stable_id == "wins" else "<>"
            return self.db.query(
                "SELECT p.symbol,p.strategy_id,o.outcome,o.exit_reason,o.pnl_dollars,"
                "o.pnl_pct,o.closed_at FROM closed_outcomes o "
                "JOIN paper_positions p ON p.id=o.position_id "
                f"WHERE o.outcome {operator} 'WIN' ORDER BY o.closed_at DESC LIMIT 50"
            )
''',
    '''        if stable_id in {"wins", "losses"}:
            comparison = "> 0" if stable_id == "wins" else "< 0"
            return self.db.query(
                "SELECT p.symbol,p.strategy_id,o.outcome,o.exit_reason,o.pnl_dollars,"
                "o.pnl_pct,o.closed_at FROM closed_outcomes o "
                "JOIN paper_positions p ON p.id=o.position_id "
                f"WHERE o.pnl_dollars {comparison} "
                "ORDER BY o.closed_at DESC LIMIT 50"
            )
''',
)
remove_once(
    "tradysquid/discord/publishing.py",
    '                    "shadow-candidates",\n',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''    async def _publish_bootstrap_cards(self) -> dict[str, Any]:
''',
    '''    async def _publish_bootstrap_cards(
        self,
        *,
        stable_ids: set[str] | None = None,
    ) -> dict[str, Any]:
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''        for stable_id, channel_name, title in self.REQUIRED_BOOTSTRAP_CARDS:
            try:
''',
    '''        for stable_id, channel_name, title in self.REQUIRED_BOOTSTRAP_CARDS:
            if stable_ids is not None and stable_id not in stable_ids:
                continue
            try:
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''    )

    def __init__(
        self,
        database,
        root: Path,
        learning_center,
        services: dict[str, Callable[..., Any]],
''',
    '''    )

    CORE_BOOTSTRAP_IDS = frozenset(
        stable_id
        for stable_id, route in CARD_ROUTES.items()
        if bool(route.get("mandatory", False))
    )

    def __init__(
        self,
        database,
        root: Path,
        learning_center,
        services: dict[str, Callable[..., Any]],
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''        positions = self.db.query(
            "SELECT id FROM paper_positions ORDER BY opened_at DESC LIMIT 250"
        )
''',
    '''        positions = self.db.query(
            "SELECT id FROM paper_positions ORDER BY opened_at DESC"
        )
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''            cards = await self._publish_bootstrap_cards()
            learning = await self._publish_learning_center()
            journals = await self._publish_journals()
''',
    '''            cards = await self._publish_bootstrap_cards(
                stable_ids=set(self.CORE_BOOTSTRAP_IDS)
            )
            learning = {
                "status": "PENDING",
                "reconciled": 0,
                "failed": 0,
                "failures": [],
            }
            journals = {
                "status": "PENDING",
                "reconciled": 0,
                "failed": 0,
                "failures": [],
            }
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''            failures = (
                int(cards["mandatory_failed"])
                + int(learning["failed"])
                + int(journals["failed"])
                + len(missing_routes)
            )
''',
    '''            failures = int(cards["mandatory_failed"]) + len(missing_routes)
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''                "journals": journals,
                "routing_manifest": str(manifest_path),
''',
    '''                "journals": journals,
                "extended_backfill": {"status": "PENDING"},
                "routing_manifest": str(manifest_path),
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''                    f"mandatory cards={cards['mandatory_failed']}, "
                    f"learning={learning['failed']}, journals={journals['failed']}"
''',
    '''                    f"mandatory cards={cards['mandatory_failed']}"
''',
)
replace_once(
    "tradysquid/discord/publishing.py",
    '''    async def refresh(self, event: str = "all") -> None:
''',
    '''    async def complete_backfill(self) -> dict[str, Any]:
        """Populate non-core cards, all lessons, and all historical journals.

        This runs after core readiness so Discord history reconciliation cannot
        roll back an otherwise healthy scanner and paper-trading runtime.
        """

        async with self._refresh_lock:
            cards = await self._publish_bootstrap_cards()
            learning = await self._publish_learning_center()
            journals = await self._publish_journals()
            failures = (
                int(cards["failed"])
                + int(learning["failed"])
                + int(journals["failed"])
            )
            status = "PASS" if failures == 0 else "DEGRADED"
            receipt = {
                "status": status,
                "persistent_cards": cards,
                "learning_center": learning,
                "journals": journals,
                "completed_at": _utc_now(),
                "secret_values_written": False,
            }
            state_directory = self.root / "state"
            state_directory.mkdir(parents=True, exist_ok=True)
            (state_directory / "discord-extended-backfill.json").write_text(
                json.dumps(receipt, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            self._record_receipt("publishing-extended-backfill", status, receipt)
            return receipt

    async def refresh(self, event: str = "all") -> None:
''',
)

replace_once(
    "tradysquid/discord/bot.py",
    "import json\n",
    "import asyncio\nimport json\n",
)
replace_once(
    "tradysquid/discord/bot.py",
    '''        self.tree = None
''',
    '''        self.tree = None
        self.extended_task = None
''',
)
replace_once(
    "tradysquid/discord/bot.py",
    '''    async def start(self, token: str) -> None:
''',
    '''    async def _finish_extended_bootstrap(
        self,
        guild: Any,
        structure: DiscordStructureService,
        database: Any,
    ) -> None:
        receipt_path = self._readiness_path()
        try:
            current = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            current = {}

        try:
            extended = (
                await self.publishing.complete_backfill()
                if self.publishing is not None
                else {"status": "SKIPPED"}
            )
            retired = (
                await retire_stable_messages(
                    database,
                    guild,
                    bot_user_id=(
                        str(self.client.user.id)
                        if self.client and self.client.user
                        else ""
                    ),
                )
                if database is not None
                else {"status": "SKIPPED"}
            )
            protected_channel_ids = {
                str(channel.id)
                for channel in structure.resolved_channels.values()
                if getattr(channel, "id", None) is not None
            }
            cleanup = await structure.cleanup(
                guild,
                protected_channel_ids=protected_channel_ids,
                bot_user_id=(
                    str(self.client.user.id)
                    if self.client and self.client.user
                    else ""
                ),
            )
            statuses = {
                str(extended.get("status", "SKIPPED")),
                str(retired.get("status", "SKIPPED")),
                str(cleanup.get("status", "SKIPPED")),
            }
            final_status = "PASS" if statuses <= {"PASS", "SKIPPED"} else "DEGRADED"
            current.update(
                {
                    "status": final_status,
                    "extended_backfill": extended,
                    "retired_messages": retired,
                    "layout_cleanup": cleanup,
                    "extended_completed_at": _utc_now(),
                }
            )
        except Exception as exc:
            current.update(
                {
                    "status": "DEGRADED",
                    "extended_backfill": {
                        "status": "FAILED",
                        "error": f"{type(exc).__name__}: {exc}",
                    },
                    "extended_completed_at": _utc_now(),
                }
            )
        self._write_readiness(current)

    async def start(self, token: str) -> None:
''',
)
replace_once(
    "tradysquid/discord/bot.py",
    '''                retired_receipt = None
                if database is not None:
                    retired_receipt = await retire_stable_messages(
                        database,
                        guild,
                        bot_user_id=(
                            str(self.client.user.id) if self.client.user else ""
                        ),
                    )

                protected_channel_ids = {
                    str(channel.id)
                    for channel in structure.resolved_channels.values()
                    if getattr(channel, "id", None) is not None
                }
                cleanup_receipt = await structure.cleanup(
                    guild,
                    protected_channel_ids=protected_channel_ids,
                    bot_user_id=(
                        str(self.client.user.id) if self.client.user else ""
                    ),
                )
''',
    '''                retired_receipt = {"status": "PENDING"}
                cleanup_receipt = {"status": "PENDING"}
''',
)
replace_once(
    "tradysquid/discord/bot.py",
    '''                self._write_readiness(receipt)
                self.ready = True
''',
    '''                self._write_readiness(receipt)
                self.ready = True
                if self.extended_task and not self.extended_task.done():
                    self.extended_task.cancel()
                self.extended_task = asyncio.create_task(
                    self._finish_extended_bootstrap(guild, structure, database),
                    name="tradysquid-discord-extended-backfill",
                )
''',
)
replace_once(
    "tradysquid/discord/bot.py",
    '''    async def close(self) -> None:
        if self.client and not self.client.is_closed():
            await self.client.close()
''',
    '''    async def close(self) -> None:
        if self.extended_task and not self.extended_task.done():
            self.extended_task.cancel()
        if self.client and not self.client.is_closed():
            await self.client.close()
''',
)

replace_once(
    "tradysquid/discord/structure.py",
    '''            *[
                channel
                for category in self.invented_categories
                for channel in _category_channels(category)
            ],
''',
    '''            *[
                channel
                for category in self.invented_categories
                for channel in _category_channels(category)
                if _name(channel).casefold() in MIGRATION_CHANNEL_NAMES
            ],
''',
)
replace_once(
    "tradysquid/discord/structure.py",
    '''            async for message in history(limit=100, oldest_first=False):
''',
    '''            async for message in history(limit=None, oldest_first=False):
''',
)
replace_once(
    "tradysquid/discord/structure.py",
    '''        candidate_ids = {_object_id(item) for item in self.cleanup_candidates}
        for channel in all_channels:
            category_is_invented = _category_name(channel).upper() in INVENTED_CATEGORIES
            name_is_migration = _name(channel).casefold() in MIGRATION_CHANNEL_NAMES
            if category_is_invented or name_is_migration:
                candidate_ids.add(_object_id(channel))
''',
    '''        candidate_ids = {
            _object_id(item)
            for item in self.cleanup_candidates
            if _category_name(item).upper() in INVENTED_CATEGORIES
            and _name(item).casefold() in MIGRATION_CHANNEL_NAMES
        }
''',
)

replace_once(
    "scripts/auto_install_clean_rebuild.ps1",
    '''function Start-LegacySupervisor {
''',
    '''function Export-TradysquidScheduledTasks {
    param([Parameter(Mandatory = $true)][string]$Destination)

    $TaskDirectory = Join-Path $Destination 'scheduled-tasks'
    New-Item -ItemType Directory -Force -Path $TaskDirectory | Out-Null
    $Records = @()
    $Index = 0
    foreach ($Task in @(Get-ScheduledTask -ErrorAction SilentlyContinue | Where-Object {
        $_.TaskName -like '*Tradysquid*'
    })) {
        $FileName = ('task-{0:D3}.xml' -f $Index)
        $XmlPath = Join-Path $TaskDirectory $FileName
        Export-ScheduledTask -TaskName $Task.TaskName -TaskPath $Task.TaskPath |
            Set-Content -LiteralPath $XmlPath -Encoding Unicode
        $Records += [pscustomobject]@{
            task_name = [string]$Task.TaskName
            task_path = [string]$Task.TaskPath
            xml_file = $FileName
        }
        $Index++
    }
    $Records | ConvertTo-Json -Depth 5 |
        Set-Content -LiteralPath (Join-Path $TaskDirectory 'manifest.json') -Encoding UTF8
}

function Restore-TradysquidScheduledTasks {
    param([Parameter(Mandatory = $true)][string]$Source)

    $TaskDirectory = Join-Path $Source 'scheduled-tasks'
    $ManifestPath = Join-Path $TaskDirectory 'manifest.json'
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) { return }
    $Raw = Get-Content -LiteralPath $ManifestPath -Raw | ConvertFrom-Json
    foreach ($Record in @($Raw)) {
        $XmlPath = Join-Path $TaskDirectory ([string]$Record.xml_file)
        if (-not (Test-Path -LiteralPath $XmlPath -PathType Leaf)) { continue }
        $Xml = Get-Content -LiteralPath $XmlPath -Raw
        Register-ScheduledTask `
            -TaskName ([string]$Record.task_name) `
            -TaskPath ([string]$Record.task_path) `
            -Xml $Xml `
            -Force | Out-Null
    }
}

function Start-LegacySupervisor {
''',
)
replace_once(
    "scripts/auto_install_clean_rebuild.ps1",
    '''    $EnvironmentHash = Copy-RuntimeSnapshot -Root $Repository -Destination $BackupRoot
''',
    '''    $EnvironmentHash = Copy-RuntimeSnapshot -Root $Repository -Destination $BackupRoot
    Export-TradysquidScheduledTasks -Destination $BackupRoot
''',
)
replace_once(
    "scripts/auto_install_clean_rebuild.ps1",
    '''        if ($BackupRoot) {
            try { Restore-RuntimeSnapshot -Root $Repository -Source $BackupRoot } catch { $Status = 'FAILED' }
        }
''',
    '''        if ($BackupRoot) {
            try { Restore-RuntimeSnapshot -Root $Repository -Source $BackupRoot } catch { $Status = 'FAILED' }
            try { Restore-TradysquidScheduledTasks -Source $BackupRoot } catch { $Status = 'FAILED' }
        }
''',
)

write(
    "docs/CURRENT-REQUIREMENTS.md",
    '''# Current requirements traceability

This document reflects the owner-approved runtime after the August 3, 2026
Discord-layout and full-audit corrections. Repository tests prove code behavior;
only a receipt from the owner computer can prove live deployment.

| Requirement | Implementation | Configuration / data | Automated proof | Live proof |
|---|---|---|---|---|
| Exactly six independent option strategies | `tradysquid/strategies`, `config/strategies/*.json` | strategy profiles, versions, acknowledgements | strategy and installation tests | running registry receipt |
| Rotating optionable universe, maximum 25 | `tradysquid/universe` | `config/defaults.json`, universe tables | universe tests | active-universe receipt/card |
| Global maximum $100 paper risk | `tradysquid/trading/risk.py` | strategy filters and defaults | risk/fill tests | controlled rejection |
| Accepted and rejected candidate tracking | `tradysquid/scanner` | candidate/evidence/rejection tables | scanner tests | current scan receipt |
| No shadow-trading feature | no active shadow command, route, scheduler job, status, table, or renderer | obsolete bot-authored message/channel cleanup only | full-audit regression tests | retired-message cleanup receipt |
| Automatic paper-entry modes actually open selected candidates | `Application.scan_symbol`, `PaperBroker.open` | versioned `entry.selection_mode` | full-audit regression tests | paper-entry lifecycle receipt |
| Stops and targets actually close positions | `Application.monitor_positions`, `PaperBroker.mark/close` | position marks, closed outcomes, lifecycle events | paper lifecycle tests | closed outcome and journal |
| Existing legacy closed paper trades are preserved | `tradysquid/data/legacy_import.py` | ignored `state/ford-plays-log.csv` to canonical SQLite ledger | idempotent importer tests | import receipt and historical cards |
| Original Discord dashboard plus Strategy Control | `tradysquid/discord/layout.py`, `structure.py` | `config/discord-schema.json`, saved channel IDs | Discord layout tests | Discord readiness receipt |
| No SCANNING, PAPER TRADING, or LEARNING CENTER 2 dashboard | safe migration cleanup in `structure.py` | cleanup receipts | migration tests | live cleanup receipt |
| Stable readable cards update in place | publishing and message reconciliation | Discord message state | publishing tests | acknowledged message IDs |
| One Learning Center with 27 numbered lessons | learning catalog and original channel mapping | `config/learning-center.json` | Learning Center tests | extended backfill receipt |
| One stable Trade Journal thread per paper position | `discord/journals.py`, forum reconciliation | journal state | journal tests | extended backfill receipt |
| Closed trades populate Wins, Losses, Performance, and Learning | canonical `closed_outcomes` queries | SQLite ledger | historical-card regression tests | Discord card acknowledgements |
| Core startup does not wait for every historical journal | core bootstrap plus asynchronous extended backfill | core and extended receipts | bootstrap contract tests | both live receipts |
| Scanning and position monitoring begin immediately | scheduler startup jobs | scheduler receipts | scheduler tests | recent scheduler runs |
| Complete `.env`, data, state, and logs survive handoff | automatic handoff and setup scripts | external backup | installer contract tests | handoff receipt |
| Rollback restores prior scheduled tasks | `auto_install_clean_rebuild.ps1` | task XML backup | PowerShell contract test | rollback receipt plus task inventory |
| Read-only Tradier only | `tradysquid/providers/tradier.py` | market-data endpoints | forbidden-write tests | provider readiness |
| One Windows application PID | process lock and startup task | PID/startup receipts | process-lock tests | exactly-one-process acceptance |

## Current deployment boundary

The tested target is not considered installed merely because GitHub CI passes.
Live completion requires the owner computer to produce current PASS receipts for
automatic handoff, setup, application startup, Discord core readiness, and the
extended Discord backfill.
''',
)

replace_once(
    "tests/test_feature_restoration_contract.py",
    '''        if "closed_outcomes" in normalized and "= 'WIN'" in normalized:
''',
    '''        if "closed_outcomes" in normalized and "pnl_dollars > 0" in normalized:
''',
)
replace_once(
    "tests/test_feature_restoration_contract.py",
    '''        if "closed_outcomes" in normalized and "<> 'WIN'" in normalized:
''',
    '''        if "closed_outcomes" in normalized and "pnl_dollars < 0" in normalized:
''',
)

write(
    "tests/test_full_audit_regressions.py",
    '''from __future__ import annotations

import csv
import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

from tradysquid.app import Application
from tradysquid.core.config import AppConfig, validate_strategy_config
from tradysquid.core.enums import CandidateStatus, Regime
from tradysquid.core.models import OptionContract
from tradysquid.data.database import Database
from tradysquid.data.legacy_import import import_legacy_closed_trades
from tradysquid.discord.layout import CARD_ROUTES
from tradysquid.discord.publishing import DiscordPublishingService
from tradysquid.learning.center import LearningCenter
from tradysquid.strategies.registry import StrategyRegistry
from tradysquid.trading.paper_broker import PaperBroker


ROOT = Path(__file__).resolve().parents[1]


class Publisher:
    def __init__(self):
        self.events = []

    def notify(self, event):
        self.events.append(event)


class Diagnostics:
    def __init__(self):
        self.events = []

    def observe(self, *args, **kwargs):
        self.events.append((args, kwargs))


def _eligible_call(config):
    contract = OptionContract(
        "CALL",
        "X",
        (date.today() + timedelta(days=14)).isoformat(),
        100,
        "call",
        0.70,
        0.80,
        100,
        500,
        0.40,
    )
    strategy = StrategyRegistry(config.strategies).get("regular-call")
    decision = strategy.evaluate(
        "scan", "X", 100, Regime.BULLISH_CONTROLLED, [contract], 80
    )
    decision.status = CandidateStatus.SELECTED
    decision.configuration_snapshot["entry"]["selection_mode"] = (
        "automatically open qualified paper trades"
    )
    return decision


def test_shadow_is_not_an_active_runtime_status_or_route():
    assert not hasattr(CandidateStatus, "SHADOW")
    assert "shadow-candidates" not in CARD_ROUTES
    publishing = (ROOT / "tradysquid/discord/publishing.py").read_text(
        encoding="utf-8"
    )
    assert 'stable_id == "shadow-candidates"' not in publishing
    assert '"shadow-candidates",' not in publishing


def test_shadow_selection_mode_is_rejected():
    config = AppConfig.load(ROOT).strategies["regular-call"]
    changed = json.loads(json.dumps(config))
    changed["entry"]["selection_mode"] = "shadow-only"
    try:
        validate_strategy_config(changed)
    except ValueError as exc:
        assert "selection_mode" in str(exc)
    else:
        raise AssertionError("shadow-only selection mode was accepted")


def test_selected_candidate_auto_opens_paper_position(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "auto-open.db")
    database.initialize()
    database.register_strategies(config.strategies)
    decision = _eligible_call(config)

    app = object.__new__(Application)
    app.scanner = SimpleNamespace(scan_symbol=lambda symbol, trigger: [decision])
    app.paper = PaperBroker(database)
    app.db = database
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()

    result = Application.scan_symbol(app, "X", "test")

    assert len(result) == 1
    assert database.query("SELECT COUNT(*) AS n FROM paper_positions")[0]["n"] == 1
    assert "scan" in app.publisher.events
    assert "paper" in app.publisher.events


def test_target_hit_closes_position_in_monitor(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "auto-close.db")
    database.initialize()
    database.register_strategies(config.strategies)
    decision = _eligible_call(config)
    broker = PaperBroker(database)
    position = broker.open(decision)

    app = object.__new__(Application)
    app.db = database
    app.paper = broker
    app.publisher = Publisher()
    app.diagnostics = Diagnostics()
    app._position_quotes = lambda position_id: {"CALL": (1.20, 1.25)}

    results = Application.monitor_positions(app)

    assert results[0]["state"] == "CLOSED_WIN"
    assert database.query(
        "SELECT outcome FROM closed_outcomes WHERE position_id=?",
        (position.position_id,),
    )[0]["outcome"] == "CLOSED_WIN"
    assert "paper" in app.publisher.events


def test_legacy_closed_trade_import_is_idempotent(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "legacy.db")
    database.initialize()
    database.register_strategies(config.strategies)
    source = tmp_path / "ford-plays-log.csv"
    with source.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "trade_id",
                "timestamp",
                "play_type",
                "ticker",
                "call_or_put",
                "entry_contract_value",
                "max_risk",
                "outcome",
                "pct_gain_loss",
                "realized_pl_dollars",
                "closed_at",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "trade_id": "old-1",
                "timestamp": "2026-07-01T14:00:00+00:00",
                "play_type": "REGULAR",
                "ticker": "F",
                "call_or_put": "CALL",
                "entry_contract_value": "80",
                "max_risk": "80",
                "outcome": "WIN",
                "pct_gain_loss": "25",
                "realized_pl_dollars": "20",
                "closed_at": "2026-07-01T15:00:00+00:00",
            }
        )

    first = import_legacy_closed_trades(database, source, config.strategies)
    second = import_legacy_closed_trades(database, source, config.strategies)

    assert first["imported"] == 1
    assert second["already_present"] == 1
    assert database.query("SELECT COUNT(*) AS n FROM closed_outcomes")[0]["n"] == 1


def test_wins_and_losses_use_pnl_sign_not_old_labels(tmp_path):
    config = AppConfig.load(ROOT)
    database = Database(tmp_path / "cards.db")
    database.initialize()
    database.register_strategies(config.strategies)
    publisher = DiscordPublishingService(
        database,
        tmp_path,
        LearningCenter(config.learning_center),
        {
            "health": lambda: {},
            "version": lambda: "test",
            "open_positions": lambda: [],
            "report": lambda *args: {},
            "strategies": lambda: [],
        },
    )
    now = "2026-08-03T15:00:00+00:00"
    for suffix, pnl, outcome in (
        ("win", 10.0, "CLOSED_WIN"),
        ("loss", -5.0, "CLOSED_LOSS"),
        ("flat", 0.0, "CLOSED_BREAKEVEN"),
    ):
        database.execute(
            "INSERT INTO trade_cycles(id,candidate_id,strategy_id,started_at,status) "
            "VALUES (?,?,?,?,?)",
            (f"cycle-{suffix}", f"candidate-{suffix}", "regular-call", now, "CLOSED"),
        )
        database.execute(
            "INSERT INTO paper_positions("
            "id,trade_cycle_id,candidate_id,strategy_id,strategy_version,strategy_hash,"
            "symbol,direction,structure,state,opened_at,closed_at,entry_value,current_value,"
            "maximum_risk,pnl_dollars,pnl_pct,mfe_pct,mae_pct,config_json"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"position-{suffix}",
                f"cycle-{suffix}",
                f"candidate-{suffix}",
                "regular-call",
                "1",
                "hash",
                suffix.upper(),
                "call",
                "long-option",
                outcome,
                now,
                now,
                50,
                50 + pnl,
                50,
                pnl,
                pnl / 50,
                max(pnl / 50, 0),
                min(pnl / 50, 0),
                "{}",
            ),
        )
        database.execute(
            "INSERT INTO closed_outcomes("
            "position_id,outcome,exit_reason,pnl_dollars,pnl_pct,closed_at"
            ") VALUES (?,?,?,?,?,?)",
            (f"position-{suffix}", outcome, "test", pnl, pnl / 50, now),
        )

    assert [row["symbol"] for row in publisher._card_value("wins")] == ["WIN"]
    assert [row["symbol"] for row in publisher._card_value("losses")] == ["LOSS"]


def test_core_bootstrap_is_bounded_and_extended_backfill_is_separate():
    source = (ROOT / "tradysquid/discord/publishing.py").read_text(encoding="utf-8")
    assert "CORE_BOOTSTRAP_IDS" in source
    assert "async def complete_backfill" in source
    assert "discord-extended-backfill.json" in source
    assert "ORDER BY opened_at DESC LIMIT 250" not in source


def test_rollback_restores_scheduled_tasks():
    source = (ROOT / "scripts/auto_install_clean_rebuild.ps1").read_text(
        encoding="utf-8"
    )
    assert "Export-TradysquidScheduledTasks" in source
    assert "Restore-TradysquidScheduledTasks" in source
    assert "Export-ScheduledTask" in source
    assert "Register-ScheduledTask" in source


def test_cleanup_does_not_select_channels_by_name_alone():
    source = (ROOT / "tradysquid/discord/structure.py").read_text(encoding="utf-8")
    assert "history(limit=None" in source
    assert "category_is_invented or name_is_migration" not in source
''',
)

print("Full audit repairs applied.")
