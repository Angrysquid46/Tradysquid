"""Per-trade forensics: entry reasoning, liquidity, exit mechanics, and
excursion history in one place, for any trade instead of a bespoke query
every time. Read-only - never touches the log, never places or closes
anything.

Usage:
    python trade_autopsy.py                    # every trade opened today
    python trade_autopsy.py --open              # every currently open trade
    python trade_autopsy.py --closed            # every closed trade
    python trade_autopsy.py --ticker CCL         # every CCL trade
    python trade_autopsy.py --trade-id CCL-20260807-001
    python trade_autopsy.py --summary            # aggregate stats only
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

import ford_scan


def _parse_ts(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _entry_spread_pct(row: dict) -> float:
    entry = ford_scan.as_float(row.get("entry_price")) or 0.0
    spread = ford_scan.as_float(row.get("bid_ask_width_at_entry")) or 0.0
    return (spread / entry * 100) if entry else 0.0


def _widened_stop_floor(row: dict) -> float:
    """REGULAR/SWING/SPREAD all share single_leg_exit_signal's fixed stop,
    widened by the entry spread. SPY_0DTE uses a completely different
    model (spy_0dte_exit_signal): a -50% stop that raises ONCE to -15%
    after the trade peaks past 30% profit, with no spread-based
    widening at all. Applying the single-leg math to a SPY_0DTE row
    produced false "EXECUTION ANOMALY" flags on ordinary, correct 0DTE
    losses that happened before the floor engaged."""
    if row.get("play_type") == "SPY_0DTE":
        peak = ford_scan.as_float(row.get("max_favorable_pct")) or 0.0
        if peak >= ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT:
            return ford_scan.SPY_0DTE_FLOOR_PCT
        return -ford_scan.SPY_0DTE_STOP_PCT * 100
    base = -SINGLE_STOP_PCT_HINT * 100
    return base - abs(_entry_spread_pct(row))


SINGLE_STOP_PCT_HINT = ford_scan.SINGLE_STOP_PCT


def _fmt(value, digits: int = 1, suffix: str = "") -> str:
    if value is None or value == "":
        return "n/a"
    try:
        return f"{float(value):.{digits}f}{suffix}"
    except (TypeError, ValueError):
        return str(value)


def autopsy(row: dict) -> str:
    lines: list[str] = []
    trade_id = row.get("trade_id") or "?"
    outcome = row.get("outcome") or "OPEN"
    lines.append(f"{'=' * 78}")
    lines.append(
        f"{trade_id}  {row.get('ticker')}  {row.get('play_type')} {row.get('call_or_put')}"
        f"  strike {row.get('strike')}  exp {row.get('expiration')}  [{outcome}]"
    )

    opened = _parse_ts(row.get("timestamp") or "")
    closed = _parse_ts(row.get("closed_at") or "")
    held = ""
    if opened and closed:
        held = f" (held {closed - opened})"
    elif opened:
        held = f" (open {datetime.now(opened.tzinfo) - opened})" if opened.tzinfo else ""
    lines.append(f"  Opened: {row.get('timestamp')}   Closed: {row.get('closed_at') or '-'}{held}")

    lines.append("  --- Entry ---")
    lines.append(
        f"  entry_price={_fmt(row.get('entry_price'), 2, '')}"
        f"  setup_score={_fmt(row.get('setup_score'))}"
        f"  regime={row.get('market_regime')}"
    )
    lines.append(f"  setup_reason: {row.get('setup_reason') or 'n/a'}")
    if row.get("thesis") and row.get("thesis") != row.get("setup_reason"):
        lines.append(f"  thesis: {row.get('thesis')}")

    lines.append("  --- Liquidity at entry ---")
    spread_pct = _entry_spread_pct(row)
    lines.append(
        f"  bid_ask_width={_fmt(row.get('bid_ask_width_at_entry'), 2, '')}"
        f" ({_fmt(spread_pct, 1, '%')} of entry price)"
        f"  open_interest={row.get('open_interest_at_entry')}"
        f"  option_volume={row.get('option_volume_at_entry')}"
    )
    try:
        oi = int(float(row.get("open_interest_at_entry") or 0))
        vol = int(float(row.get("option_volume_at_entry") or 0))
        if oi < ford_scan.MIN_OPEN_INTEREST or vol < ford_scan.MIN_OPTION_VOLUME:
            lines.append(
                f"  !! FLAG: entered below the CURRENT liquidity floor "
                f"(OI>={ford_scan.MIN_OPEN_INTEREST}, vol>={ford_scan.MIN_OPTION_VOLUME}) "
                f"- this trade predates the current filter."
            )
    except (TypeError, ValueError):
        pass
    lines.append(
        f"  delta={_fmt(row.get('delta_at_entry'), 3)}"
        f"  theta={_fmt(row.get('theta_at_entry'), 4)}"
        f"  iv={_fmt(row.get('iv_at_entry'), 2)}"
    )

    lines.append("  --- Risk floor ---")
    widened = _widened_stop_floor(row)
    if row.get("play_type") == "SPY_0DTE":
        peak = ford_scan.as_float(row.get("max_favorable_pct")) or 0.0
        raised = peak >= ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT
        lines.append(
            f"  0DTE stop={-ford_scan.SPY_0DTE_STOP_PCT * 100:.0f}%"
            f"  floor trigger={ford_scan.SPY_0DTE_FLOOR_TRIGGER_PCT:.0f}% peak"
            f"  peak reached={peak:.0f}%"
            f"  {'floor RAISED to' if raised else 'floor not yet raised, still at'} {widened:.0f}%"
        )
    else:
        lines.append(
            f"  base stop={-SINGLE_STOP_PCT_HINT * 100:.0f}%"
            f"  spread allowance={-abs(spread_pct):.1f}pt"
            f"  widened stop floor={widened:.1f}%"
        )

    lines.append("  --- Excursion ---")
    max_fav = ford_scan.as_float(row.get("max_favorable_pct"))
    max_adv = ford_scan.as_float(row.get("max_adverse_pct"))
    lines.append(
        f"  max_favorable={_fmt(max_fav, 1, '%')}"
        f"  max_adverse={_fmt(max_adv, 1, '%')}"
        f"  current/final pnl={_fmt(row.get('current_pl_pct') if outcome == 'OPEN' else row.get('pct_gain_loss'), 1, '%')}"
    )
    if max_fav is not None and max_fav <= 0.01:
        lines.append(
            "  !! FLAG: NEVER WENT GREEN - not even briefly. Either entered at the "
            "tail of an already-completed move, or the mark was bad from minute one."
        )

    if outcome != "OPEN":
        lines.append("  --- Exit ---")
        lines.append(
            f"  exit_price={_fmt(row.get('exit_price'), 2, '')}"
            f"  pct_gain_loss={_fmt(row.get('pct_gain_loss'), 1, '%')}"
            f"  realized=${_fmt(row.get('realized_pl_dollars'), 2, '')}"
            f"  last_signal={row.get('last_signal')}"
        )
        pnl = ford_scan.as_float(row.get("pct_gain_loss"))
        if pnl is not None and outcome == "LOSS" and pnl < widened - 5:
            lines.append(
                f"  !! FLAG: EXECUTION ANOMALY - realized loss ({pnl:.0f}%) blew past the "
                f"computed stop floor ({widened:.1f}%) by {widened - pnl:.0f} points. "
                "The mark used to trigger this exit may not have been a real, "
                "tradeable price - check option_volume_at_entry and the underlying's "
                "actual move during the hold window before trusting this number."
            )

    return "\n".join(lines)


def summarize(rows: list[dict]) -> str:
    total = len(rows)
    if not total:
        return "No trades match this filter."
    closed = [r for r in rows if (r.get("outcome") or "OPEN") != "OPEN"]
    wins = [r for r in closed if r.get("outcome") == "WIN"]
    losses = [r for r in closed if r.get("outcome") == "LOSS"]
    never_green = [
        r for r in rows
        if (ford_scan.as_float(r.get("max_favorable_pct")) or 0) <= 0.01
    ]
    anomalies = []
    for row in closed:
        widened = _widened_stop_floor(row)
        pnl = ford_scan.as_float(row.get("pct_gain_loss"))
        if row.get("outcome") == "LOSS" and pnl is not None and pnl < widened - 5:
            anomalies.append(row)
    lines = [
        f"Trades: {total}   Closed: {len(closed)} ({len(wins)}W / {len(losses)}L)",
        f"Never went green (not even briefly): {len(never_green)}/{total}"
        f" ({len(never_green) / total * 100:.0f}%)",
        f"Execution anomalies (loss blew past its own stop floor): {len(anomalies)}",
    ]
    if anomalies:
        lines.append("  " + ", ".join(r.get("trade_id", "?") for r in anomalies))
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trade-id")
    parser.add_argument("--ticker")
    parser.add_argument("--open", action="store_true")
    parser.add_argument("--closed", action="store_true")
    parser.add_argument("--today", action="store_true")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    rows = ford_scan.read_log()

    if args.trade_id:
        rows = [r for r in rows if r.get("trade_id") == args.trade_id]
    elif args.ticker:
        rows = [r for r in rows if (r.get("ticker") or "").upper() == args.ticker.upper()]
    elif args.open:
        rows = ford_scan.open_rows(rows)
    elif args.closed:
        rows = ford_scan.closed_rows(rows)
    elif args.all:
        pass
    else:
        today = datetime.now().date().isoformat()
        rows = [r for r in rows if str(r.get("timestamp") or "").startswith(today)]

    rows.sort(key=lambda r: r.get("timestamp") or "")

    if args.summary:
        print(summarize(rows))
        return 0

    if not rows:
        print("No trades match this filter.")
        return 0

    for row in rows:
        print(autopsy(row))
    print("=" * 78)
    print(summarize(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
