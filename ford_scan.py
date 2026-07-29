#!/usr/bin/env python3
"""
Ford (F) options scanner — free, self-hosted replacement for the Cowork version.

Runs every 5 min via GitHub Actions (see .github/workflows/ford-scan.yml).
Uses Tradier's official brokerage API for market data (and optionally your
Tradier account's positions, if TRADIER_ACCOUNT_ID is set) instead of any
unofficial Robinhood scraping.

State (the trade log / "watchlist") is a CSV committed back into this repo
by the GitHub Action after each run — that's the free substitute for a
database, since GitHub Actions runners are stateless between runs.

Env vars required (set as GitHub Actions secrets):
  TRADIER_TOKEN         - your Tradier API bearer token (production or sandbox)
  TRADIER_BASE_URL       - https://api.tradier.com/v1 (default) or
                            https://sandbox.tradier.com/v1 for paper trading
  DISCORD_WEBHOOK_URL    - Discord incoming webhook URL for notifications
  TRADIER_ACCOUNT_ID     - optional. If set, the script also checks your real
                            Tradier positions for F options and reports P&L /
                            stop-out / take-profit against them. If unset,
                            the script only scans for candidates and tracks
                            the *suggested* plays in the CSV log (you place
                            trades wherever you want; the log is the script's
                            own memory of what it suggested, not your broker).

Never places, modifies, or cancels any order. Read-only + notifications only.
"""

import os
import sys
import csv
import json
import html
import time
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TICKER = "F"
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN")
TRADIER_ACCOUNT_ID = os.environ.get("TRADIER_ACCOUNT_ID")  # optional
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")

REPO_ROOT = Path(__file__).resolve().parent
STATE_DIR = REPO_ROOT / "state"
DOCS_DIR = REPO_ROOT / "docs"
LOG_PATH = STATE_DIR / "ford-plays-log.csv"
DASHBOARD_PATH = DOCS_DIR / "index.html"

LOG_HEADER = [
    "timestamp", "action", "play_type", "ticker", "call_or_put", "strike",
    "expiration", "cost_or_credit", "delta_at_entry", "outcome", "pct_gain_loss",
    "closed_at",
]

# Market hours gate (Central Time, matches Robinhood/US equity options hours)
MARKET_TZ = ZoneInfo("America/Chicago")
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)

# Candidate screening thresholds — tune these to taste
MIN_OPEN_INTEREST = 25
SPREAD_SHORT_DELTA_MIN = 0.10
SPREAD_SHORT_DELTA_MAX = 0.35
SINGLE_LEG_DELTA_MIN = 0.35   # regular/swing legs: avoid deep ITM or ultra-far OTM
SINGLE_LEG_DELTA_MAX = 0.65
STRIKE_BAND_PCT = 0.20         # only consider strikes within +/-20% of spot

# Management rule thresholds
SPREAD_STOP_MULTIPLE = 2.0     # stop out if cost to close ~doubles the credit
SPREAD_TAKE_PROFIT_PCT = 0.50  # take profit at 50% of credit captured
SINGLE_TAKE_PROFIT_PCT = 0.225 # +22.5% (midpoint of the 20-25% band)
SINGLE_STOP_PCT = 0.225        # -22.5%

SESSION = requests.Session()


# ---------------------------------------------------------------------------
# Tradier API helpers
# ---------------------------------------------------------------------------

def tradier_get(path, params=None):
    if not TRADIER_TOKEN:
        print("ERROR: TRADIER_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)
    resp = SESSION.get(
        f"{TRADIER_BASE_URL}{path}",
        params=params or {},
        headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
        timeout=20,
    )
    resp.raise_for_status()
    return resp.json()


def get_quote(symbol):
    data = tradier_get("/markets/quotes", {"symbols": symbol, "greeks": "false"})
    q = data.get("quotes", {}).get("quote")
    if isinstance(q, list):
        q = q[0]
    return q


def get_expirations(symbol):
    data = tradier_get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    exp = data.get("expirations", {}).get("date")
    if exp is None:
        return []
    if isinstance(exp, str):
        return [exp]
    return exp


def get_strikes(symbol, expiration):
    data = tradier_get("/markets/options/strikes", {"symbol": symbol, "expiration": expiration})
    s = data.get("strikes", {}).get("strike")
    if s is None:
        return []
    if isinstance(s, (int, float)):
        return [s]
    return s


def get_chain(symbol, expiration):
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )
    opts = data.get("options", {}).get("option")
    if opts is None:
        return []
    if isinstance(opts, dict):
        return [opts]
    return opts


def get_positions(account_id):
    data = tradier_get(f"/accounts/{account_id}/positions")
    pos = data.get("positions", {})
    if pos in (None, "null"):
        return []
    p = pos.get("position")
    if p is None:
        return []
    if isinstance(p, dict):
        return [p]
    return p


# ---------------------------------------------------------------------------
# Market hours gate
# ---------------------------------------------------------------------------

def market_is_open_now():
    now = datetime.now(MARKET_TZ)
    if now.weekday() >= 5:  # Sat/Sun
        return False, now
    open_t = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_t = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_t <= now <= close_t, now


# ---------------------------------------------------------------------------
# CSV log (the free substitute for the watchlist / trade memory)
# ---------------------------------------------------------------------------

def read_log():
    if not LOG_PATH.exists():
        return []
    with open(LOG_PATH, newline="") as f:
        return list(csv.DictReader(f))


def write_log(rows):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=LOG_HEADER)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def append_log_row(rows, **kwargs):
    row = {k: "" for k in LOG_HEADER}
    row.update(kwargs)
    rows.append(row)


def open_rows(rows):
    return [r for r in rows if r.get("outcome") == "OPEN"]


# ---------------------------------------------------------------------------
# Candidate scanning
# ---------------------------------------------------------------------------

def pick_expirations(expirations, today):
    """Return (near_term, swing_candidates) expiration lists.
    near_term: expirations within ~8 days, for spreads + regular plays.
    swing: expirations roughly 14-42 days out.
    """
    near, swing = [], []
    for e in expirations:
        d = datetime.strptime(e, "%Y-%m-%d").date()
        days_out = (d - today).days
        if 0 < days_out <= 8:
            near.append(e)
        elif 14 <= days_out <= 42:
            swing.append(e)
    return sorted(near), sorted(swing)


def filter_strikes(strikes, spot):
    lo, hi = spot * (1 - STRIKE_BAND_PCT), spot * (1 + STRIKE_BAND_PCT)
    return sorted(s for s in strikes if lo <= s <= hi)


def real_bid(opt):
    return opt.get("bid") and opt.get("bid") > 0


def has_liquidity(opt):
    return real_bid(opt) and (opt.get("open_interest") or 0) >= MIN_OPEN_INTEREST


def scan_credit_spreads(chain_calls, chain_puts, expiration, spot):
    """Low-delta short leg, next strike out as the long leg, real bid on both."""
    candidates = []
    for kind, chain in (("call", chain_calls), ("put", chain_puts)):
        by_strike = {o["strike"]: o for o in chain if has_liquidity(o)}
        strikes = sorted(by_strike.keys())
        for i, k in enumerate(strikes):
            short_opt = by_strike[k]
            delta = abs((short_opt.get("greeks") or {}).get("delta") or 0)
            if not (SPREAD_SHORT_DELTA_MIN <= delta <= SPREAD_SHORT_DELTA_MAX):
                continue
            # long leg = next strike further OTM
            long_strike = strikes[i + 1] if kind == "call" and i + 1 < len(strikes) else None
            if kind == "put":
                long_strike = strikes[i - 1] if i - 1 >= 0 else None
            if long_strike is None or long_strike not in by_strike:
                continue
            long_opt = by_strike[long_strike]
            if not (long_opt.get("ask") and long_opt.get("ask") > 0):
                continue
            credit = short_opt["bid"] - long_opt["ask"]
            width = abs(k - long_strike)
            if credit <= 0 or width <= 0:
                continue
            max_loss = width - credit
            candidates.append({
                "play_type": "SPREAD",
                "call_or_put": kind,
                "sell_strike": k,
                "buy_strike": long_strike,
                "expiration": expiration,
                "credit": round(credit, 2),
                "max_loss": round(max_loss, 2),
                "delta": round(delta, 3),
                "pop_approx": round(1 - delta, 3),
                "sell_bid": short_opt["bid"], "sell_ask": short_opt.get("ask"),
                "buy_bid": long_opt.get("bid"), "buy_ask": long_opt["ask"],
            })
    return candidates


def scan_single_legs(chain_calls, chain_puts, expiration, play_type):
    candidates = []
    for kind, chain in (("call", chain_calls), ("put", chain_puts)):
        for o in chain:
            if not has_liquidity(o):
                continue
            delta = abs((o.get("greeks") or {}).get("delta") or 0)
            if not (SINGLE_LEG_DELTA_MIN <= delta <= SINGLE_LEG_DELTA_MAX):
                continue
            cost = o.get("ask")
            if not cost or cost <= 0:
                continue
            candidates.append({
                "play_type": play_type,
                "call_or_put": kind,
                "strike": o["strike"],
                "expiration": expiration,
                "cost": round(cost, 2),
                "delta": round(delta, 3),
                "bid": o.get("bid"), "ask": o.get("ask"),
                "open_interest": o.get("open_interest"),
            })
    return candidates


def fmt_strike(x):
    """Consistent strike formatting (16.0 -> '16', 14.5 -> '14.5') so the same
    strike always produces the same string — otherwise '16' vs '16.0' would
    make already_tracked() think an existing play is a brand-new candidate
    every single run and spam duplicate log rows / notifications."""
    return f"{float(x):g}"


def format_spread_strike(sell_strike, buy_strike):
    """Self-labeling strike field for the CSV log — never rely on a silent
    'first number is the sell leg' convention. Anyone opening the raw CSV
    (or reading a Discord/dashboard line) should see BUY/SELL explicitly."""
    return f"SELL {fmt_strike(sell_strike)} / BUY {fmt_strike(buy_strike)}"


def parse_spread_strikes(strike_field):
    """Parses 'SELL 14.5 / BUY 14' -> (14.5, 14.0). Falls back to a bare
    'sell/buy' numeric pair for any older-format rows already in the log."""
    import re
    m = re.search(r"SELL\s*([\d.]+)\s*/\s*BUY\s*([\d.]+)", strike_field, re.IGNORECASE)
    if m:
        return float(m.group(1)), float(m.group(2))
    # legacy fallback: plain "14.5/14"
    sell_s, buy_s = strike_field.split("/")
    return float(sell_s), float(buy_s)


def already_tracked(open_log_rows, play_type, call_or_put, strike_str, expiration):
    for r in open_log_rows:
        if (r.get("play_type") == play_type and r.get("call_or_put") == call_or_put
                and r.get("strike") == strike_str and r.get("expiration") == expiration):
            return True
    return False


# ---------------------------------------------------------------------------
# P&L + management rules for open plays
# ---------------------------------------------------------------------------

def chain_lookup(chain, strike):
    for o in chain:
        if o["strike"] == strike:
            return o
    return None


def days_to_expiry(expiration_str):
    d = datetime.strptime(expiration_str, "%Y-%m-%d").date()
    return (d - date.today()).days


def evaluate_open_row(row, chains_by_exp):
    """Returns dict with live pricing / P&L / signal for one OPEN log row.
    Signal priority matches the original rules: STOP OUT, then TAKE PROFIT,
    then hard EXPIRY CLOSE the day before/of expiration, else HOLD."""
    exp = row["expiration"]
    kind = row["call_or_put"]
    chain = (chains_by_exp.get(exp) or {}).get(kind, [])
    expiring_soon = days_to_expiry(exp) <= 1

    if row["play_type"] == "SPREAD":
        sell_s, buy_s = parse_spread_strikes(row["strike"])
        sell_opt = chain_lookup(chain, sell_s)
        buy_opt = chain_lookup(chain, buy_s)
        if not sell_opt or not buy_opt:
            return {"signal": "HOLD", "note": "no live quote", "pl_dollars": None, "pl_pct": None}
        credit = float(row["cost_or_credit"].replace(" credit", ""))
        cost_to_close = (sell_opt.get("ask") or sell_opt.get("last") or 0) - (buy_opt.get("bid") or buy_opt.get("last") or 0)
        pl_per_spread = credit - cost_to_close
        pl_pct_of_credit = (pl_per_spread / credit) if credit else 0
        signal = "HOLD"
        if cost_to_close >= credit * SPREAD_STOP_MULTIPLE:
            signal = "STOP OUT"
        elif pl_per_spread >= credit * SPREAD_TAKE_PROFIT_PCT:
            signal = "TAKE PROFIT"
        elif expiring_soon:
            signal = "EXPIRY CLOSE"
        return {
            "signal": signal, "pl_dollars": round(pl_per_spread * 100, 2),
            "pl_pct": round(pl_pct_of_credit * 100, 1),
            "cost_to_close": round(cost_to_close, 2),
            "sell_quote": sell_opt, "buy_quote": buy_opt,
        }
    else:
        strike = float(row["strike"])
        opt = chain_lookup(chain, strike)
        if not opt:
            return {"signal": "HOLD", "note": "no live quote", "pl_dollars": None, "pl_pct": None}
        entry = float(row["cost_or_credit"])
        mark = ((opt.get("bid") or 0) + (opt.get("ask") or 0)) / 2 or opt.get("last") or 0
        pl_per_contract = mark - entry
        pl_pct = (pl_per_contract / entry) if entry else 0
        signal = "HOLD"
        if pl_pct <= -SINGLE_STOP_PCT:
            signal = "STOP OUT"
        elif pl_pct >= SINGLE_TAKE_PROFIT_PCT:
            signal = "TAKE PROFIT"
        elif expiring_soon:
            signal = "EXPIRY CLOSE"
        return {
            "signal": signal, "pl_dollars": round(pl_per_contract * 100, 2),
            "pl_pct": round(pl_pct * 100, 1), "mark": round(mark, 2), "quote": opt,
        }


# ---------------------------------------------------------------------------
# Discord notifications
# ---------------------------------------------------------------------------

def notify_discord(lines, title=None):
    if not DISCORD_WEBHOOK_URL or not lines:
        return
    content = ("**" + title + "**\n" if title else "") + "\n".join(lines)
    try:
        SESSION.post(DISCORD_WEBHOOK_URL, json={"content": content[:1900]}, timeout=10)
    except requests.RequestException as e:
        print(f"Discord notify failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Dashboard (static HTML, safe to publish — no secrets embedded)
# ---------------------------------------------------------------------------

def _play_title(row, esc):
    if row["play_type"] == "SPREAD":
        sell_s, buy_s = parse_spread_strikes(row["strike"])
        return f'SPREAD &middot; {esc(row["call_or_put"].upper())} ({esc(row["expiration"])})', sell_s, buy_s
    return f'{esc(row["play_type"])} &middot; {esc(row["call_or_put"].upper())} {esc(row["strike"])} ({esc(row["expiration"])})', None, None


def render_dashboard(spot_quote, open_evals, all_rows, new_candidates_summary, closed_today_summary):
    """open_evals: [(row, eval_dict), ...] for currently-OPEN rows (live P&L).
    all_rows: the FULL log (every row ever written) — used to build the
    Watchlist tab (entry details only, no live calls needed) and the
    Closed/Winners&Losers tab (outcome WIN/LOSS history)."""
    now_ct = datetime.now(MARKET_TZ).strftime("%Y-%m-%d %H:%M %Z")
    last = spot_quote.get("last") if spot_quote else None
    prev_close = spot_quote.get("prevclose") if spot_quote else None
    chg = (last - prev_close) if (last and prev_close) else None
    chg_pct = (chg / prev_close * 100) if (chg is not None and prev_close) else None

    def esc(s):
        return html.escape(str(s))

    # ---- Tab 1: Watchlist — entry details only (strike, expiration, entry price/credit, delta) ----
    watchlist_html = []
    for row in all_rows:
        if row.get("outcome") != "OPEN":
            continue
        title, sell_s, buy_s = _play_title(row, esc)
        legs = ""
        if row["play_type"] == "SPREAD":
            legs = (f'<div class="legrow"><span><b>SELL</b> {esc(sell_s)} {esc(row["call_or_put"].upper())}</span></div>'
                    f'<div class="legrow"><span><b>BUY</b> {esc(buy_s)} {esc(row["call_or_put"].upper())}</span></div>')
        watchlist_html.append(f'''
          <div class="play-group">
            <div class="play-head">
              <div class="play-title">{title}</div>
              <div class="plsub">Entry: {esc(row.get("cost_or_credit",""))} &middot; Δ {esc(row.get("delta_at_entry",""))}</div>
            </div>
            <div class="plsub">Suggested {esc(row.get("timestamp","")[:16].replace("T"," "))}</div>
            {legs}
          </div>''')

    # ---- Tab 2: Open Trades — live P&L + signal ----
    open_html = []
    for row, ev in open_evals:
        pl = ev.get("pl_dollars")
        pl_cls = "pos" if (pl or 0) > 0 else ("neg" if (pl or 0) < 0 else "zero")
        signal = ev.get("signal", "—")
        sig_cls = "sig-warn" if signal in ("STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE") else "sig-hold"
        title, sell_s, buy_s = _play_title(row, esc)
        legs = ""
        if row["play_type"] == "SPREAD":
            legs = (f'<div class="legrow"><span><b>SELL</b> {esc(sell_s)} {esc(row["call_or_put"].upper())}</span></div>'
                    f'<div class="legrow"><span><b>BUY</b> {esc(buy_s)} {esc(row["call_or_put"].upper())}</span></div>')
        open_html.append(f'''
          <div class="play-group">
            <div class="play-head">
              <div class="play-title">{title}</div>
              <div class="pl {pl_cls}">{"—" if pl is None else f"${pl:.2f}"} {"" if ev.get("pl_pct") is None else f"({ev['pl_pct']}%)"}</div>
            </div>
            <div class="plsub">Signal: <span class="{sig_cls}">{esc(signal)}</span></div>
            {legs}
          </div>''')

    # ---- Tab 3: Closed — Winners & Losers ----
    closed_rows = [r for r in all_rows if r.get("outcome") in ("WIN", "LOSS")]
    closed_rows.sort(key=lambda r: r.get("closed_at") or "", reverse=True)
    wins = sum(1 for r in closed_rows if r["outcome"] == "WIN")
    losses = sum(1 for r in closed_rows if r["outcome"] == "LOSS")
    win_rate = f"{wins/(wins+losses)*100:.0f}%" if (wins + losses) else "—"
    closed_html = []
    for row in closed_rows:
        title, sell_s, buy_s = _play_title(row, esc)
        win = row["outcome"] == "WIN"
        badge_cls = "badge-win" if win else "badge-loss"
        pct = row.get("pct_gain_loss") or ""
        closed_html.append(f'''
          <div class="play-group closed">
            <div class="play-head">
              <div class="play-title">{title}</div>
              <div><span class="badge {badge_cls}">{"WIN" if win else "LOSS"}</span> <span class="pl {"pos" if win else "neg"}">{esc(pct)}%</span></div>
            </div>
            <div class="plsub">Entry: {esc(row.get("cost_or_credit",""))} &middot; Opened {esc(row.get("timestamp","")[:10])} &middot; Closed {esc((row.get("closed_at") or "")[:16].replace("T"," ") or "—")}</div>
          </div>''')

    html_doc = f'''<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta http-equiv="refresh" content="300">
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; background:#fff; color:#1a1a1a; padding:20px; max-width:720px; margin:0 auto; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color:#666; font-size:13px; margin-bottom:16px; }}
  .card {{ border:1px solid #e2e2e2; border-radius:10px; padding:16px; margin-bottom:16px; background:#fafafa; }}
  .card h2 {{ font-size:14px; text-transform:uppercase; letter-spacing:.04em; color:#555; margin:0 0 10px; }}
  .price {{ font-size:28px; font-weight:700; }}
  .chg {{ font-size:14px; font-weight:600; }}
  .up {{ color:#16794d; }} .down {{ color:#c22b2b; }} .flat {{ color:#666; }}
  .play-group {{ border:1px solid #dfe3ea; border-radius:8px; padding:10px 12px; margin-bottom:10px; background:#fff; border-left:4px solid #6b5bd6; }}
  .play-group.closed {{ border-left-color:#999; }}
  .play-head {{ display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; }}
  .play-title {{ font-weight:700; font-size:13.5px; }}
  .pl {{ font-weight:700; font-size:14px; }}
  .pl.pos {{ color:#16794d; }} .pl.neg {{ color:#c22b2b; }} .pl.zero {{ color:#666; }}
  .plsub {{ font-size:11px; color:#777; margin-top:4px; }}
  .legrow {{ font-size:12px; color:#555; padding:2px 0; }}
  .muted {{ color:#888; font-size:13px; }}
  .footer {{ color:#999; font-size:11px; margin-top:6px; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; }}
  .badge-win {{ background:#eaf7ee; color:#1c8a44; }}
  .badge-loss {{ background:#fdeceb; color:#b0281c; }}
  .sig-hold {{ color:#555; font-weight:700; }}
  .sig-warn {{ color:#b0281c; font-weight:700; }}
  .tabs {{ display:flex; gap:6px; margin-bottom:14px; border-bottom:1px solid #e2e2e2; }}
  .tab-btn {{ appearance:none; border:none; background:none; padding:10px 14px; font-size:13px; font-weight:600;
             color:#888; cursor:pointer; border-bottom:2px solid transparent; }}
  .tab-btn.active {{ color:#1a1a1a; border-bottom-color:#6b5bd6; }}
  .tab-panel {{ display:none; }}
  .tab-panel.active {{ display:block; }}
</style></head>
<body>
<h1>Ford (F) Options Scan</h1>
<div class="sub">Self-hosted &middot; Tradier data &middot; auto-refreshes every 5 min &middot; analysis only, no trades placed automatically &middot; last run: {now_ct}</div>

<div class="card">
  <h2>Spot</h2>
  {"<div class='price'>$" + f"{last:.2f}" + "</div><div class='chg " + ("up" if (chg or 0) > 0 else "down" if (chg or 0) < 0 else "flat") + "'>" + (f"{chg:+.2f} ({chg_pct:+.2f}%)" if chg is not None else "") + "</div>" if last else "<div class='muted'>Quote unavailable</div>"}
</div>

<div class="tabs">
  <button class="tab-btn active" data-tab="open">Open Trades ({len(open_html)})</button>
  <button class="tab-btn" data-tab="watchlist">Watchlist ({len(watchlist_html)})</button>
  <button class="tab-btn" data-tab="closed">Closed &middot; {wins}W-{losses}L ({win_rate})</button>
</div>

<div id="tab-open" class="tab-panel active">
  {"".join(open_html) if open_html else "<div class='muted'>Nothing open right now.</div>"}
</div>

<div id="tab-watchlist" class="tab-panel">
  {"".join(watchlist_html) if watchlist_html else "<div class='muted'>Watchlist is empty.</div>"}
</div>

<div id="tab-closed" class="tab-panel">
  {"".join(closed_html) if closed_html else "<div class='muted'>Nothing closed yet.</div>"}
</div>

<div class="card">
  <h2>Latest Scan Summary</h2>
  <div class="muted">{esc(new_candidates_summary)}</div>
  <div class="muted">{esc(closed_today_summary)}</div>
  <div class="footer">Generated by GitHub Actions every 5 min during market hours (8:30am&ndash;3:00pm CT, Mon&ndash;Fri).</div>
</div>

<script>
document.querySelectorAll('.tab-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
  }});
}});
</script>

</body></html>'''
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    DASHBOARD_PATH.write_text(html_doc)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    is_open, now = market_is_open_now()
    if not is_open:
        print(f"Market closed ({now.isoformat()}), exiting without using API calls.")
        return

    rows = read_log()
    spot = get_quote(TICKER)
    if not spot or not spot.get("last"):
        print("Could not get spot quote, aborting run.", file=sys.stderr)
        return
    spot_price = spot["last"]

    expirations = get_expirations(TICKER)
    near_exps, swing_exps = pick_expirations(expirations, date.today())

    # ---- pull chains for every relevant expiration once ----
    chains_by_exp = {}
    for exp in set(near_exps[:2] + swing_exps[:2]):  # cap API calls: nearest 2 of each bucket
        strikes = filter_strikes(get_strikes(TICKER, exp), spot_price)
        full_chain = get_chain(TICKER, exp)
        calls = [o for o in full_chain if o.get("option_type") == "call" and o["strike"] in strikes]
        puts = [o for o in full_chain if o.get("option_type") == "put" and o["strike"] in strikes]
        chains_by_exp[exp] = {"call": calls, "put": puts}

    # ---- evaluate currently OPEN rows against fresh quotes ----
    open_log_rows = open_rows(rows)
    evaluated = []
    closed_notes = []
    for row in open_log_rows:
        ev = evaluate_open_row(row, chains_by_exp)
        evaluated.append((row, ev))
        signal = ev.get("signal")
        if signal in ("STOP OUT", "TAKE PROFIT", "EXPIRY CLOSE"):
            pl_pct = ev.get("pl_pct") or 0
            if signal == "TAKE PROFIT":
                row["outcome"] = "WIN"
            elif signal == "STOP OUT":
                row["outcome"] = "LOSS"
            else:  # EXPIRY CLOSE - win or loss depends on which side of breakeven it ended up on
                row["outcome"] = "WIN" if pl_pct > 0 else "LOSS"
            row["pct_gain_loss"] = str(ev.get("pl_pct", ""))
            row["closed_at"] = datetime.now(MARKET_TZ).isoformat()
            closed_notes.append(
                f'{signal} — {row["play_type"]} {row["call_or_put"].upper()} {row["strike"]} '
                f'({row["expiration"]}) {ev.get("pl_pct")}%'
            )

    # ---- scan for new candidates ----
    new_rows = []
    for exp in near_exps[:1]:  # nearest weekly expiration for spreads + regular
        calls, puts = chains_by_exp.get(exp, {}).get("call", []), chains_by_exp.get(exp, {}).get("put", [])
        for c in scan_credit_spreads(calls, puts, exp, spot_price):
            strike_str = format_spread_strike(c["sell_strike"], c["buy_strike"])
            if already_tracked(open_log_rows, "SPREAD", c["call_or_put"], strike_str, exp):
                continue
            append_log_row(
                rows, timestamp=datetime.now(MARKET_TZ).isoformat(), action="SELL open",
                play_type="SPREAD", ticker=TICKER, call_or_put=c["call_or_put"],
                strike=strike_str, expiration=exp,
                cost_or_credit=f'{c["credit"]} credit', delta_at_entry=c["delta"], outcome="OPEN",
            )
            new_rows.append(f'SELL F {c["call_or_put"].upper()} {c["sell_strike"]} / BUY {c["buy_strike"]} '
                             f'({exp}) credit ${c["credit"]}, max loss ${c["max_loss"]}, PoP~{c["pop_approx"]*100:.0f}%')
        for s in scan_single_legs(calls, puts, exp, "REGULAR"):
            strike_str = fmt_strike(s["strike"])
            if already_tracked(open_log_rows, "REGULAR", s["call_or_put"], strike_str, exp):
                continue
            append_log_row(
                rows, timestamp=datetime.now(MARKET_TZ).isoformat(), action="BUY open",
                play_type="REGULAR", ticker=TICKER, call_or_put=s["call_or_put"],
                strike=strike_str, expiration=exp,
                cost_or_credit=str(s["cost"]), delta_at_entry=s["delta"], outcome="OPEN",
            )
            new_rows.append(f'BUY F {s["call_or_put"].upper()} {s["strike"]} ({exp}) ${s["cost"]}, delta {s["delta"]}')

    for exp in swing_exps[:1]:  # nearest swing-window expiration
        calls, puts = chains_by_exp.get(exp, {}).get("call", []), chains_by_exp.get(exp, {}).get("put", [])
        for s in scan_single_legs(calls, puts, exp, "SWING"):
            strike_str = fmt_strike(s["strike"])
            if already_tracked(open_log_rows, "SWING", s["call_or_put"], strike_str, exp):
                continue
            append_log_row(
                rows, timestamp=datetime.now(MARKET_TZ).isoformat(), action="BUY open",
                play_type="SWING", ticker=TICKER, call_or_put=s["call_or_put"],
                strike=strike_str, expiration=exp,
                cost_or_credit=str(s["cost"]), delta_at_entry=s["delta"], outcome="OPEN",
            )
            new_rows.append(f'BUY F {s["call_or_put"].upper()} {s["strike"]} ({exp}) ${s["cost"]}, delta {s["delta"]} [SWING]')

    write_log(rows)

    # ---- notify only on real signals, never on plain no-change runs ----
    notify_lines = list(closed_notes) + new_rows
    if notify_lines:
        notify_discord(notify_lines, title=f"F options — {datetime.now(MARKET_TZ).strftime('%-I:%M %p CT')}")

    # ---- dashboard ----
    new_summary = f"{len(new_rows)} new candidate(s) this scan." if new_rows else "No new candidates this scan."
    closed_summary = f"{len(closed_notes)} closed this scan." if closed_notes else "Nothing closed this scan."
    render_dashboard(spot, evaluated, rows, new_summary, closed_summary)

    print(f"Run complete: {len(new_rows)} new, {len(closed_notes)} closed, {len(evaluated)} open evaluated.")


if __name__ == "__main__":
    main()
