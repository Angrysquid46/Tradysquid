"""Sanity check: every ticker in MEAN_REVERSION_VALIDATED_TICKERS must
have a REAL, currently tradeable option - liquid (option_has_liquidity)
AND within MAX_CONTRACT_ASK/MAX_RISK_PER_TRADE - at the swing delta band.

A ticker that passes the historical direction backtest but can never
clear the entry filter (too expensive, too illiquid) is dead weight at
best and misleading at worst. Run this before adding anything to
MEAN_REVERSION_VALIDATED_TICKERS, not after.

    python verify_validated_tickers.py
"""

from __future__ import annotations

import run_with_env

run_with_env.load_env()

import spy_scanner


def check_ticker(ticker: str) -> tuple[bool, str]:
    try:
        expirations = spy_scanner.get_expirations(ticker)
    except Exception as exc:
        return False, f"could not fetch expirations: {exc}"
    near, swing = spy_scanner.pick_expirations(expirations, spy_scanner.now_ct().date())
    # Mirrors scan_candidates: validated mean-reversion tickers trade the
    # near-dated bucket, not the 21-45 day swing bucket.
    if ticker in spy_scanner.MEAN_REVERSION_VALIDATED_TICKERS:
        exp = near[0] if near else None
    else:
        exp = swing[0] if swing else (near[0] if near else None)
    if not exp:
        return False, "no swing or near expiration available"
    quote = spy_scanner.get_quote(ticker) or {}
    spot = spy_scanner.as_float(quote.get("last"))
    if spot is None:
        return False, "could not fetch a live quote"
    try:
        allowed = set(spy_scanner.filter_strikes(spy_scanner.get_strikes(ticker, exp), spot))
        chain = [o for o in spy_scanner.get_chain(ticker, exp) if float(o.get("strike", -1)) in allowed]
    except Exception as exc:
        return False, f"could not fetch chain: {exc}"
    calls = [o for o in chain if o.get("option_type") == "call"]
    puts = [o for o in chain if o.get("option_type") == "put"]
    tradeable_calls = spy_scanner.scan_single_legs(calls, "call", exp, "SWING", spot_price=spot)
    tradeable_puts = spy_scanner.scan_single_legs(puts, "put", exp, "SWING", spot_price=spot)
    if tradeable_calls or tradeable_puts:
        return True, (
            f"OK - {len(tradeable_calls)} call / {len(tradeable_puts)} put candidate(s) "
            f"clear liquidity + price cap at {exp}"
        )
    return False, f"no candidate clears liquidity + \\${spy_scanner.MAX_CONTRACT_ASK:.2f} price cap at {exp} (spot ${spot:.2f})"


def main() -> int:
    print(f"MAX_CONTRACT_ASK=${spy_scanner.MAX_CONTRACT_ASK:.2f}  MAX_RISK_PER_TRADE=${spy_scanner.MAX_RISK_PER_TRADE:.0f}")
    print(f"MIN_OPEN_INTEREST={spy_scanner.MIN_OPEN_INTEREST}  MIN_OPTION_VOLUME={spy_scanner.MIN_OPTION_VOLUME}")
    print()
    failed = []
    for ticker in sorted(spy_scanner.MEAN_REVERSION_VALIDATED_TICKERS):
        ok, detail = check_ticker(ticker)
        print(f"{ticker}: {'PASS' if ok else 'FAIL'} - {detail}")
        if not ok:
            failed.append(ticker)
    print()
    if failed:
        print(f"!! {len(failed)} validated ticker(s) currently cannot produce a real trade: {failed}")
        print("This can be a genuine, real block (drop the ticker) or a market-closed/weekend")
        print("liquidity snapshot artifact (recheck when markets are open) - it is not")
        print("automatically safe to ignore either way without checking which one it is.")
        return 1
    print("All validated tickers currently clear the real entry filter.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
