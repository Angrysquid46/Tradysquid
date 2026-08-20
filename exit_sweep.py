"""Hold the entries fixed. Sweep hundreds of exits. See what clears.

The 15 strategies lose under their current exits - a +115% target hits
about 10% of the time against a 39.5% break-even. That says those exits
are wrong. It does not say the entries are.

Testing that properly means running many exits against the same entries,
and the obvious way is too slow: 15 entries x 30 exits x 1,000 sessions is
450,000 simulations, hours of work, most of it recomputing the same option
prices.

So this records the PATH once and evaluates every exit against it. For each
signal, walk forward to the bell once, storing (minute, premium P/L, spot).
Pricing is the expensive part and it happens exactly once per signal. An
exit rule is then a cheap scan over a list, so the hundredth exit costs
almost nothing.

**One position at a time is preserved.** That rule couples exits to
entries: a 5-minute exit frees the strategy to take a signal a 30-minute
exit is still holding through. Each rule therefore walks the signals in
order and skips any that opens before the previous trade closed, exactly as
the live scanner does. Ignoring that would credit every rule with every
signal and quietly invent trades.

`test_exit_sweep.py` asserts a swept rule produces the same trades as
`backtest_lab.simulate` running it directly. Without that this is a faster
way to be wrong.
"""

from __future__ import annotations

import statistics
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import backtest_lab as lab
import spy_option_backtest as ob
import spy_option_model as om


@dataclass
class Path:
    """One signal's trade, priced minute by minute to the bell."""
    signal_index: int
    entry_index: int
    direction: str
    kind: str
    strike: float
    entry_minute: int
    entry_price: float
    entry_spot: float
    session_date: str
    minutes: list[int] = field(default_factory=list)
    pnl_pct: list[float] = field(default_factory=list)
    marks: list[float] = field(default_factory=list)
    spots: list[float] = field(default_factory=list)
    indices: list[int] = field(default_factory=list)
    rows: list[dict] = field(default_factory=list)


def build_paths(rows: Sequence[dict[str, Any]], signals: Sequence[tuple[int, str]],
                vol: float, *, target_delta: float = ob.DEFAULT_TARGET_DELTA
                ) -> list[Path]:
    """Price every signal to the bell, once.

    Deliberately prices ALL signals, including ones a given exit rule would
    never reach because it is still holding. Which signals are actually
    taken depends on the rule, and that is decided later.
    """
    out: list[Path] = []
    total = len(rows)
    for signal_index, direction in signals:
        entry_index = signal_index + 1
        if entry_index >= total:
            continue
        entry_row = rows[entry_index]
        spot = entry_row.get("open")
        entry_minute = entry_row.get("minutes_since_open")
        if spot is None or entry_minute is None or entry_minute >= ob.LAST_EXIT_MINUTE:
            continue
        kind = "call" if direction == "LONG" else "put"
        strike = om.select_strike(spot, entry_minute, vol, kind, target_delta)
        entry_price = om.quote(spot, strike, entry_minute, vol, kind).ask
        if entry_price <= 0.05 or entry_price > ob.MAX_CONTRACT_ASK:
            continue
        if entry_price * 100 > ob.MAX_RISK_PER_TRADE:
            continue

        path = Path(signal_index=signal_index, entry_index=entry_index,
                    direction=direction, kind=kind, strike=strike,
                    entry_minute=entry_minute, entry_price=entry_price,
                    entry_spot=entry_row.get("close"),
                    session_date=entry_row["session_date"])
        for offset in range(entry_index, total):
            bar = rows[offset]
            minute, close = bar.get("minutes_since_open"), bar.get("close")
            if minute is None or close is None:
                continue
            mark = om.quote(close, strike, minute, vol, kind).bid
            path.minutes.append(minute)
            path.marks.append(mark)
            path.spots.append(close)
            path.indices.append(offset)
            path.rows.append(bar)
            path.pnl_pct.append((mark - entry_price) / entry_price * 100.0)
            if minute >= ob.LAST_EXIT_MINUTE:
                break
        if path.minutes:
            out.append(path)
    return out


def apply_rule(paths: Sequence[Path], rule: lab.ExitFn, *, label: str
               ) -> list[ob.OptionTrade]:
    """Walk the session's signals under one exit rule, one position at a time."""
    trades: list[ob.OptionTrade] = []
    blocked_until = -1
    for path in paths:
        if path.signal_index <= blocked_until:
            continue          # still holding when this signal fired
        peak = 0.0
        exit_at = len(path.minutes) - 1
        reason = "eod_close"
        for step, minute in enumerate(path.minutes):
            pnl = path.pnl_pct[step]
            peak = max(peak, pnl)
            found = rule(lab.TradeState(
                minutes_held=minute - path.entry_minute,
                minute_of_session=minute, pnl_pct=pnl, peak_pct=peak,
                mark=path.marks[step], entry_price=path.entry_price,
                spot=path.spots[step], entry_spot=path.entry_spot,
                direction=path.direction, kind=path.kind, strike=path.strike,
                row=path.rows[step]))
            if not found and minute >= ob.LAST_EXIT_MINUTE:
                found = "eod_close"
            if found:
                exit_at, reason = step, found
                break
        exit_price = path.marks[exit_at]
        net = ((exit_price - path.entry_price) * 100.0
               - ob.COMMISSION_PER_CONTRACT * 2)
        trades.append(ob.OptionTrade(
            strategy=label, session_date=path.session_date,
            direction=path.direction, kind=path.kind, strike=path.strike,
            entry_minute=path.entry_minute, exit_minute=path.minutes[exit_at],
            entry_price=path.entry_price, exit_price=exit_price,
            pnl_pct=(exit_price - path.entry_price) / path.entry_price * 100.0,
            pnl_dollars=net, peak_pct=peak, exit_reason=reason,
            contracts=1, vol=0.0))
        blocked_until = path.indices[exit_at]
    return trades


def sweep(entries: dict[str, lab.EntryFn], exits: dict[str, lab.ExitFn], *,
          deltas: Sequence[float] = (ob.DEFAULT_TARGET_DELTA,),
          since: str | None = None, until: str | None = None,
          limit: int | None = None, progress_every: int = 250
          ) -> tuple[dict[tuple[str, str], lab.Result], lab.Coverage]:
    """Every entry against every exit, at every target delta, in one walk.

    `deltas` sweeps CONTRACT SELECTION, which until now was the one thing
    all 15 strategies shared: scan_new_strategy_candidates takes no
    strategy argument at all - one delta band, one ask ceiling, one risk
    cap, and every caller takes candidates[0]. A 5-minute exhaustion fade
    and a 30-minute momentum continuation are handed the identical
    0.50-delta contract.

    Paths must be rebuilt per delta, because the strike changes and so does
    every price along it. So this costs len(deltas) times a single-delta
    sweep, unlike adding exits, which is free.
    """
    import option_session_inputs as osi
    import spy_backtest as bt
    import spy_option_data as od

    conn = bt.connect()
    option_conn = od.open_readonly()
    started = time.perf_counter()
    trades: dict[tuple[str, str], list[ob.OptionTrade]] = {
        (e, f"d{d:.2f}|{x}"): [] for e in entries for d in deltas for x in exits}
    scored = measured = proxied = 0
    first = last = None

    try:
        chain_sessions = om.sessions_with_zero_dte(option_conn)
        vol_cache: dict[str, Any] = {}
        for session, rows in bt.load_sessions(conn, limit=limit, since=since,
                                              until=until):
            if not osi.zero_dte_listed(session, chain_sessions=chain_sessions):
                continue
            if session not in vol_cache:
                vol_cache[session] = osi.session_inputs(session, option_conn)
            inputs = vol_cache[session]
            if inputs is None:
                continue
            scored += 1
            measured += inputs.is_measured
            proxied += not inputs.is_measured
            first = first or session
            last = session
            for entry_name, entry_fn in entries.items():
                signals = entry_fn(rows)
                if not signals:
                    continue
                for delta in deltas:
                    paths = build_paths(rows, signals, inputs.vol,
                                        target_delta=delta)
                    if not paths:
                        continue
                    for exit_name, rule in exits.items():
                        key = (entry_name, f"d{delta:.2f}|{exit_name}")
                        trades[key].extend(
                            apply_rule(paths, rule, label=f"{entry_name}|{key[1]}"))
            if progress_every and scored % progress_every == 0:
                print(f"  {scored} sessions ({time.perf_counter() - started:.0f}s)",
                      flush=True)
    finally:
        conn.close()
        option_conn.close()

    results = {key: lab.summarize(f"{key[0]}|{key[1]}", value)
               for key, value in trades.items()}
    return results, lab.Coverage(scored, first, last,
                                 round(time.perf_counter() - started, 1),
                                 measured_sessions=measured,
                                 proxy_sessions=proxied)
