"""GROK autonomous paper runtime."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from bots.grok import BOT_NAME
from bots.grok.contract_selection import select_contract
from bots.grok.engine import Decision, evaluate_entry, evaluate_exit
from bots.grok.preflight import run_preflight
from bots.grok.sizing import decide_contracts
from bots.grok.state import load_state, save_state

logger = logging.getLogger("grok.runtime")


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


class GrokRuntime:
    def __init__(
        self,
        *,
        scoreboard_conn: Any,
        get_features: Callable[[], dict[str, Any]],
        get_chain: Callable[[], list[dict[str, Any]]],
        get_underlying: Callable[[], dict[str, Any]],
        is_session_open: Callable[[], bool],
        minutes_to_close: Callable[[], float],
        provider_ok: Callable[[], bool],
    ):
        self.sb = scoreboard_conn
        self.get_features = get_features
        self.get_chain = get_chain
        self.get_underlying = get_underlying
        self.is_session_open = is_session_open
        self.minutes_to_close = minutes_to_close
        self.provider_ok = provider_ok
        self.private = load_state()
        self._running = False

    def recover(self) -> None:
        import scoreboard as sb

        gen = sb.current_generation(self.sb, BOT_NAME)
        bankroll = sb.current_bankroll(self.sb, BOT_NAME)
        pos = sb.current_position_status(self.sb, BOT_NAME)
        self.private.current_generation = gen
        save_state(self.private)
        logger.info(
            "recovered GROK gen=%s bankroll=%.2f position=%s",
            gen, bankroll, "OPEN" if pos else "FLAT",
        )

    def preflight(self) -> bool:
        import scoreboard as sb

        pos = sb.current_position_status(self.sb, BOT_NAME)
        session_open = self.is_session_open()
        result = run_preflight(
            scoreboard_available=True,
            market_data_available=True,
            today_0dte_available=True,
            provider_reachable=self.provider_ok(),
            no_open_position=pos is None,
            session_open=True,
        )
        if not result.ok:
            logger.error("preflight failed: %s", result.failures)
            return False
        if not session_open:
            logger.info("session closed; runtime idle-capable")
        for w in result.warnings:
            logger.warning("preflight warning: %s", w)
        return True

    def cycle(self) -> Decision:
        import scoreboard as sb

        if not self.is_session_open():
            return Decision(action="NO_ACTION", reason="session closed")

        pos = sb.current_position_status(self.sb, BOT_NAME)
        features = self.get_features() or {}
        bankroll = sb.current_bankroll(self.sb, BOT_NAME)
        gen = sb.current_generation(self.sb, BOT_NAME)

        if pos is not None:
            chain = self.get_chain() or []
            symbol = pos.get("contract_symbol")
            current_bid = 0.0
            for c in chain:
                if c.get("symbol") == symbol or c.get("option_symbol") == symbol:
                    current_bid = float(c.get("bid") or 0)
                    break
            opened = pos.get("opened_at") or _now_iso()
            try:
                opened_dt = datetime.fromisoformat(opened)
                minutes_held = (
                    datetime.now(opened_dt.tzinfo) - opened_dt
                ).total_seconds() / 60.0
            except Exception:
                minutes_held = 0.0

            decision = evaluate_exit(
                position=pos,
                features=features,
                current_bid=current_bid,
                minutes_held=minutes_held,
                minutes_to_close=self.minutes_to_close(),
            )
            logger.info(
                "EXIT_EVAL action=%s bid=%.2f reason=%s",
                decision.action, current_bid, decision.reason,
            )
            if decision.action == "EXIT" and current_bid > 0:
                self._close_trade(pos, current_bid, decision.reason)
            return decision

        if bankroll < 5.0:
            self._maybe_bust(bankroll)
            return Decision(action="NO_ACTION", reason="bankroll too low")

        chain = self.get_chain() or []
        logger.info(
            "CYCLE bars=%s ret3=%s ret5=%s chain=%s bankroll=%.2f",
            features.get("bar_count"),
            features.get("ret_3m"),
            features.get("ret_5m"),
            len(chain),
            bankroll,
        )

        decision = evaluate_entry(features, chain, bankroll)
        if decision.action != "ENTER" or not decision.side:
            logger.info("NO_ENTER reason=%s rejected=%s", decision.reason, decision.rejected[:3])
            return decision

        selected = select_contract(decision.side, chain, bankroll, decision.confidence)
        if selected is None:
            logger.warning(
                "ENTER signal but no contract side=%s chain=%s",
                decision.side, len(chain),
            )
            return Decision(
                action="NO_ACTION",
                reason="no fillable contract",
                candidates_considered=decision.candidates_considered,
                rejected=decision.rejected
                + [{"family": decision.family or "", "reason": "contract selection failed"}],
            )

        contracts = decide_contracts(
            selected.ask, bankroll, decision.confidence, selected.spread_pct
        )
        if contracts < 1:
            contracts = selected.contracts
        if contracts < 1:
            return Decision(action="NO_ACTION", reason="unaffordable after sizing")

        self._open_trade(
            side=decision.side,
            symbol=selected.symbol,
            entry_price=selected.ask,
            contracts=contracts,
            generation=gen,
            bankroll=bankroll,
            family=decision.family or "unknown",
            reason=f"{decision.reason} | {selected.reason}",
        )
        return decision

    def _open_trade(
        self,
        *,
        side: str,
        symbol: str,
        entry_price: float,
        contracts: int,
        generation: int,
        bankroll: float,
        family: str,
        reason: str,
    ) -> None:
        import scoreboard as sb

        trade_id = f"GROK-{generation}-{uuid.uuid4().hex[:10]}"
        sb.record_trade_open(
            self.sb,
            trade_id=trade_id,
            bot=BOT_NAME,
            generation=generation,
            opened_at=_now_iso(),
            side=side,
            contract_symbol=symbol,
            entry_price=entry_price,
            contracts=contracts,
            entry_bankroll=bankroll,
        )
        logger.info(
            "OPEN %s %s x%s @ %.2f family=%s reason=%s",
            side, symbol, contracts, entry_price, family, reason,
        )
        self.private.decision_log_tail.append({
            "at": _now_iso(),
            "action": "ENTER",
            "trade_id": trade_id,
            "side": side,
            "symbol": symbol,
            "family": family,
            "reason": reason,
        })
        self.private.decision_log_tail = self.private.decision_log_tail[-200:]
        save_state(self.private)

    def _close_trade(self, pos: dict[str, Any], exit_price: float, reason: str) -> None:
        import scoreboard as sb

        trade_id = pos["trade_id"]
        entry = float(pos["entry_price"])
        contracts = int(pos["contracts"])
        pnl = (exit_price - entry) * 100 * contracts
        sb.record_trade_close(
            self.sb,
            trade_id=trade_id,
            closed_at=_now_iso(),
            exit_price=exit_price,
            pnl_usd=pnl,
        )
        logger.info("CLOSE %s pnl=%.2f reason=%s", trade_id, pnl, reason)
        self.private.decision_log_tail.append({
            "at": _now_iso(),
            "action": "EXIT",
            "trade_id": trade_id,
            "pnl": pnl,
            "reason": reason,
        })
        self.private.decision_log_tail = self.private.decision_log_tail[-200:]
        save_state(self.private)

    def _maybe_bust(self, bankroll: float) -> None:
        import scoreboard as sb

        min_qualifying = 15.0
        if bankroll + 0.01 >= min_qualifying:
            return
        gen = sb.current_generation(self.sb, BOT_NAME)
        try:
            sb.record_generation_event(
                self.sb,
                bot=BOT_NAME,
                generation=gen,
                event="BUSTED",
                detail=f"bankroll {bankroll:.2f} cannot fund min qualifying trade",
                minimum_qualifying_cost=min_qualifying,
            )
            sb.record_generation_event(
                self.sb,
                bot=BOT_NAME,
                generation=gen + 1,
                event="STARTED",
                detail="post-bust reset to $1000",
            )
            self.private.current_generation = gen + 1
            save_state(self.private)
            logger.warning("GROK generation %s BUSTED → started %s", gen, gen + 1)
        except ValueError as exc:
            logger.info("bust check skipped: %s", exc)

    def start(self) -> None:
        self.recover()
        if not self.preflight():
            raise RuntimeError("GROK preflight failed — refusing to start")
        self._running = True
        logger.info("GROK runtime started")

    def stop(self) -> None:
        self._running = False
        save_state(self.private)
        logger.info("GROK runtime stopped")
