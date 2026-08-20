"""Throw any idea at the archive and get numbers back.

The engine knows nothing about strategies. It takes two functions:

    entry(rows)  -> [(bar_index, "LONG"|"SHORT"), ...]
    exit(state)  -> a reason string to close, or None to keep holding

That is the whole interface. Anything expressible as those two functions
can be measured without editing this file, adding a registry entry, or
naming a strategy anywhere.

## Why the exit is a function

It used to be a dataclass of fixed fields - target, stop, floor, ratchet,
stagnation, time, underlying - and a new exit IDEA meant editing both the
dataclass and `_exit_signal`. A trailing stop, "get out if VWAP flips",
"hold unless it is up 20% by minute 10": none of those are expressible as
fields. As a function they are three lines each.

`premium_exit()` wraps the old `OptionExit` as one such function, so every
number measured under the old engine reproduces exactly. That is asserted
in `test_backtest_lab.py` against `simulate_option_trades` itself, not
assumed.

## Why nothing here names a strategy

Every driver that came before held strategy names - SHORTLIST, ENTRY_KEYS,
build_roster - so deleting a strategy broke the harness. It happened twice
(#274, #281) and the option layer was dead for weeks. This file has no
list of strategies to fall out of date.

## What is honest and what is modelled

Real: SPY 1-minute bars and their features, and which sessions had a
same-day expiry listed.

Modelled: every option price, from that day's IV level. The archive has no
intraday option quotes and never has. Results are evidence, not fills, and
`Result.modelled` says so rather than leaving it in a docstring.

Live risk gates are mirrored from spy_scanner: one contract, ask between
$0.05 and $5.00, position inside the $500 cap, $0.04 per contract each
way, flat by 15:45.

## Read the coverage before believing a number

`Result.coverage` carries the sessions scored and the first and last dates.
It is not decoration - as of 2026-08-20 the archive can only score
2010-01-15 to 2021-05-05, which is entirely BEFORE SPY had daily 0DTE
expiries. A table that does not say what window it came from will be read
as if it describes today.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import spy_option_backtest as ob
import spy_option_model as om

EntryFn = Callable[[Sequence[dict[str, Any]]], list[tuple[int, str]]]

# SPY listed same-day expiries on Tuesday/Thursday from 2022-04-25 and on
# every weekday from 2022-05-04. Anything measured before that is a
# different instrument, whatever the backtest calls it.
DAILY_0DTE_FROM = "2022-05-04"


@dataclass
class TradeState:
    """Everything an exit rule could reasonably want, once per minute."""
    minutes_held: int
    minute_of_session: int
    pnl_pct: float           # option premium, percent of entry
    peak_pct: float          # best pnl_pct seen so far this trade
    mark: float              # current option bid
    entry_price: float       # option ask paid
    spot: float              # SPY now
    entry_spot: float        # SPY at entry
    direction: str           # LONG or SHORT
    kind: str                # call or put
    strike: float
    row: dict[str, Any]      # the whole feature row: vwap, atr, adx, ...

    @property
    def drawdown_pct(self) -> float:
        """How far off the peak this trade currently sits."""
        return self.pnl_pct - self.peak_pct

    @property
    def spot_move_pct(self) -> float:
        """Underlying move since entry, signed FOR the position."""
        if not self.entry_spot:
            return 0.0
        move = (self.spot - self.entry_spot) / self.entry_spot * 100.0
        return move if self.direction == "LONG" else -move


ExitFn = Callable[[TradeState], str | None]


@dataclass
class Idea:
    label: str
    entry: EntryFn
    exit: ExitFn


@dataclass
class Result:
    label: str
    trades: int = 0
    win_rate: float = 0.0
    avg_dollars: float = 0.0
    total_dollars: float = 0.0
    avg_pct: float = 0.0
    median_pct: float = 0.0
    profit_factor: float = 0.0
    avg_minutes_held: float = 0.0
    exit_reasons: dict[str, int] = field(default_factory=dict)
    modelled: bool = True

    def line(self) -> str:
        return (f"{self.label:<34}{self.trades:>8,}{self.win_rate:>7.1f}%"
                f"{self.avg_dollars:>+9.2f}{self.total_dollars:>+12,.0f}"
                f"{self.avg_minutes_held:>8.0f}m")


@dataclass
class Coverage:
    sessions_scored: int
    first_session: str | None
    last_session: str | None
    elapsed_seconds: float
    # How the volatility input was obtained, per session. A measured chain
    # IV and a VIX proxy are different strengths of evidence and the split
    # travels with the result rather than being assumed.
    measured_sessions: int = 0
    proxy_sessions: int = 0

    @property
    def covers_daily_0dte_era(self) -> bool:
        return bool(self.last_session and self.last_session >= DAILY_0DTE_FROM)

    def warning(self) -> str:
        notes = []
        if not self.covers_daily_0dte_era:
            notes.append(
                f"NOTE: scored {self.first_session} to {self.last_session}. "
                f"SPY had no daily 0DTE expiry until {DAILY_0DTE_FROM}, so "
                f"none of this is from the regime these ideas trade in.")
        if self.proxy_sessions:
            share = self.proxy_sessions / max(
                self.measured_sessions + self.proxy_sessions, 1) * 100
            notes.append(
                f"NOTE: {self.proxy_sessions:,} of "
                f"{self.measured_sessions + self.proxy_sessions:,} sessions "
                f"({share:.0f}%) priced off a VIX proxy, not a measured "
                f"same-day IV. 0DTE vol is routinely far from 30-day vol.")
        return "\n".join(notes)


# ---------------------------------------------------------------------------
# Exit rules you can hand to an Idea. None of these invent a threshold -
# every number is an argument the caller supplies.
# ---------------------------------------------------------------------------

def hold_for(minutes: int) -> ExitFn:
    """Pure clock: close after `minutes`, whatever the trade is doing."""
    def rule(state: TradeState) -> str | None:
        return "time_stop" if state.minutes_held >= minutes else None
    return rule


def premium_exit(rules: ob.OptionExit) -> ExitFn:
    """The original OptionExit shape, as a function.

    Exists so everything measured under the old engine reproduces here
    exactly - asserted against simulate_option_trades in the tests.
    """
    def rule(state: TradeState) -> str | None:
        reason, should = ob._exit_signal(
            state.pnl_pct, state.peak_pct, state.minute_of_session, rules)
        if should:
            return reason
        if ob._stagnation_bail(state.pnl_pct,
                               state.minute_of_session - state.minutes_held,
                               state.minute_of_session, rules):
            return "stagnation_bail"
        if rules.time_stop_minutes and state.minutes_held >= rules.time_stop_minutes:
            return "time_stop"
        if rules.underlying_stop_pct:
            reason, should = ob._underlying_exit(
                state.entry_spot, state.spot, state.direction, rules)
            if should:
                return reason
        return None
    return rule


def target_and_stop(target_pct: float | None, stop_pct: float | None) -> ExitFn:
    """Close at +target_pct or -stop_pct of premium. Either may be None."""
    def rule(state: TradeState) -> str | None:
        if stop_pct is not None and state.pnl_pct <= stop_pct:
            return "stop"
        if target_pct is not None and state.pnl_pct >= target_pct:
            return "target"
        return None
    return rule


def trailing_stop(give_back_pct: float, arm_at_pct: float = 0.0) -> ExitFn:
    """Once up `arm_at_pct`, close after giving back `give_back_pct`."""
    def rule(state: TradeState) -> str | None:
        if state.peak_pct < arm_at_pct:
            return None
        if state.peak_pct - state.pnl_pct >= give_back_pct:
            return "trailing_stop"
        return None
    return rule


def first_of(*rules: ExitFn) -> ExitFn:
    """Whichever rule fires first wins. Order is the priority."""
    def rule(state: TradeState) -> str | None:
        for candidate in rules:
            reason = candidate(state)
            if reason:
                return reason
        return None
    return rule


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------

def simulate(rows: Sequence[dict[str, Any]], signals: Sequence[tuple[int, str]],
             vol: float, exit_rule: ExitFn, *, label: str,
             target_delta: float = ob.DEFAULT_TARGET_DELTA) -> list[ob.OptionTrade]:
    """One session, one idea. Same structural rules as the live system:
    fill at the NEXT bar's open, one position at a time, flat by 15:45."""
    by_index = dict(signals)
    trades: list[ob.OptionTrade] = []
    index, total = 0, len(rows)

    while index < total:
        direction = by_index.get(index)
        if direction is None:
            index += 1
            continue

        entry_index = index + 1
        if entry_index >= total:
            break
        entry_row = rows[entry_index]
        spot = entry_row.get("open")
        entry_minute = entry_row.get("minutes_since_open")
        if spot is None or entry_minute is None or entry_minute >= ob.LAST_EXIT_MINUTE:
            index += 1
            continue

        kind = "call" if direction == "LONG" else "put"
        strike = om.select_strike(spot, entry_minute, vol, kind, target_delta)
        entry_price = om.quote(spot, strike, entry_minute, vol, kind).ask
        if entry_price <= 0.05 or entry_price > ob.MAX_CONTRACT_ASK:
            index += 1
            continue
        contracts = 1 if entry_price * 100 <= ob.MAX_RISK_PER_TRADE else 0
        if contracts < 1:
            index += 1
            continue

        entry_spot = entry_row.get("close")
        peak_pct = 0.0
        exit_index, exit_price, reason = entry_index, entry_price, "eod_close"

        for offset in range(entry_index, total):
            bar = rows[offset]
            minute, close = bar.get("minutes_since_open"), bar.get("close")
            if minute is None or close is None:
                continue
            mark = om.quote(close, strike, minute, vol, kind).bid
            pnl_pct = (mark - entry_price) / entry_price * 100.0
            peak_pct = max(peak_pct, pnl_pct)

            found = exit_rule(TradeState(
                minutes_held=minute - entry_minute, minute_of_session=minute,
                pnl_pct=pnl_pct, peak_pct=peak_pct, mark=mark,
                entry_price=entry_price, spot=close, entry_spot=entry_spot,
                direction=direction, kind=kind, strike=strike, row=bar,
            ))
            # The bell is not negotiable and is not the idea's business -
            # but it is applied AFTER the rule, so an idea that wants out
            # on the closing bar still records its own reason. That
            # ordering is what makes premium_exit reproduce the original
            # engine exactly rather than relabelling its last trade.
            if not found and minute >= ob.LAST_EXIT_MINUTE:
                found = "eod_close"
            if found:
                exit_index, exit_price, reason = offset, mark, found
                break
        else:
            last = rows[-1]
            exit_index = total - 1
            exit_price = om.quote(last["close"], strike,
                                  last.get("minutes_since_open") or ob.LAST_EXIT_MINUTE,
                                  vol, kind).bid

        net = ((exit_price - entry_price) * 100.0 * contracts
               - ob.COMMISSION_PER_CONTRACT * contracts * 2)
        trades.append(ob.OptionTrade(
            strategy=label, session_date=entry_row["session_date"],
            direction=direction, kind=kind, strike=strike,
            entry_minute=entry_minute,
            exit_minute=rows[exit_index].get("minutes_since_open") or 0,
            entry_price=entry_price, exit_price=exit_price,
            pnl_pct=(exit_price - entry_price) / entry_price * 100.0,
            pnl_dollars=net, peak_pct=peak_pct, exit_reason=reason,
            contracts=contracts, vol=vol,
        ))
        index = exit_index + 1

    return trades


def summarize(label: str, trades: Sequence[ob.OptionTrade]) -> Result:
    if not trades:
        return Result(label=label)
    dollars = [t.pnl_dollars for t in trades]
    pcts = [t.pnl_pct for t in trades]
    wins = [d for d in dollars if d > 0]
    losses = [-d for d in dollars if d < 0]
    reasons: dict[str, int] = {}
    for t in trades:
        reasons[t.exit_reason] = reasons.get(t.exit_reason, 0) + 1
    return Result(
        label=label,
        trades=len(trades),
        win_rate=len(wins) / len(trades) * 100.0,
        avg_dollars=statistics.fmean(dollars),
        total_dollars=sum(dollars),
        avg_pct=statistics.fmean(pcts),
        median_pct=statistics.median(pcts),
        profit_factor=(sum(wins) / sum(losses)) if losses else float("inf"),
        avg_minutes_held=statistics.fmean(
            [t.exit_minute - t.entry_minute for t in trades]),
        exit_reasons=dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
    )


def measure(ideas: Iterable[Idea], *, since: str | None = None,
            until: str | None = None, limit: int | None = None,
            newest: bool = False, progress_every: int = 200,
            target_delta: float = ob.DEFAULT_TARGET_DELTA,
            ) -> tuple[list[Result], Coverage]:
    """Score every idea in ONE walk of the archive.

    Ten ideas cost what one costs, which is the point: the expensive part
    is reading 1.4M bars and pricing options, not the rules.
    """
    import option_session_inputs as osi
    import spy_backtest as bt
    import spy_option_data as od

    ideas = list(ideas)
    conn = bt.connect()
    option_conn = od.open_readonly()
    started = time.perf_counter()
    trades: dict[str, list[ob.OptionTrade]] = {idea.label: [] for idea in ideas}
    scored, first, last = 0, None, None
    measured = proxied = 0

    try:
        # The real listing record, used only for sessions old enough to
        # need it - after 2022-05-04 a weekday 0DTE is a calendar fact.
        chain_sessions = om.sessions_with_zero_dte(option_conn)
        vol_cache: dict[str, osi.SessionInputs | None] = {}
        for session, rows in bt.load_sessions(conn, limit=limit, newest=newest,
                                              since=since, until=until):
            if not osi.zero_dte_listed(session, chain_sessions=chain_sessions):
                continue
            if session not in vol_cache:
                vol_cache[session] = osi.session_inputs(session, option_conn)
            inputs = vol_cache[session]
            if inputs is None:
                continue
            vol = inputs.vol
            measured += inputs.is_measured
            proxied += not inputs.is_measured
            scored += 1
            first = first or session
            last = session
            # Ideas often share an entry - compute each distinct one once.
            signal_cache: dict[int, list[tuple[int, str]]] = {}
            for idea in ideas:
                key = id(idea.entry)
                if key not in signal_cache:
                    signal_cache[key] = idea.entry(rows)
                signals = signal_cache[key]
                if signals:
                    trades[idea.label].extend(
                        simulate(rows, signals, vol, idea.exit,
                                 label=idea.label, target_delta=target_delta))
            if progress_every and scored % progress_every == 0:
                print(f"  {scored} sessions ({time.perf_counter() - started:.0f}s)",
                      flush=True)
    finally:
        conn.close()
        option_conn.close()

    results = [summarize(idea.label, trades[idea.label]) for idea in ideas]
    return results, Coverage(scored, first, last,
                             round(time.perf_counter() - started, 1),
                             measured_sessions=measured, proxy_sessions=proxied)


def report(results: Sequence[Result], coverage: Coverage) -> str:
    """A table narrow enough to read on a phone."""
    lines = [
        f"sessions {coverage.sessions_scored:,}  "
        f"{coverage.first_session} to {coverage.last_session}  "
        f"({coverage.elapsed_seconds / 60:.0f} min)",
        "",
        f"{'idea':<34}{'n':>8}{'win%':>8}{'$/trade':>9}{'total':>12}{'held':>9}",
        "-" * 80,
    ]
    lines += [r.line() for r in sorted(results, key=lambda r: -r.avg_dollars)]
    warning = coverage.warning()
    if warning:
        lines += ["", warning]
    lines += ["", "Option prices are MODELLED from that day's IV. Evidence, not fills."]
    return "\n".join(lines)
