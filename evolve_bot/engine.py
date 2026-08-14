"""One scan cycle for the evolve bot: reprice/close open positions, then
look for one new entry if capital allows. Phase 1 deliberately reuses
spy_scanner's already-proven 0DTE opening-range signal, exit rules, and
contract-selection logic (delta band, liquidity, ask-price sanity bounds)
rather than reimplementing them from scratch - "trades on existing
rule-based signals from day one" per the design.

The exit rule specifically is evolvable as of Phase 12: evaluate_exit_for_row
below calls logic_state.current_exit_signal instead of spy_scanner's exit
function directly, so an owner-approved Phase 12 proposal (applied via
apply_proposal.py) can override the live stop/target/floor levels for
this bot's own trades without touching spy_scanner.py at all. Until a
proposal is ever applied, logic_state falls straight back to
spy_scanner's own live constants - identical behavior to every earlier
phase.

spy_scanner is imported directly for its Tradier data-fetch and signal
math only - confirmed its own imports (and everything it imports) are
pure stdlib + requests, no Flask/PyNaCl/openai/Pillow, so this works
cleanly from evolve_bot's own isolated venv with no dependency conflict.
Never touches spy_scanner's Discord/state paths - those all require a
live DiscordTracker this bot deliberately doesn't have yet (Phase 1 is
explicitly local-only, no Discord wiring until there's something real to
show).
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

import bankroll
import discord_post
import logic_state
import market_features
import model_scoring
import self_tuning
import tradelog

PLAY_TYPE = "SPY_EVOLVE"
ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
BANKROLL_PATH = STATE_DIR / "bankroll.json"
TRADELOG_PATH = STATE_DIR / "trades.csv"

# Phase 7, deliberately OFF by default: shadow mode (Phase 6) has logged
# exactly one real prediction as of 2026-08-12, nowhere near enough
# closed shadow trades to know whether the model's scores track real
# outcomes. The model_score_at_entry column below is always populated on
# every real trade regardless of this flag - purely informational, zero
# behavior change - so historical trades already carry the model's
# opinion for later analysis. Only the actual skip-the-trade behavior is
# gated. Flip EVOLVE_MODEL_FILTER_ENABLED=true once shadow mode has
# enough history to trust; nothing else about this file needs to change.
MODEL_FILTER_ENABLED = os.environ.get("EVOLVE_MODEL_FILTER_ENABLED", "false").strip().lower() == "true"
MODEL_MIN_WIN_PROBABILITY = float(os.environ.get("EVOLVE_MODEL_MIN_WIN_PROBABILITY", "0.5"))


def build_thesis(candidate: dict[str, Any], context: dict[str, Any], market_condition: str) -> str:
    """A real thesis grounded in the actual signal values behind this
    trade, not invented after the fact - the owner's explicit ask."""
    return (
        f"{candidate['call_or_put'].upper()} on the {context['regime']} opening-range breakout "
        f"({context.get('reason', '')}). Delta {candidate['delta']}, IV "
        f"{candidate['iv'] if candidate['iv'] != '' else 'n/a'}, market condition at entry: "
        f"{market_condition}."
    )


def evaluate_exit_for_row(row: dict[str, str], quote: dict[str, Any] | None, timestamp) -> dict[str, Any] | None:
    """Pure exit-evaluation step for one open row against one real quote -
    no bankroll logic, so shadow.py (Phase 6) can reuse this identically
    against its own hypothetical open rows instead of re-implementing the
    exit-signal walk. Mutates the row's running peak/trough tracking
    fields as a side effect (needed for the NEXT evaluation regardless of
    whether this one closes the position) but never the outcome/close
    fields - only the caller, which knows whether real capital is
    involved, does that. Returns None when there's nothing usable to
    evaluate (missing/unreliable quote, or no real entry price)."""
    if not quote or not s.quote_is_reliable_for_exit(quote):
        # A 0DTE option that's already past its own expiration date will
        # NEVER get a usable quote again - Tradier purges expired symbols
        # almost immediately (confirmed empirically in Phase 2). Without
        # this fallback, a position whose quote went bad right as it
        # should have force-closed (e.g. a widening spread in the final
        # minutes before expiry) gets orphaned forever: no quote means
        # this function always returns None, which means it's never
        # re-evaluated, which means it can never close. Found live
        # 2026-08-13: EVOLVE-20260812-002 sat OPEN a full day past its
        # own expiration, silently blocking every new entry since this
        # bot only holds one position at a time.
        expiration = row.get("expiration", "")
        if expiration and expiration < timestamp.date().isoformat():
            entry = s.as_float(row.get("entry_price"), 0.0) or 0.0
            row["last_evaluated_at"] = timestamp.isoformat()
            return {
                "signal": "EXPIRATION CLOSE",
                "note": "Forced closed: past its own expiration date with no final quote available.",
                "mark": 0.0,
                "entry": entry,
                "pnl_pct": -100.0,
                "peak_pct": s.as_float(row.get("max_favorable_pct"), 0.0) or 0.0,
                "trough_pct": s.as_float(row.get("max_adverse_pct"), 0.0) or 0.0,
                "should_close": True,
            }
        return None
    entry = s.as_float(row.get("entry_price"), 0.0) or 0.0
    if entry <= 0:
        return None
    mark = s.conservative_option_exit(quote)
    close_time = timestamp.replace(
        hour=s.MARKET_CLOSE[0], minute=s.MARKET_CLOSE[1], second=0, microsecond=0
    )
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    pnl_pct = (mark - entry) / entry * 100
    peak_pct = max(s.as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct, pnl_pct)
    trough_pct = min(s.as_float(row.get("max_adverse_pct"), pnl_pct) or pnl_pct, pnl_pct)
    signal, note = logic_state.current_exit_signal(entry, mark, minutes_remaining, peak_pct)
    row["last_evaluated_at"] = timestamp.isoformat()
    row["max_favorable_pct"] = str(round(peak_pct))
    row["max_adverse_pct"] = str(round(trough_pct))
    return {
        "signal": signal,
        "note": note,
        "mark": mark,
        "entry": entry,
        "pnl_pct": pnl_pct,
        "peak_pct": peak_pct,
        "trough_pct": trough_pct,
        "should_close": signal in s.CLOSING_SIGNALS,
    }


def _post_trade_card(trade_id: str, content: str) -> None:
    """One upserted card per trade_id, edited in place across its whole
    lifecycle (open -> live-held updates -> final close), instead of a
    separate permanent 'opened' message plus a separate 'held' card -
    owner: "why's it showing 2 cards for every trade?" (both landed in
    the single #evolve-trades channel, since this bot - unlike the main
    system's separate entry/updates/exit channels - only has one trades
    channel). Once a trade closes this key is never upserted again, so
    the final message simply stays put as that trade's permanent record
    - satisfies "still be able to track history" without a second card.
    Same fail-soft contract as before: a Discord problem here must never
    affect the real position tracking that already happened above."""
    if not trade_id:
        return
    try:
        discord_post.upsert_message("trades", f"trade:{trade_id}", content)
    except discord_post.DiscordPostError:
        pass


def _refresh_dashboard() -> None:
    """Keeps the #evolve-dashboard cards (stats/milestones/equity curve)
    current - called only when a trade actually opened or closed this
    cycle (see run_cycle), not on every ~3-minute tick regardless of
    activity. Originally ran unconditionally every cycle (fixing a
    different complaint: the dashboard going stale mid-day under the old
    once-a-day gate), but upsert_message/upsert_file used to delete and
    repost a brand-new message on every refresh - Discord push-notifies
    on a new message but not on an edit, so posting on a fixed timer
    regardless of activity meant a real phone notification every ~3
    minutes even on a day with zero trades. Owner: "it's spamming the
    fuck out of me even without trades... it simply needs to update per
    trade." Now gated on real activity AND upsert_message/upsert_file
    edit the existing message in place (see discord_post.py) - both
    matter, since even an edit-in-place still doesn't need to happen
    when nothing changed. Imported locally, not at module scope -
    presentation.py imports this module (for TRADELOG_PATH/BANKROLL_PATH),
    so a top-level import here would be circular."""
    import presentation

    try:
        presentation.post_dashboard()
    except discord_post.DiscordPostError:
        pass


def _post_held_position_update(row: dict[str, str], result: dict[str, Any]) -> None:
    trade_id = row.get("trade_id", "")
    if not trade_id:
        return
    pnl_pct = result.get("pnl_pct") or 0.0
    emoji = "\U0001F7E2" if pnl_pct >= 0 else "\U0001F534"
    content = (
        f"{emoji} SPY_EVOLVE HELD · {row.get('option_symbol')}\n"
        f"Entry ${result['entry']:.2f} → Mark ${result['mark']:.2f} ({pnl_pct:+.0f}%)\n"
        f"Peak {result['peak_pct']:+.0f}% · Trough {result['trough_pct']:+.0f}% · {result.get('note', '')}"
    )
    _post_trade_card(trade_id, content)


def _close_open_positions(
    rows: list[dict[str, str]], bank: dict[str, Any], timestamp
) -> tuple[dict[str, Any], int]:
    open_rows = tradelog.open_rows(rows)
    if not open_rows:
        return bank, 0
    quote_map = s.get_quotes(
        [row["option_symbol"] for row in open_rows if row.get("option_symbol")],
        include_greeks=True,
    )
    closed_count = 0
    for row in open_rows:
        quote = quote_map.get(row.get("option_symbol", ""))
        result = evaluate_exit_for_row(row, quote, timestamp)
        if result is None:
            continue
        if not result["should_close"]:
            _post_held_position_update(row, result)
            continue
        contracts = int(row.get("contracts") or 0)
        proceeds = round(result["mark"] * 100 * contracts, 2)
        pl_dollars = round((result["mark"] - result["entry"]) * 100 * contracts, 2)
        row["outcome"] = "WIN" if pl_dollars > 0 else ("LOSS" if pl_dollars < 0 else "SCRATCH")
        row["exit_price"] = str(round(result["mark"], 2))
        row["closed_at"] = timestamp.isoformat()
        row["last_signal"] = result["signal"]
        row["pl_dollars"] = str(pl_dollars)
        row["pl_pct"] = str(round(result["pnl_pct"]))
        bank = bankroll.credit_exit(bank, proceeds)
        row["balance_after"] = str(bank["balance"])
        closed_count += 1
        emoji = "\U0001F7E2" if row["outcome"] == "WIN" else ("\U0001F534" if row["outcome"] == "LOSS" else "⚪")
        _post_trade_card(
            row.get("trade_id", ""),
            f"{emoji} SPY_EVOLVE closed {row['option_symbol']}: {row['outcome']} "
            f"{row['pl_pct']}% (${pl_dollars:,.2f}) — {result['signal']}\n"
            f"Balance: ${bank['balance']:,.2f}",
        )
    return bank, closed_count


def find_candidate(timestamp, spot_price: float, play_type: str = PLAY_TYPE) -> dict[str, Any]:
    """Pure market-detection step - real entry-window check, real signal,
    real chain, real candidate scoring - with no bankroll/capital logic
    and no dependency on whether a real position is already open. Split
    out from _try_open_new_position specifically so shadow.py (Phase 6)
    can reuse the IDENTICAL real detection logic instead of maintaining a
    second copy that could drift from this one (the same class of bug
    this project has hit before with CLOSING_SIGNALS and the diagnostic
    log-check duplication)."""
    if s.entry_window_blocked(timestamp):
        return {"qualified": False, "reason": "entry window blocked"}
    today_str = timestamp.date().isoformat()
    if today_str not in s.get_expirations(s.TICKER):
        return {"qualified": False, "reason": "no expiration listed for today", "today_str": today_str}

    history = s.get_daily_history(s.TICKER, days=120)
    market_condition = s.classify_market_condition(history)["label"]
    intraday_1m = s.get_intraday_history(s.TICKER, interval="1min")
    context = s.spy_0dte_opening_range_signal(intraday_1m, bar_minutes=1)
    if not context.get("qualified"):
        return {
            "qualified": False, "reason": "opening range signal not qualified",
            "context": context, "today_str": today_str,
        }

    allowed_strikes = set(s.filter_strikes(s.get_strikes(s.TICKER, today_str), spot_price))
    raw_chain = s.get_chain(s.TICKER, today_str)
    chain = [option for option in raw_chain if float(option.get("strike", -1)) in allowed_strikes]
    kind = "call" if context["regime"] == "BULLISH / CONTROLLED" else "put"
    pool = [option for option in chain if option.get("option_type") == kind]
    candidates = s.scan_spy_0dte_candidates(pool, kind, today_str, spot_price, context, play_type=play_type)
    if not candidates:
        return {
            "qualified": False, "reason": "no candidates passed filters",
            "context": context, "chain": chain, "today_str": today_str,
        }
    candidates.sort(key=lambda candidate: candidate.get("score", 0), reverse=True)
    best = candidates[0]
    return {
        "qualified": True,
        "candidate": best,
        "context": context,
        "market_condition": market_condition,
        "chain": chain,
        "today_str": today_str,
    }


def _try_open_new_position(
    rows: list[dict[str, str]], bank: dict[str, Any], timestamp, spot_price: float
) -> tuple[dict[str, str] | None, dict[str, Any]]:
    """Returns (new_row_or_None, possibly-updated bank) - explicit return
    rather than mutating the caller's bank dict in place, so the entry-
    debit accounting stays as easy to follow as _close_open_positions'
    exit-credit accounting above."""
    # One position at a time for phase 1 - the simplest correct starting
    # point; concurrent positions are a natural later increment once this
    # core loop is proven, not a phase-1 requirement.
    if tradelog.open_rows(rows):
        return None, bank
    found = find_candidate(timestamp, spot_price)
    if not found["qualified"]:
        return None, bank
    best = found["candidate"]
    context = found["context"]
    market_condition = found["market_condition"]
    chain = found["chain"]
    today_str = found["today_str"]

    put_call_ratio = market_features.put_call_ratio_from_chain(chain)
    vix_series = market_features.fetch_vix_series(
        (timestamp.date() - timedelta(days=10)).isoformat(), today_str
    )
    vix = market_features.vix_on_or_before(today_str, vix_series)
    sentiment = market_features.market_sentiment_for_date(today_str)
    explanation = model_scoring.explain_score(best, context, market_condition, vix, sentiment, put_call_ratio)
    model_score = explanation["score"] if explanation else None
    model_narrative = model_scoring.build_model_narrative(explanation)

    # Scoring always happens (see MODEL_FILTER_ENABLED's docstring above);
    # only this skip is gated. A candidate the rule-based signal already
    # qualified never gets blocked just because scoring failed open
    # (model_score is None) - only an actual low score does.
    if MODEL_FILTER_ENABLED and model_score is not None and model_score < MODEL_MIN_WIN_PROBABILITY:
        return None, bank

    size_dollars = bankroll.position_size_dollars(bank, self_tuning.current_position_size_pct())
    contracts = bankroll.contracts_affordable(size_dollars, best["entry_price"])
    if contracts < 1:
        return None, bank
    cost = round(best["entry_price"] * 100 * contracts, 2)

    row = tradelog.blank_row()
    row.update(
        {
            "trade_id": tradelog.next_trade_id(rows, bank["run_number"], timestamp),
            "run_number": str(bank["run_number"]),
            "timestamp": timestamp.isoformat(),
            "option_symbol": best["option_symbol"],
            "call_or_put": best["call_or_put"],
            "strike": str(best["strike"]),
            "expiration": best["expiration"],
            "entry_price": str(best["entry_price"]),
            "contracts": str(contracts),
            "position_size_dollars": str(size_dollars),
            "balance_before": str(bank["balance"]),
            "spot_price_at_entry": str(round(spot_price, 2)),
            "delta_at_entry": str(best["delta"]),
            "theta_at_entry": str(best["theta"]),
            "iv_at_entry": str(best["iv"]),
            "open_interest_at_entry": str(best["open_interest"]),
            "volume_at_entry": str(best["option_volume"]),
            "market_regime": context["regime"],
            "market_condition_at_entry": market_condition,
            "opening_range_high": str(context.get("range_high", "")),
            "opening_range_low": str(context.get("range_low", "")),
            "vix_at_entry": "" if vix is None else str(vix),
            "sentiment_at_entry": "" if sentiment is None else str(sentiment),
            "put_call_ratio_at_entry": "" if put_call_ratio is None else str(put_call_ratio),
            "model_score_at_entry": "" if model_score is None else str(model_score),
            "model_narrative_at_entry": model_narrative,
            "thesis": build_thesis(best, context, market_condition),
            "outcome": "OPEN",
            "max_favorable_pct": "0",
            "max_adverse_pct": "0",
            "last_evaluated_at": timestamp.isoformat(),
        }
    )
    bank = bankroll.debit_entry(bank, cost)
    rows.append(row)
    _post_trade_card(
        row["trade_id"],
        f"\U0001F7E2 SPY_EVOLVE opened {row['call_or_put'].upper()} {row['strike']} exp {row['expiration']} "
        f"@ ${row['entry_price']} x{contracts} (${cost:,.2f} risked)\n{row['thesis']}",
    )
    return row, bank


def run_cycle() -> dict[str, Any]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    bank = bankroll.load_state(BANKROLL_PATH)
    rows = tradelog.read_log(TRADELOG_PATH)

    is_open, timestamp = s.market_is_open_now()
    if not is_open:
        return {"status": "market closed"}

    spot = s.get_quote(s.TICKER)
    if not spot or s.as_float(spot.get("last")) is None:
        return {"status": "spot quote unavailable"}
    spot_price = float(spot["last"])

    bank, closed_count = _close_open_positions(rows, bank, timestamp)

    # Evaluated right after closing (in memory, off the same `rows` list -
    # no extra disk read needed), so a trade that just closed this very
    # cycle is immediately eligible to inform the next sizing decision.
    # Cheap and idempotent either way (see evaluate_tuning's docstring) -
    # safe to call every cycle regardless of whether anything closed now.
    tuning_result = self_tuning.evaluate_tuning(tradelog.closed_rows(rows))

    opened_row, bank = _try_open_new_position(rows, bank, timestamp, spot_price)

    tradelog.write_log(TRADELOG_PATH, rows)
    bankroll.save_state(BANKROLL_PATH, bank)
    if closed_count or opened_row:
        _refresh_dashboard()
    return {
        "status": "ok",
        "closed": closed_count,
        "opened": bool(opened_row),
        "balance": bank["balance"],
        "run_number": bank["run_number"],
        "tuning": tuning_result["status"],
    }


if __name__ == "__main__":
    print(run_cycle())
