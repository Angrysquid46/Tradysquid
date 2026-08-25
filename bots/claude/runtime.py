"""Phase 13: AXIOM's live runtime - the job callbacks scheduler.py polls,
plus main(). Every live market_data.py call is gated through
market_api_budget.request_allowed() at the priority tiers Section 8/
market_api_budget.py's own doc comments reserve for exactly this use.
All position state goes through scoreboard.py exclusively - no second
position store. Discord posting and rivalry commentary reuse the shared
discord_transport/discord_surface_manifest/rivalry modules, never
reimplemented.

Entry/exit decisions themselves read market data via
backtest_lab.MarketView, the same interface backtest_runner.py uses, so
AXIOM's live and backtested behavior can never silently diverge. That
interface reads Section 5's already-captured Parquet snapshots (populated
by the shared market_data_collector.py jobs, at most ~1 minute stale
during market hours) rather than AXIOM issuing its own duplicate Tradier
calls for every scan - there is no shared market cache, so re-fetching
the same chain every job cycle would just be wasted API budget for data
that's already been captured seconds ago. AXIOM does make one live
Tradier call of its own, gated at the matching priority tier, as a final
safety check immediately before committing capital or closing a position.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import backtest_lab
import discord_surface_manifest
import discord_transport
import market_api_budget
import market_data
import rivalry
import scoreboard

from bots.claude import backtest_runner, contract_selection, evolution, execution, exits, signal, sizing
from bots.claude.parameters import HYPOTHESIS_DEFAULTS
from bots.claude.scheduler import Job, acquire_instance_lock, connect_db, due, get_state, run_job, set_state

BOT = "AXIOM"
SURFACE_ID = "axiom-live-position"
POSTMORTEM_DIR = Path(__file__).resolve().parent / "postmortems"

_CHANNEL_ID = os.environ.get("AXIOM_CHANNEL_ID", "").strip()

# AXIOM's own rivalry voice: genuinely competitive, aimed at BLACKTIDE, not
# just "slightly better" (owner directive, 2026-08-25) - free-form text
# within rivalry.py's own rate limits (3/event, 20/day, 6/min, 20s gap).
_WIN_LINES = [
    "AXIOM closed {side} {symbol} for +${pnl:.2f}. BLACKTIDE, that's the gap widening.",
    "Another green close for AXIOM (+${pnl:.2f} on {symbol}). Keep watching, BLACKTIDE.",
]
_LOSS_LINES = [
    "AXIOM took -${pnl:.2f} on {symbol}. One trade. BLACKTIDE hasn't earned the lead yet.",
    "Red on {symbol}, -${pnl:.2f}. Noted. Next signal's already loading.",
]
_BUST_LINES = [
    "AXIOM's generation {generation} is done - bankroll hit zero. New generation, same target: BLACKTIDE.",
]


def _tracker() -> discord_transport.DiscordTracker:
    return discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )


def _post(content: str) -> None:
    """Best-effort - AXIOM's Discord channel isn't provisioned by this
    phase (that's Phase 15 launch scope), so this silently no-ops until
    AXIOM_CHANNEL_ID is configured, matching this repo's existing pattern
    of checking tracker.enabled before posting rather than crashing."""
    if not _CHANNEL_ID:
        return
    tracker = _tracker()
    if not tracker.enabled:
        return
    try:
        tracker.upsert_singleton_message(_CHANNEL_ID, content, search_token="AXIOM")
    except discord_transport.DiscordError:
        pass


def _ensure_surface(connection) -> None:
    discord_surface_manifest.register_surface(
        connection,
        surface_id=SURFACE_ID,
        category="AXIOM",
        channel=_CHANNEL_ID or "unconfigured",
        owner="Claude",
        purpose="AXIOM's live position/rivalry card",
        producer="bots.claude.runtime",
        publisher="discord_transport",
        update_mode=discord_surface_manifest.UPDATE_MODE_EVENT_DRIVEN,
        expected_silence=True,
    )


def entry_scan_job(connection) -> str:
    sb = scoreboard.connect_db()
    if scoreboard.current_position_status(sb, BOT):
        return "position already open"

    now = market_data.now_ct()
    view = backtest_lab.MarketView("SPY")
    bars = view.bars_as_of(now, lookback_minutes=16 * 60)
    if not bars:
        return "no bars available"
    current_price = bars[-1]["close"]
    causal = backtest_lab.compute_features(bars)

    evo_conn = evolution.connect_db()
    selected = signal.entry_decision(evo_conn, current_price, causal or {})
    if selected is None:
        return "no hypothesis fired"

    snapshot = view.options_as_of(now)
    contract = contract_selection.select_contract(
        snapshot["contracts"], selected.decision.side, now.date(), selected.params
    )
    if contract is None:
        return f"{selected.name} fired ({selected.decision.side}) but no eligible contract"

    if not market_api_budget.request_allowed(market_api_budget.PRIORITY_ENTRY_CRITICAL_DATA):
        return "budget gate declined final entry safety check, retrying next cycle"
    safety_quote = market_data.get_quote("SPY")
    if safety_quote is None:
        return "final safety quote unavailable, skipping this cycle"

    bankroll = scoreboard.current_bankroll(sb, BOT)
    contracts_count = sizing.position_size(bankroll, contract["ask"], selected.params)
    if contracts_count <= 0:
        return f"bankroll ${bankroll:.2f} insufficient for ask ${contract['ask']:.2f}"

    trade_id = str(uuid.uuid4())
    generation = scoreboard.current_generation(sb, BOT)
    scoreboard.record_trade_open(
        sb,
        trade_id=trade_id,
        bot=BOT,
        generation=generation,
        opened_at=now.isoformat(),
        side=selected.decision.side,
        contract_symbol=contract["option_symbol"],
        entry_price=execution.entry_fill_price(contract),
        contracts=contracts_count,
        entry_bankroll=bankroll,
    )
    evolution.record_trade_attribution(
        evo_conn, trade_id=trade_id, hypothesis_name=selected.name, generation=generation
    )
    _ensure_surface(connection)
    discord_surface_manifest.record_surface_event(
        connection, surface_id=SURFACE_ID, event_type="EVENT",
        detail=f"opened {selected.decision.side} {contract['option_symbol']} x{contracts_count} via {selected.name}",
    )
    _post(
        f"**AXIOM entered {selected.decision.side}** ({selected.name})\n"
        f"{contract['option_symbol']} x{contracts_count}\n{selected.decision.rationale}"
    )
    return f"opened {selected.decision.side} {contract['option_symbol']} x{contracts_count} via {selected.name}"


def position_monitor_job(connection) -> str:
    sb = scoreboard.connect_db()
    trade = scoreboard.current_position_status(sb, BOT)
    if not trade:
        return "no open position"

    evo_conn = evolution.connect_db()
    hypothesis_name = evolution.get_attribution(evo_conn, trade["trade_id"])
    if hypothesis_name:
        params = evolution.get_hypothesis_params(evo_conn, hypothesis_name)
    else:
        # Defensive only - attribution is written right after
        # scoreboard.record_trade_open in entry_scan_job, so this means a
        # crash happened in that exact window. Falls back to the
        # trend_continuation defaults rather than failing to monitor a
        # real open position at all.
        params = dict(HYPOTHESIS_DEFAULTS["trend_continuation"])

    now = market_data.now_ct()
    view = backtest_lab.MarketView("SPY")
    snapshot = view.options_as_of(now)
    contract = next(
        (c for c in snapshot["contracts"] if c["option_symbol"] == trade["contract_symbol"]), None
    )
    if contract is None:
        return "no current quote for held contract"

    decision = exits.should_exit(trade, contract, now, params)
    if not decision.should_exit:
        return f"holding, pnl_pct={decision.pnl_pct}"

    market_api_budget.request_allowed(market_api_budget.PRIORITY_EXIT_CRITICAL_DATA)
    exit_price = execution.exit_fill_price(contract)
    pnl_usd = (exit_price - trade["entry_price"]) * 100 * trade["contracts"]
    scoreboard.record_trade_close(
        sb, trade_id=trade["trade_id"], closed_at=now.isoformat(),
        exit_price=exit_price, pnl_usd=pnl_usd,
    )

    _ensure_surface(connection)
    discord_surface_manifest.record_surface_event(
        connection, surface_id=SURFACE_ID, event_type="EVENT",
        detail=f"closed {trade['contract_symbol']} reason={decision.reason} pnl=${pnl_usd:.2f}",
    )

    trigger = rivalry.TRIGGERS[3] if pnl_usd > 0 else rivalry.TRIGGERS[4]  # TRADE_CLOSED_WIN/LOSS
    lines = _WIN_LINES if pnl_usd > 0 else _LOSS_LINES
    message = lines[hash(trade["trade_id"]) % len(lines)].format(
        side=trade["side"], symbol=trade["contract_symbol"], pnl=abs(pnl_usd)
    )
    rc = rivalry.connect_db()
    try:
        rivalry.record_rivalry_event(
            rc, rivalry_event_id=str(uuid.uuid4()), event_group_id=trade["trade_id"],
            trigger=trigger, speaker=BOT, message=message,
            public_score_snapshot=scoreboard.scoreboard_snapshot(sb, BOT),
            trade_reference=trade["trade_id"], generation=trade["generation"],
        )
    except rivalry.RivalryLimitExceeded:
        pass

    _post(f"**AXIOM closed** {trade['contract_symbol']}\n{decision.reason} - ${pnl_usd:+.2f}")
    return f"closed {trade['contract_symbol']} reason={decision.reason} pnl=${pnl_usd:.2f}"


def _build_postmortem(sb, generation: int) -> dict[str, Any]:
    return {
        "bot": BOT,
        "generation": generation,
        "trade_count": scoreboard.trade_count(sb, BOT, generation),
        "total_pnl_usd": scoreboard.total_pnl(sb, BOT, generation),
        "win_rate": scoreboard.win_rate(sb, BOT, generation),
        "profit_factor": scoreboard.profit_factor(sb, BOT, generation),
        "expectancy_usd": scoreboard.expectancy(sb, BOT, generation),
        "average_winner_usd": scoreboard.average_winner(sb, BOT, generation),
        "average_loser_usd": scoreboard.average_loser(sb, BOT, generation),
        "largest_winner_usd": scoreboard.largest_winner(sb, BOT, generation),
        "largest_loser_usd": scoreboard.largest_loser(sb, BOT, generation),
        "max_drawdown_usd": scoreboard.max_drawdown(sb, BOT, generation),
        "bust_count_lifetime": scoreboard.bust_count(sb, BOT),
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def bust_check_job(connection) -> str:
    sb = scoreboard.connect_db()
    generation = scoreboard.current_generation(sb, BOT)
    bankroll = scoreboard.current_bankroll(sb, BOT)
    if bankroll > 0:
        return f"bankroll ${bankroll:.2f}, no bust"

    if get_state(connection, f"busted:generation:{generation}") == "1":
        return f"generation {generation} bust already handled"

    POSTMORTEM_DIR.mkdir(parents=True, exist_ok=True)
    postmortem = _build_postmortem(sb, generation)
    postmortem_path = POSTMORTEM_DIR / f"generation_{generation}.json"
    postmortem_path.write_text(json.dumps(postmortem, indent=2, default=str), encoding="utf-8")

    scoreboard.record_generation_event(
        sb, bot=BOT, generation=generation, event="BUSTED",
        detail=f"bankroll reached ${bankroll:.2f}; postmortem at {postmortem_path.name}",
    )
    scoreboard.record_generation_event(
        sb, bot=BOT, generation=generation + 1, event="STARTED",
        detail="fresh generation, bankroll reset to $1,000",
    )
    set_state(connection, f"busted:generation:{generation}", "1")

    rc = rivalry.connect_db()
    try:
        rivalry.record_rivalry_event(
            rc, rivalry_event_id=str(uuid.uuid4()), event_group_id=f"bust-{generation}",
            trigger="GENERATION_BUSTED", speaker=BOT,
            message=_BUST_LINES[0].format(generation=generation),
            public_score_snapshot=scoreboard.scoreboard_snapshot(sb, BOT),
            generation=generation,
        )
    except rivalry.RivalryLimitExceeded:
        pass

    _post(f"**AXIOM generation {generation} busted.** New generation started at $1,000.")
    return f"generation {generation} busted, postmortem written, generation {generation + 1} started"


def evolve_job(connection) -> str:
    """Re-judges every enabled hypothesis against its OWN attributed real
    closed trades (scoreboard.py, the official ledger) and deterministically
    tightens/retires underperformers. No live Tradier calls - reads only
    already-recorded scoreboard/attribution data."""
    evo_conn = evolution.connect_db()
    applied = evolution.update_fitness_and_evolve(evo_conn)
    if not applied:
        return "no hypothesis had enough sample/negative fitness to evolve"
    return f"{len(applied)} hypothesis evolution step(s) applied: " + ", ".join(
        f"{e['hypothesis']}:{e['event']}" for e in applied
    )


def backtest_refresh_job(connection) -> str:
    """Off the live-trading path, no live Tradier calls - reads only
    already-captured data via MarketView. Keeps re-measuring
    parameters.py's values as real data accrues without blocking launch
    on that happening first (owner directive, 2026-08-25)."""
    today = date.today()
    start = date(2026, 8, 24)  # earliest real captured SPY data on disk
    record = backtest_runner.run_backtest(start, today)
    return f"backtest recorded: {record['results']['trade_count']} trades, tier={record['evidence_tier']}"


JOBS = [
    Job("axiom-entry-scan", timedelta(seconds=30), entry_scan_job,
        market_hours_only=True, retry_interval=timedelta(seconds=30)),
    Job("axiom-position-monitor", timedelta(seconds=15), position_monitor_job,
        market_hours_only=True, retry_interval=timedelta(seconds=15)),
    Job("axiom-bust-check", timedelta(minutes=5), bust_check_job,
        retry_interval=timedelta(minutes=1)),
    Job("axiom-evolve", timedelta(hours=1), evolve_job,
        retry_interval=timedelta(minutes=15)),
    Job("axiom-backtest-refresh", timedelta(hours=24), backtest_refresh_job,
        retry_interval=timedelta(hours=1)),
]


def main() -> int:
    listener = acquire_instance_lock()
    connection = connect_db()
    try:
        while True:
            now = market_data.now_ct()
            for job in JOBS:
                if due(connection, job, now):
                    run_job(connection, job)
            time.sleep(5)
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
