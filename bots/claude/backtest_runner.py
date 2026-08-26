"""Phase 13 v2: AXIOM's own backtest orchestration.

Walks backtest_lab.MarketView bar-by-bar (causal - never sees a bar past
the point being evaluated), running the exact same hypothesis-pool
selection logic the live runtime uses, then records an honest,
reproducible entry via backtest_lab.record_backtest.

Uses a FRESH, isolated, in-memory evolution state per run
(evolution.connect_db(":memory:")) with its own local pnl-by-hypothesis
tracking, injected as select_hypothesis's/update_fitness_and_evolve's
fitness_fn - a backtest run never reads or writes the live
state/axiom_evolution.db or scoreboard.db, and never appends to the
shared evolution_log.jsonl audit trail. This keeps every backtest run
fully self-contained and reproducible.

Only a handful of trading days of real captured SPY data exist as of
this phase - not a statistically meaningful sample. This module is run
as an integration/mechanism proof (the pipeline, selection, and
record_backtest call work end-to-end, honestly tiered), not to lock any
of parameters.py's values. Re-running this periodically as more real
data accrues is how those values eventually get refined; nothing in
AXIOM's live path is blocked on that happening first (owner directive,
2026-08-25).
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

import backtest_lab
import market_data

from bots.claude import contract_selection, evolution, exits, sizing
from bots.claude.execution import build_execution_assumptions, entry_fill_price, exit_fill_price
from bots.claude.parameters import HYPOTHESIS_DEFAULTS

_TIER_SEVERITY = {backtest_lab.TIER_A: 0, backtest_lab.TIER_B: 1, backtest_lab.TIER_C: 2}


def _bar_datetime(bar: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(str(bar["bar_time"])).replace(tzinfo=market_data.MARKET_TZ)


def _simulate_day(
    view: backtest_lab.MarketView,
    day: date,
    evo_conn,
    local_pnls: dict[str, list[float]],
    starting_bankroll: float,
    tiers_seen: list[str],
) -> list[dict[str, Any]]:
    def local_fitness_fn(_connection, name: str) -> tuple[float | None, int]:
        return evolution.fitness_from_pnls(local_pnls[name])

    end_of_day = datetime.combine(day, datetime.max.time()).replace(tzinfo=market_data.MARKET_TZ)
    bars = view.bars_as_of(end_of_day, lookback_minutes=16 * 60)
    session_bars = [b for b in bars if b["bar_time"][:10] == day.isoformat()]
    if not session_bars:
        return []

    trades: list[dict[str, Any]] = []
    open_trade: dict[str, Any] | None = None
    open_contract: dict[str, Any] | None = None
    open_hypothesis: str | None = None
    open_params: dict[str, float] | None = None

    for i in range(len(session_bars)):
        window = session_bars[: i + 1]
        current_dt = _bar_datetime(session_bars[i])
        current_price = session_bars[i]["close"]
        causal = backtest_lab.compute_features(window)

        if open_trade is None:
            selected = evolution.select_hypothesis(evo_conn, current_price, causal or {}, fitness_fn=local_fitness_fn)
            if selected is None:
                continue
            snapshot = view.options_as_of(current_dt)
            tiers_seen.append(snapshot["tier"])
            confidence = selected.decision.contributing_signals.get("confidence", 0.5)
            contract = contract_selection.select_contract(
                snapshot["contracts"], selected.decision.side, day, selected.params, confidence=confidence
            )
            if contract is None:
                continue
            ask = contract["ask"]
            contracts_count = sizing.position_size(starting_bankroll, ask, selected.params)
            if contracts_count <= 0:
                continue
            open_trade = {
                "opened_at": current_dt.isoformat(),
                "side": selected.decision.side,
                "contract_symbol": contract["option_symbol"],
                "entry_price": entry_fill_price(contract),
                "contracts": contracts_count,
            }
            open_contract = contract
            open_hypothesis = selected.name
            open_params = selected.params
            continue

        snapshot = view.options_as_of(current_dt)
        tiers_seen.append(snapshot["tier"])
        matched = next(
            (c for c in snapshot["contracts"] if c["option_symbol"] == open_trade["contract_symbol"]),
            None,
        )
        if matched is None:
            continue
        open_contract = matched
        decision = exits.should_exit(
            {"entry_price": open_trade["entry_price"]}, matched, current_dt, open_params
        )
        if not decision.should_exit:
            continue
        exit_price = exit_fill_price(matched)
        pnl_usd = (exit_price - open_trade["entry_price"]) * 100 * open_trade["contracts"]
        trades.append(
            {
                **open_trade,
                "hypothesis": open_hypothesis,
                "closed_at": current_dt.isoformat(),
                "exit_price": exit_price,
                "exit_reason": decision.reason,
                "pnl_usd": pnl_usd,
            }
        )
        local_pnls[open_hypothesis].append(pnl_usd)
        open_trade = None
        open_contract = None
        open_hypothesis = None
        open_params = None

    if open_trade is not None and open_contract is not None:
        exit_price = exit_fill_price(open_contract)
        pnl_usd = (exit_price - open_trade["entry_price"]) * 100 * open_trade["contracts"]
        trades.append(
            {
                **open_trade,
                "hypothesis": open_hypothesis,
                "closed_at": _bar_datetime(session_bars[-1]).isoformat(),
                "exit_price": exit_price,
                "exit_reason": "END_OF_SIMULATED_DAY",
                "pnl_usd": pnl_usd,
            }
        )
        local_pnls[open_hypothesis].append(pnl_usd)

    return trades


def _summarize(trades: list[dict[str, Any]]) -> dict[str, Any]:
    by_hypothesis: dict[str, dict[str, Any]] = {}
    for name in HYPOTHESIS_DEFAULTS:
        own = [t for t in trades if t["hypothesis"] == name]
        if own:
            total = sum(t["pnl_usd"] for t in own)
            wins = [t for t in own if t["pnl_usd"] > 0]
            by_hypothesis[name] = {
                "trade_count": len(own),
                "total_pnl_usd": total,
                "win_rate": len(wins) / len(own),
                "expectancy_usd": total / len(own),
            }
        else:
            by_hypothesis[name] = {"trade_count": 0, "total_pnl_usd": 0.0, "win_rate": None, "expectancy_usd": None}

    if not trades:
        return {"trade_count": 0, "total_pnl_usd": 0.0, "win_rate": None, "expectancy_usd": None,
                "by_hypothesis": by_hypothesis}
    total = sum(t["pnl_usd"] for t in trades)
    wins = [t for t in trades if t["pnl_usd"] > 0]
    return {
        "trade_count": len(trades),
        "total_pnl_usd": total,
        "win_rate": len(wins) / len(trades),
        "expectancy_usd": total / len(trades),
        "by_hypothesis": by_hypothesis,
        "trades": trades,
    }


def run_backtest(
    start_date: date,
    end_date: date,
    bot_version: str = "axiom-v2",
    random_seed: int | None = None,
) -> dict[str, Any]:
    view = backtest_lab.MarketView("SPY")
    evo_conn = evolution.connect_db(":memory:")
    local_pnls: dict[str, list[float]] = defaultdict(list)
    tiers_seen: list[str] = []
    all_trades: list[dict[str, Any]] = []
    trading_days_with_bars = 0

    def local_fitness_fn(_connection, name: str) -> tuple[float | None, int]:
        return evolution.fitness_from_pnls(local_pnls[name])

    current = start_date
    while current <= end_date:
        day_trades = _simulate_day(view, current, evo_conn, local_pnls, 1000.0, tiers_seen)
        if day_trades or view.bars_as_of(
            datetime.combine(current, datetime.max.time()).replace(tzinfo=market_data.MARKET_TZ)
        ):
            trading_days_with_bars += 1
        all_trades.extend(day_trades)
        # Evolve once per simulated day, isolated to this run's in-memory
        # state - never touches live evolution/scoreboard state or the
        # shared audit log.
        evolution.update_fitness_and_evolve(evo_conn, fitness_fn=local_fitness_fn, log_path=None)
        current += timedelta(days=1)

    if tiers_seen:
        evidence_tier = max(tiers_seen, key=lambda t: _TIER_SEVERITY.get(t, 2))
    else:
        evidence_tier = backtest_lab.TIER_C

    results = _summarize(all_trades)
    fingerprint = backtest_lab.dataset_fingerprint("SPY", start_date, end_date)
    data_quality = {
        "trading_days_with_bar_data": trading_days_with_bars,
        "disclosure": (
            "Only a handful of trading days of real captured SPY data exist as of "
            "this run - not a statistically meaningful sample. This run is an "
            "integration/mechanism proof, not a parameter-locking measurement."
        ),
    }

    return backtest_lab.record_backtest(
        bot_version=bot_version,
        dataset_fingerprint=fingerprint,
        date_range=(start_date.isoformat(), end_date.isoformat()),
        evidence_tier=evidence_tier,
        data_quality=data_quality,
        feature_versions={"backtest_lab": backtest_lab.FEATURE_VERSION},
        execution_assumptions=build_execution_assumptions(),
        parameters={name: dict(params) for name, params in HYPOTHESIS_DEFAULTS.items()},
        random_seed=random_seed,
        results=results,
    )
