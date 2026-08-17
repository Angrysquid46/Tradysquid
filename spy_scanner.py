"""
Tradysquids dynamic options scanner + Discord paper-trade tracker.

Purpose
-------
- Read-only Tradier market data.
- Tracks each play in CSV, a static HTML dashboard, and one Discord forum post.
- Reprices open plays on each scheduled run and routes closed results to Discord.

Required GitHub Actions secrets
-------------------------------
TRADIER_TOKEN
TRADIER_BASE_URL
DISCORD_WEBHOOK_URL          # fallback alerts
DISCORD_BOT_TOKEN            # TradeBot REST authentication
DISCORD_GUILD_ID             # Tradysquids server ID

Expected Discord channel names
------------------------------
Forum: trade-journal
Text: scanner-feed, qualified-trades, entry-alerts, position-updates,
      exit-alerts, wins, losses, scratches, daily-recap, weekly-report,
      1m-performance, 1m-results, 5m-performance, 5m-results,
      scanner-status, api-errors, workflow-log, admin-notes, welcome,
      strategy-rules, risk-management, server-guide

Expected forum status tags
--------------------------
WATCHING, QUALIFIED, OPEN, HOLDING, TARGET HIT, STOP WARNING,
WIN, LOSS, SCRATCH, EXPIRED
Emoji prefixes are fine. Matching ignores emoji and punctuation.
"""

from __future__ import annotations

import csv
import hashlib
import html
import json
import math
import os
import re
import sys
import tempfile
import threading
import time
from datetime import date, datetime, time as dt_time, timedelta
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import requests
import dynamic_universe
import economic_calendar
import trade_intelligence

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Hard-locked to SPY - this system trades SPY exclusively. Previously
# configurable via a SCAN_TICKER env var to support scanning other tickers
# (multi_ticker_scan.py mutated this at runtime per ticker); that capability
# was removed entirely per explicit owner direction, not just disabled, so
# there is no longer an env-var override to silently repoint this.
TICKER = "SPY"
TRADIER_BASE_URL = os.environ.get("TRADIER_BASE_URL", "https://api.tradier.com/v1").rstrip("/")
TRADIER_TOKEN = os.environ.get("TRADIER_TOKEN", "").strip()
DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
SEC_USER_AGENT = os.environ.get("SEC_USER_AGENT", "").strip()

REPO_ROOT = Path(__file__).resolve().parent
SCANNER_CONFIG_PATH = REPO_ROOT / "config" / "scanner.json"


def configured(name: str, default: Any) -> Any:
    try:
        payload = json.loads(SCANNER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    return payload.get(name, default)


STATE_DIR = REPO_ROOT / "state"
DOCS_DIR = REPO_ROOT / "docs"
LOG_PATH = STATE_DIR / "spy-plays-log.csv"
DASHBOARD_PATH = DOCS_DIR / "index.html"
REPORT_STATE_PATH = STATE_DIR / "discord-report-state.json"
CHART_PATH = DOCS_DIR / "spy-market-chart.svg"
CHART_SCREENSHOT_PATH = DOCS_DIR / "spy-market-chart.png"
TRADE_SNAPSHOT_DIR = DOCS_DIR / "trade-snapshots"
# Tradier does not retain historical data for expired options - there is
# no way to ever go back and ask "what did the chain look like when this
# trade was entered" unless that moment is captured as it happens. This
# doesn't change any entry/exit decision; it only makes future analysis
# possible that otherwise never could be, no matter how good the
# after-the-fact tooling gets.
CHAIN_SNAPSHOT_DIR = DOCS_DIR / "chain-snapshots"
INTRADAY_SNAPSHOT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
DAILY_SNAPSHOT_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
CHART_PUBLIC_URL = os.environ.get(
    "CHART_PUBLIC_URL",
    "https://angrysquid46.github.io/Tradysquid/spy-market-chart.svg",
).strip()

MARKET_TZ = ZoneInfo("America/Chicago")
# Tradier's /markets/timesales endpoint interprets naive start/end strings in
# America/New_York regardless of the timezone the caller meant - confirmed
# live: a request with end="15:00" (intended as 3pm CT close) returned bars
# stopping exactly at 15:00 ET, one hour before the real CT close, silently
# dropping the last hour of every session. Any timesales start/end string
# must be built through _et_window_str() below, not an f-string literal.
TRADIER_TIMESALES_TZ = ZoneInfo("America/New_York")
MARKET_OPEN = (8, 30)
MARKET_CLOSE = (15, 0)

# Candidate screening. Both floors are set from real chain depth, not
# guesses: sampling live chains across the active universe (F, SOFI, AAL,
# CCL, NIO, T, RIVN) showed every one of them has 10-30+ contracts clearing
# open interest 500+, and 5-17 contracts clearing volume 200+, at the near
# expiration alone - these bars are genuinely tradeable, not theoretical.
# Open interest alone doesn't prove a contract is tradeable today - it can
# sit unchanged for weeks. A floor of 1 let contracts with essentially no
# same-day trading (2, 5 contracts) through, and those are exactly the
# fills that turn into unreliable marks: an entry against a quote nobody is
# really trading against, then a mark-to-market swing that isn't a real
# price move. Traced from live paper trades where every position with
# single-digit entry-day option volume showed zero favorable excursion
# before stopping out.
MIN_OPEN_INTEREST = int(os.environ.get("MIN_OPEN_INTEREST", "500"))
MIN_OPTION_VOLUME = int(os.environ.get("MIN_OPTION_VOLUME", "200"))
MAX_BID_ASK_PCT = float(os.environ.get("MAX_BID_ASK_PCT", "0.25"))
# SPY 0DTE: a standalone, ticker-exclusive plan built entirely separate
# from the rest of the system, per explicit owner direction not to reuse
# any of the multi-ticker machinery above. Its own risk cap, own delta
# band, own stop/target, own signal - nothing here is read by any other
# play type, and nothing above is read by this one.
SPY_0DTE_TICKER = "SPY"
SPY_MANUAL_PLAY_TYPE = "SPY_MANUAL"
# SPY_0DTE_1M and SPY_0DTE_5M retired 2026-08-17. Their shared opening-range
# entry measured +0.0004 ATR/trade (t=+0.39) on 1-minute bars and -0.0004
# (t=-0.64, negative in all four eras) on 5-minute bars across 3,347
# sessions - indistinguishable from random entries on the same bars.
#
# SPY_MANUAL stays: it is not a scanner-driven strategy, it is the play
# type an owner-opened position carries, so removing it would strand any
# manual trade with no exit evaluator.
#
# The 0DTE exit machinery (spy_0dte_exit_signal and its tests) is left in
# place, so restoring either variant is a one-line change.
# See docs/BACKTEST_RESULTS.md.
SPY_0DTE_PLAY_TYPES = (SPY_MANUAL_PLAY_TYPE,)


def is_spy_0dte_play_type(play_type: str | None) -> bool:
    """True for either independently-tracked SPY 0DTE variant (1-minute or
    5-minute opening-range bar interval) or a manually-forced entry
    (SPY_MANUAL - see /force-trade) - all three share every exit rule, risk
    cap, and delta band, so every place that branches on "is this a SPY
    0DTE trade" should treat them the same way rather than re-listing each
    string each time."""
    return play_type in SPY_0DTE_PLAY_TYPES


SPY_0DTE_OPENING_RANGE_MINUTES = int(os.environ.get(
    "SPY_0DTE_OPENING_RANGE_MINUTES", configured("spy_0dte_opening_range_minutes", 30)
))
# SPY_0DTE_1M is the variant this system's TradingView webhook was actually
# built for: its own Pine indicator (the one behind the 66.8% backtest) is
# the live entry trigger, not the Python opening-range breakout below - that
# math stays in place only for SPY_0DTE_5M. The 10 ratchet-floor variants
# share this exact same live TradingView alert too, per owner direction -
# they're the same entry as 1M, only their exit (the ratchet floor/stop)
# differs, so there's no reason for them to run a separate, less accurate
# Python approximation of the same entry when the real signal is available.
# A fresh TradingView alert for SPY older than this many seconds no longer
# counts as a live signal, so a position doesn't reopen off a stale alert
# well after the fact.
SPY_0DTE_1M_TRADINGVIEW_MAX_AGE_SECONDS = int(os.environ.get(
    "SPY_0DTE_1M_TRADINGVIEW_MAX_AGE_SECONDS",
    configured("spy_0dte_1m_tradingview_max_age_seconds", 180),
))
# Keyed by play_type, not a single value - the same TradingView alert has
# to be able to independently open SPY_0DTE_1M and every enabled ratchet
# variant without one variant consuming it and starving the other ten.
SPY_TRADINGVIEW_CONSUMED_EVENT_PATH = STATE_DIR / "spy-tradingview-consumed.json"
SPY_0DTE_DELTA_MIN = float(os.environ.get(
    "SPY_0DTE_DELTA_MIN", configured("spy_0dte_delta_min", 0.40)
))
SPY_0DTE_DELTA_MAX = float(os.environ.get(
    "SPY_0DTE_DELTA_MAX", configured("spy_0dte_delta_max", 0.60)
))
SPY_0DTE_MAX_CONTRACT_ASK = float(os.environ.get(
    "SPY_0DTE_MAX_CONTRACT_ASK", configured("spy_0dte_max_contract_ask", 5.00)
))
SPY_0DTE_MAX_RISK_PER_TRADE = float(os.environ.get(
    "SPY_0DTE_MAX_RISK_PER_TRADE", configured("spy_0dte_max_risk_per_trade", 500.0)
))
# Backtested on real intraday bars (opening-range breakout, real
# transaction costs, worst-case intrabar stop/target checks): 86% win
# rate, +59.4% avg return/trade on the recent 8-week window, and
# separately re-validated against a real historical correction+recovery
# (Robinhood get_equity_historicals, March-April 2026, SPY's real -9.1%
# drawdown that quarter): 81% win rate, bullish and bearish sides
# performing almost identically (+71%/+69% avg), proving the downside
# isn't just noise inside an uptrend. Live now (trade_types_enabled.
# spy_0dte = true).
SPY_0DTE_STOP_PCT = float(os.environ.get(
    "SPY_0DTE_STOP_PCT", configured("spy_0dte_stop_pct", 0.50)
))
SPY_0DTE_TARGET_PCT = float(os.environ.get(
    "SPY_0DTE_TARGET_PCT", configured("spy_0dte_target_pct", 0.50)
))
# Once a trade proves itself (crosses this peak), the stop-loss floor
# raises ONCE from -50% to SPY_0DTE_FLOOR_PCT and holds there - it does
# not keep trailing behind every subsequent tick. A continuously-
# trailing stop was tested and tested badly (it caught 21 of 24 fires
# on trades that would have gone on to hit the real 50% target, only 3
# were genuine saves) because 0DTE dips and recovers constantly on the
# way to a real move. A one-time raised floor, at a wide enough level to
# survive normal noise, gave up ~5% of total backtested profit in
# exchange for capping the worst case per trade at -15% instead of the
# full -50% - a real trade-off, not free money, but the disaster case
# (a trade that peaks near the target and fully round-trips to the
# stop) is real and happened 3 times in 62 backtested trades.
SPY_0DTE_FLOOR_TRIGGER_PCT = float(os.environ.get(
    "SPY_0DTE_FLOOR_TRIGGER_PCT", configured("spy_0dte_floor_trigger_pct", 30.0)
))
SPY_0DTE_FLOOR_PCT = float(os.environ.get(
    "SPY_0DTE_FLOOR_PCT", configured("spy_0dte_floor_pct", -15.0)
))
# SPY Ratchet-floor variants: 10 independently-tracked strategies, each
# reusing SPY_0DTE's exact entry signal and contract selection (delta band,
# max ask, risk cap - all shared as-is, not duplicated), but with a
# different exit shape - no fixed take-profit target; a floor that locks in
# profit every step_pct once peak gain first crosses it, and ratchets up
# every further step; stop_pct only applies before the first step ever
# fires. Picked from a 1,680-combo backtest against real Tradier 1-minute
# SPY history (2026-08-10) - the 10 best-performing, non-degenerate
# (step, stop) pairs, all net positive (PF 1.33-1.62 on that sample). One
# shared exit function (spy_ratchet_exit_signal) serves all 10, each fed
# its own numbers from this table - see SPY_RATCHET_VARIANT_BY_PLAY_TYPE.
# RETIRED 2026-08-17. All 10 ratchet-floor variants are gone, on
# measurement rather than preference:
#
# - the ORB entry all ten shared measured +0.0004 ATR/trade (t=+0.39) over
#   3,347 sessions of real 1-minute data - indistinguishable from random
#   entries on the same bars
# - once the exit shapes were separable, which required the Phase 5 option
#   model since step_pct/stop_pct are defined in option-premium percent,
#   every ratchet placed BELOW the SPY_0DTE shape already deployed: best
#   ratchet -$275k against SPY_0DTE's -$156k, worst -$417k. Their tight
#   -16% to -18% base stops dropped win rates to 28-30% versus 42.9%.
#
# Emptied rather than deleted line by line: every derived structure -
# SPY_RATCHET_PLAY_TYPES, SPY_RATCHET_VARIANT_BY_PLAY_TYPE, the
# CHANNEL_NAMES entries, performance_reconciliation's REPORT_ROUTES - is
# generated from this tuple, so they all empty together and no ratchet
# channel gets recreated. spy_ratchet_exit_signal and its tests stay
# intact and passing, so restoring a variant is a one-line change if the
# owner ever wants one back.
#
# See docs/BACKTEST_RESULTS.md and docs/OPTION_RESULTS.md.
SPY_RATCHET_VARIANTS: tuple[dict[str, Any], ...] = ()
SPY_RATCHET_PLAY_TYPES = tuple(variant["play_type"] for variant in SPY_RATCHET_VARIANTS)
SPY_RATCHET_VARIANT_BY_PLAY_TYPE = {variant["play_type"]: variant for variant in SPY_RATCHET_VARIANTS}


def is_spy_ratchet_play_type(play_type: str | None) -> bool:
    """True for any of the 10 independently-tracked ratchet-floor variants -
    same pattern as is_spy_0dte_play_type, so callers don't re-list all 10
    strings each time."""
    return play_type in SPY_RATCHET_VARIANT_BY_PLAY_TYPE


STRIKE_BAND_PCT = float(os.environ.get("STRIKE_BAND_PCT", "0.12"))
REENTRY_COOLDOWN_MINUTES = int(os.environ.get("REENTRY_COOLDOWN_MINUTES", "1440"))
# No cap by default, per explicit direction: limiting how many positions
# can stack on one ticker only controls concentration, it doesn't make any
# individual trade smarter - and that's the part that actually needs
# fixing. The mechanism (apply_ticker_exposure_cap) stays in place and
# stays configurable in scanner.json, in case this needs revisiting later,
# but it applies no real limit unless deliberately set lower.
MAX_OPEN_POSITIONS_PER_TICKER = int(os.environ.get(
    "MAX_OPEN_POSITIONS_PER_TICKER", configured("max_open_positions_per_ticker", 99)
))
MAX_EXTENSION_ABOVE_SMA20_PCT = float(os.environ.get("MAX_EXTENSION_ABOVE_SMA20_PCT", "0.05"))

# The six legacy strategies below (regular/swing/spread) are retired - no
# new trade of these types can open - but these constants are retained
# because historical rows of these types remain in the trade log forever,
# and journal backfill/entry-alert rendering for those old rows still needs
# their real numbers, not made-up ones.
SPREAD_STOP_MULTIPLE = float(os.environ.get(
    "SPREAD_STOP_MULTIPLE", configured("spread_stop_multiple", 2.0)
))
SPREAD_TAKE_PROFIT_PCT = float(os.environ.get(
    "SPREAD_TAKE_PROFIT_PCT", configured("spread_profit_target_pct", 0.50)
))
SINGLE_TAKE_PROFIT_PCT = float(os.environ.get(
    "SINGLE_TAKE_PROFIT_PCT", configured("single_leg_profit_target_pct", 0.20)
))
SINGLE_STOP_PCT = float(os.environ.get(
    "SINGLE_STOP_PCT", configured("single_leg_stop_pct", 0.15)
))
SWING_STOP_PCT = float(os.environ.get(
    "SWING_STOP_PCT", configured("swing_stop_pct", 0.25)
))


# Discord update throttling
DISCORD_PL_CHANGE_THRESHOLD = float(os.environ.get("DISCORD_PL_CHANGE_THRESHOLD", "10.0"))
DISCORD_HEARTBEAT_MINUTES = int(os.environ.get("DISCORD_HEARTBEAT_MINUTES", "15"))
DISCORD_SYNC_EXISTING_OPEN = os.environ.get("DISCORD_SYNC_EXISTING_OPEN", "true").lower() == "true"
DISCORD_MIGRATE_LEGACY_MESSAGES = os.environ.get(
    "DISCORD_MIGRATE_LEGACY_MESSAGES", "false"
).lower() == "true"
DISCORD_FORMAT_VERSION = "13"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Tradysquids-TradeBot/1.0"})

LOG_HEADER = [
    "trade_id",
    "timestamp",
    "action",
    "play_type",
    "ticker",
    "call_or_put",
    "strike",
    "expiration",
    "option_symbol",
    "short_symbol",
    "long_symbol",
    "cost_or_credit",
    "entry_price",
    "exit_price",
    "entry_contract_value",
    "exit_contract_value",
    "result_price_source",
    "delta_at_entry",
    "theta_at_entry",
    "iv_at_entry",
    "pop_estimate",
    "max_profit",
    "max_risk",
    "breakeven",
    "open_interest_at_entry",
    "bid_ask_width_at_entry",
    "option_volume_at_entry",
    "setup_score",
    "setup_reason",
    "market_regime",
    # Universal, cross-strategy market-condition tag (trend + volatility
    # bucket, e.g. "TRENDING_UP / HIGH VOL") - distinct from market_regime
    # above, which is each strategy's own directional call, not comparable
    # across strategies. Computed once per scan cycle from SPY's own daily
    # price action (classify_market_condition) and stamped on every trade
    # opened that cycle, so results can be broken down by market condition
    # the same way regardless of which strategy opened the trade.
    "market_condition_at_entry",
    "thesis",
    "entry_confirmation",
    "invalidation",
    "risk_plan",
    "learning_plan",
    "evidence_limitations",
    "learning_version",
    "data_confidence",
    "archive_sequence",
    "outcome",
    "pct_gain_loss",
    "realized_pl_dollars",
    "closed_at",
    "last_mark",
    "current_pl_dollars",
    "current_pl_pct",
    "max_favorable_pct",
    "max_adverse_pct",
    "delta_erosion_streak",
    "iv_crush_streak",
    "thesis_invalid_streak",
    "last_signal",
    "last_evaluated_at",
    "discord_thread_id",
    "discord_status",
    "discord_format_version",
    "last_discord_signal",
    "last_discord_pl_pct",
    "last_discord_update_at",
    # SPY Key-Levels/ORB/VWAP strategy only - underlying-price-level stop/
    # target (not a % of option premium) plus which tracked level and DTE
    # tier the trade was built around. Blank for every other play type.
    "underlying_entry_price",
    "underlying_stop_price",
    "underlying_target_price",
    "active_level_name",
    "expiration_tier",
]

CHANNEL_NAMES = {
    "forum": "trade-journal",
    "scanner_feed": "scanner-feed",
    "premarket": "premarket",
    "breaking_alerts": "breaking-alerts",
    "universe_watch": "universe-watch",
    "charts": "charts-and-levels",
    "intelligence": "market-regime",
    "market_pulse": "market-regime",
    "technicals": "charts-and-levels",
    # The market-memory research store's own visualization channel. A
    # separate key from "technicals" on purpose - that one is still
    # routed to #charts-and-levels by local_information_engine and its
    # cards are cleaned up there by intraday_chart_job.
    "spy_technicals": "spy-technicals",
    "options_chain": "scanner-feed",
    "risk_desk": "scanner-controls",
    "news_events": "news-and-events",
    "sec_filings": "news-and-events",
    # Moved off new-positions (owner: "if they are qualified i just want to
    # see the active trades nothing else in here") - qualified-but-not-yet-
    # entered scanner results now share scanner-feed with the rest of the
    # scan-activity content, not the channel meant to show real entries.
    "qualified": "scanner-feed",
    "entry": "new-positions",
    "updates": "held-positions",
    "exit": "held-positions",
    "wins": "wins",
    "losses": "losses",
    "scratches": "losses",
    "expired": "losses",
    "daily_recap": "daily-recap",
    "weekly_report": "weekly-report",
    "monthly_recap": "monthly-dashboard",
    # 1-Minute, 5-Minute, Key-Levels, and Expansion-Level each keep their
    # own logical key, own state tracking, and own search-marker text (see
    # performance_reconciliation.py) - only the REAL channel every key
    # resolves to is shared now, mirroring the ratchet consolidation.
    # Owner: "do the ratchet thing but instead all the other trades
    # tradebot makes... tabs can stay meaningful and not scattered
    # craziness."
    "ticker_results": "ticker-results",
    "learning_results": "learning-results",
    "examples_reviews": "examples-and-reviews",
    "status": "system-health",
    "system_activity": "system-activity",
    "errors": "provider-status",
    "workflow_log": "workflow-log",
    "admin_notes": "scanner-controls",
    "welcome": "welcome",
    "general_chat": "general-chat",
    "strategy_rules": "rules-and-risk",
    "risk_management": "rules-and-risk",
    "server_guide": "how-to-use-tradebot",
}


# One channel per promoted strategy, generated from the registry so the
# routing cannot drift from the strategy list. Both its performance card
# and its results feed go to that strategy's own channel, per the locked
# Phase 7 scope.
try:
    import spy_live_new_strategies as _new_strategy_channels
    CHANNEL_NAMES.update(_new_strategy_channels.channel_names())
except Exception as _exc:   # pragma: no cover - import guard only
    print(f"new-strategy channel names unavailable: {_exc}", file=sys.stderr)

TAG_KEYS = {
    "WATCHING",
    "QUALIFIED",
    "OPEN",
    "HOLDING",
    "TARGET HIT",
    "STOP WARNING",
    "WIN",
    "LOSS",
    "SCRATCH",
    "EXPIRED",
}

# Every signal string any evaluate_open_*_row/exit_signal function can
# return that means "close this position now" - the single source of truth
# every close-triggering call site (main()'s scan loop, and
# local_information_engine.py's real-time stream handler and REST fallback)
# must check against. This exists because each new strategy family has
# historically invented its own close-signal string (SPY_KEY_LEVELS'
# "EXPIRATION CLOSE", SPY_EXPANSION_LEVEL's "EXPANSION EOD CLOSE", the
# ratchet variants' "FLOOR STOP"/"RATCHET EOD CLOSE") and every call site
# had its own separately hand-maintained copy of this set - which silently
# drifted: two of the three call sites never got the newer strings added,
# so a real close signal would show up on the live card but not actually
# close the trade until the next full scan cycle, up to ~15 minutes later.
CLOSING_SIGNALS = {
    "STOP OUT",
    "TAKE PROFIT",
    "BREAKEVEN STOP",
    "EXPIRY CLOSE",
    "EXPIRATION CLOSE",
    "EXPANSION EOD CLOSE",
    "THESIS INVALIDATED",
    "TIME DECAY EXIT",
    "FLOOR STOP",
    "RATCHET EOD CLOSE",
    # spy_0dte_exit_signal's own bare "EOD CLOSE" (both its real 15-minutes-
    # to-close branch and its own error-fallback branch) - the exact bug
    # this set exists to prevent, missed from this set itself: a SPY_0DTE_1M/
    # 5M position that reaches the closing window without hitting a stop/
    # target/floor would show "EOD CLOSE" as last_signal on its live card
    # but never actually get closed by any of the three call sites, since
    # none of them recognized this specific string. Confirmed live: zero
    # occurrences in the trade log so far, meaning every 0DTE trade to date
    # has happened to hit a real stop/target/floor before reaching this
    # branch - not evidence it can't happen, just that it hasn't yet.
    "EOD CLOSE",
}

# SPY_0DTE_1M/5M and SPY_EXPANSION_LEVEL were retired 2026-08-17, so their
# performance_/results_ keys are gone from this list too - a key here with no
# CHANNEL_NAMES route is dead weight even now that discover() tolerates it.
AUTOMATED_CHANNEL_KEYS = [
    "scanner_feed",
    "premarket",
    "breaking_alerts",
    "universe_watch",
    "charts",
    "intelligence",
    "market_pulse",
    "technicals",
    "options_chain",
    "risk_desk",
    "news_events",
    "sec_filings",
    "qualified",
    "entry",
    "updates",
    "exit",
    "wins",
    "losses",
    "scratches",
    "expired",
    "daily_recap",
    "weekly_report",
    "monthly_recap",
    "spy_technicals",
    "ticker_results",
    "learning_results",
    "examples_reviews",
    "status",
    "errors",
    "workflow_log",
]
# Two logical channels per ratchet variant (performance + results) - each
# variant still gets its own logical key, own state tracking, and own
# search-marker text (see performance_reconciliation.py), so its numbers
# can never bleed into another variant's. Owner: "i want all the ratchet
# stratagies in a single catagory instead of 11 different channels ...
# have each thing tracked seperately." Only the REAL channel every
# variant's logical key resolves to changed - all 10 now share one
# dashboard channel and one results channel instead of 10 category/channel
# pairs (see sync_discord_structure.py's RATCHET_CATEGORY_NAME).
for _ratchet_variant in SPY_RATCHET_VARIANTS:
    _ratchet_suffix = _ratchet_variant["play_type"].removeprefix("SPY_RATCHET_").lower()
    CHANNEL_NAMES[f"performance_ratchet_{_ratchet_suffix}"] = "ratchet-dashboard"
    CHANNEL_NAMES[f"results_ratchet_{_ratchet_suffix}"] = "ratchet-results"
    AUTOMATED_CHANNEL_KEYS.append(f"performance_ratchet_{_ratchet_suffix}")
    AUTOMATED_CHANNEL_KEYS.append(f"results_ratchet_{_ratchet_suffix}")
# One more card in the shared dashboard channel: a leaderboard ranking all
# 10 variants against each other by real P&L - owner: "a dashboard so we
# can see top performers." See performance_reconciliation.py's
# format_ratchet_leaderboard.
# All 10 ratchet variants were retired 2026-08-17 and #ratchet-dashboard was
# deleted with them, but this route survived - pointing at a channel that no
# longer exists. A card sent to a dead channel is silently dropped, so it is
# removed rather than left dangling. (Found by checking every route resolves
# to a live channel; the per-variant routes above go empty on their own,
# since they are generated from the now-empty SPY_RATCHET_VARIANTS.)
CHANNEL_NAMES.pop("ratchet_leaderboard", None)
# ratchet_leaderboard retired with the 10 variants - no route left to check.
# Same idea for the other 4 live strategies (1-Minute, 5-Minute,
# Key-Levels, Expansion-Level) - a leaderboard ranking them against each
# other in the shared strategies-dashboard channel. See
# performance_reconciliation.py's format_strategy_leaderboard.
# Moved to PERFORMANCE when #strategies-dashboard was deleted 2026-08-17.
# A cross-strategy ranking is not duplicated by the period recaps - those
# are per-period totals, not a comparison of strategies against each other -
# so it moves rather than being dropped.
CHANNEL_NAMES["strategy_leaderboard"] = "monthly-dashboard"
AUTOMATED_CHANNEL_KEYS.append("strategy_leaderboard")

SYSTEM_CHANNEL_KEYS = {
    "status",
    "errors",
    "workflow_log",
    "admin_notes",
}

MANUAL_CHANNEL_KEYS = [
    "welcome",
    "strategy_rules",
    "risk_management",
    "server_guide",
    "admin_notes",
]

# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def now_ct() -> datetime:
    return datetime.now(MARKET_TZ)


def portable_strftime(value: datetime, format_string: str) -> str:
    """Support GNU's non-padded hour token on Windows as well as Linux."""
    rendered = value.strftime(format_string.replace("%-I", "%I"))
    return re.sub(r"(?<!\d)0(\d)(?=:)", r"\1", rendered)


def as_float(value: Any, default: float | None = None) -> float | None:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def round_or_blank(value: float | None, digits: int = 2) -> str:
    return "" if value is None else str(round(value, digits))



def fmt_money(value: float | None) -> str:
    """Display one-contract and aggregate dollar values as whole dollars."""
    if value is None:
        return "—"
    rounded = int(round(value))
    return f"-${abs(rounded):,}" if rounded < 0 else f"${rounded:,}"


def fmt_option_price(value: float | None, *, approximate: bool = False) -> str:
    """Options premiums and debits/credits are always displayed to two decimals."""
    if value is None:
        return "—"
    prefix = "≈" if approximate else ""
    return f"{prefix}${round(float(value), 2):.2f}"


def fmt_iv(value: float | None) -> str:
    if value is None or value <= 0:
        return "Unavailable"
    return f"{value * 100:.0f}%"


def fmt_oi(value: Any) -> str:
    amount = int(as_float(value, 0.0) or 0)
    return f"{amount:,}" if amount > 0 else "Unavailable"


def fmt_delta(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:+.2f}"



def fmt_pct(value: float | None) -> str:
    return "—" if value is None else f"{value:+.0f}%"

def fmt_strike(value: Any) -> str:
    return f"{float(value):g}"


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=MARKET_TZ)
        return parsed.astimezone(MARKET_TZ)
    except ValueError:
        return None


def normalized_name(value: str) -> str:
    # Remove emoji/punctuation, preserve words and spaces.
    clean = re.sub(r"[^A-Za-z0-9]+", " ", value).strip().upper()
    return re.sub(r"\s+", " ", clean)


def split_chunks(values: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def read_report_state() -> dict[str, Any]:
    default = {
        "messages": {},
        "message_hashes": {},
        "daily_report_date": "",
        "weekly_report_key": "",
        "guide_version": "",
        "routed_closed_trade_ids": [],
    }
    if not REPORT_STATE_PATH.exists():
        return default
    try:
        loaded = json.loads(REPORT_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default
    if not isinstance(loaded, dict):
        return default
    default.update(loaded)
    if not isinstance(default.get("messages"), dict):
        default["messages"] = {}
    if not isinstance(default.get("routed_closed_trade_ids"), list):
        default["routed_closed_trade_ids"] = []
    return default


def write_report_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def market_is_open_now() -> tuple[bool, datetime]:
    now = now_ct()
    if now.weekday() >= 5:
        return False, now
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    return open_time <= now <= close_time, now


def days_to_expiry(expiration: str) -> int:
    return (datetime.strptime(expiration, "%Y-%m-%d").date() - now_ct().date()).days


def option_symbol(ticker: str, expiration: str, call_or_put: str, strike: float) -> str:
    exp = datetime.strptime(expiration, "%Y-%m-%d").strftime("%y%m%d")
    cp = "C" if call_or_put.lower() == "call" else "P"
    strike_code = f"{int(round(float(strike) * 1000)):08d}"
    return f"{ticker.upper()}{exp}{cp}{strike_code}"


def format_spread_strike(sell_strike: float, buy_strike: float) -> str:
    return f"SELL {fmt_strike(sell_strike)} / BUY {fmt_strike(buy_strike)}"


def parse_spread_strikes(value: str) -> tuple[float, float]:
    match = re.search(r"SELL\s*([\d.]+)\s*/\s*BUY\s*([\d.]+)", value, re.IGNORECASE)
    if match:
        return float(match.group(1)), float(match.group(2))
    parts = value.split("/")
    if len(parts) != 2:
        raise ValueError(f"Unrecognized spread strike format: {value!r}")
    return float(parts[0]), float(parts[1])



def parse_entry_price(row: dict[str, str]) -> float:
    direct = as_float(row.get("entry_price"))
    if direct is not None:
        return round(direct, 2)
    raw = (row.get("cost_or_credit") or "").replace("credit", "").strip()
    return round(as_float(raw, 0.0) or 0.0, 2)


def exit_price(row: dict[str, str]) -> float | None:
    """Tracked closing premium/debit, normalized to an option-price cent."""
    stored = as_float(row.get("exit_price"))
    if stored is not None:
        return round(stored, 2)

    if row.get("outcome") not in {"WIN", "LOSS", "SCRATCH"}:
        return None

    entry = parse_entry_price(row)
    realized = as_float(row.get("realized_pl_dollars"))
    if realized is None:
        realized = as_float(row.get("current_pl_dollars"))
    if realized is None:
        pct = as_float(row.get("pct_gain_loss"))
        if pct is None:
            return None
        realized = entry * pct

    if row.get("play_type") == "SPREAD":
        return round(entry - (realized / 100), 2)
    return round(entry + (realized / 100), 2)


def entry_contract_value(row: dict[str, str]) -> float:
    return round(parse_entry_price(row) * 100)


def exit_contract_value(row: dict[str, str]) -> float | None:
    price = exit_price(row)
    return None if price is None else round(price * 100)

def result_is_reconstructed(row: dict[str, str]) -> bool:
    return row.get("result_price_source") == "RECONSTRUCTED"



def realized_pl_dollars(row: dict[str, str]) -> float:
    """One-contract result from cent-normalized entry and exit premiums."""
    entry = parse_entry_price(row)
    closing = exit_price(row)
    if closing is not None:
        if row.get("play_type") == "SPREAD":
            return round((entry - closing) * 100)
        return round((closing - entry) * 100)

    stored = as_float(row.get("realized_pl_dollars"))
    if stored is not None:
        return round(stored)

    current = as_float(row.get("current_pl_dollars"))
    if current is not None and row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}:
        return round(current)

    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    return round(entry * pct)

def result_amount_prefix(row: dict[str, str]) -> str:
    return "≈" if result_is_reconstructed(row) else ""


def result_price_details(row: dict[str, str]) -> tuple[float, float | None, float]:
    return parse_entry_price(row), exit_price(row), realized_pl_dollars(row)


def row_key(row: dict[str, str]) -> tuple[str, str, str, str, str]:
    return (
        row.get("ticker", ""),
        row.get("play_type", ""),
        row.get("call_or_put", ""),
        row.get("strike", ""),
        row.get("expiration", ""),
    )


def trade_sequence(row: dict[str, str]) -> str:
    return str(row.get("archive_sequence") or (row.get("trade_id") or "UNKNOWN").rsplit("-", 1)[-1])


def trade_title(row: dict[str, str]) -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_sequence(row)
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        return (
            f"{ticker} #{sequence} | {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)} "
            f"{kind} CREDIT | {expiration}"
        )

    strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
    return f"{ticker} #{sequence} | BUY {strike} {kind} | {expiration}"



def play_style_key(row: dict[str, str]) -> str:
    play_type = str(row.get("play_type") or "REGULAR").upper()
    kind = str(row.get("call_or_put") or "").lower()
    if play_type == "SPREAD":
        return "bull-put-spread" if kind == "put" else "bear-call-spread"
    prefix = "swing" if play_type == "SWING" else "regular"
    return f"{prefix}-{kind or 'unknown'}"


def learning_channel_reference(channel: str) -> str:
    path = STATE_DIR / "learning-channel-map.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        channel_id = str((payload.get("channels") or {}).get(channel) or "")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        channel_id = ""
    return f"<#{channel_id}>" if channel_id else f"**#{channel}**"


def trade_learning_analysis(row: dict[str, str], *, closed: bool = False) -> str:
    """Apply stored evidence to one trade without inventing unavailable history."""
    style = play_style_key(row)
    regime = str(row.get("market_regime") or "not recorded")
    reason = str(row.get("setup_reason") or "historical setup evidence was not recorded")
    delta = as_float(row.get("delta_at_entry"))
    iv = as_float(row.get("iv_at_entry"))
    width = as_float(row.get("bid_ask_width_at_entry"))
    oi = row.get("open_interest_at_entry") or "not recorded"
    signal = str(row.get("last_signal") or ("OPEN" if not closed else "CLOSED"))
    strategy_lesson = "19-spreads-multi-leg" if "spread" in style else "17-directional-options"
    bias = "bullish" if style in {"regular-call", "swing-call", "bull-put-spread"} else "bearish"
    thesis = str(row.get("thesis") or "").strip() or (
        f"This {style.replace('-', ' ')} expresses a {bias} paper thesis on "
        f"{row.get('ticker') or TICKER}. The stored regime was {regime}; qualification: {reason}"
    )
    confirmation = str(row.get("entry_confirmation") or "").strip() or reason
    invalidation = str(row.get("invalidation") or "").strip() or "Not recorded in the original trade evidence."
    risk_plan = str(row.get("risk_plan") or "").strip() or "Not recorded in the original trade evidence."
    learning_plan = str(row.get("learning_plan") or "").strip() or (
        f"Apply {strategy_lesson}, option liquidity/Greeks, volatility, risk, execution, and journaling lessons."
    )
    limitations = str(row.get("evidence_limitations") or "").strip() or (
        "Indicators or market observations absent from the original trade record are unavailable "
        "and are not reconstructed as entry facts."
    )
    evidence = (
        f"**Delta:** {fmt_delta(delta)} · **IV:** {fmt_iv(iv)} · **OI:** {fmt_oi(oi)} · "
        f"**Bid/ask width:** {fmt_option_price(width)}"
    )
    lines = [
        "### Applied Learning Center Analysis",
        f"**Trade thesis:** {thesis}",
        f"**Entry confirmation:** {confirmation}",
        f"**Invalidation:** {invalidation}",
        f"**Risk plan:** {risk_plan}",
        f"**Learning application:** {learning_plan}",
        f"**Recorded option evidence:** {evidence}",
        f"**Evidence limitation:** {limitations}",
        f"**Learning Center version:** `{row.get('learning_version') or trade_intelligence.learning_version()}`",
        f"**Data confidence:** {row.get('data_confidence') or 'Historical evidence quality not scored'}",
        "**Learning Center path:** "
        + " · ".join(
            learning_channel_reference(channel)
            for channel in (
                "06-charts-price-action",
                "07-technical-analysis",
                "14-option-chain-liquidity",
                "15-option-pricing-greeks",
                "16-volatility",
                strategy_lesson,
                "12-portfolio-risk",
                "20-trade-planning-execution",
            )
        ),
    ]
    if closed:
        outcome = str(row.get("outcome") or "CLOSED")
        lines.extend(
            [
                "### Post-Trade Learning",
                (
                    f"This trade closed **{outcome}** because the recorded lifecycle signal was "
                    f"**{signal}**. Its MFE was **{fmt_pct(as_float(row.get('max_favorable_pct')))}** "
                    f"and MAE was **{fmt_pct(as_float(row.get('max_adverse_pct')))}**. These are "
                    "observed results, not proof that the play style will repeat."
                ),
                "**Review path:** "
                + " · ".join(
                    learning_channel_reference(channel)
                    for channel in ("23-psychology-journaling", "24-backtesting-statistics")
                ),
            ]
        )
    return "\n".join(lines)


def format_expiration(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%m/%d/%y")
    except (TypeError, ValueError):
        return value or "—"



def entry_alert_text(row: dict[str, str], include_link: str = "", summary_only: bool = False) -> str:
    """summary_only trims the card to Position/Entry Plan/Risk (through
    Break-even) - what the shared new-positions channel shows. Market Data,
    Why This Qualified, and the learning-center analysis only appear in the
    full (summary_only=False) version, which is what actually gets posted
    into the trade's own journal thread - per owner direction, that detail
    belongs in the trade's journal, not the shared channel card."""
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_sequence(row)
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry = parse_entry_price(row)
    breakeven = as_float(row.get("breakeven"))
    delta = as_float(row.get("delta_at_entry"))
    theta = as_float(row.get("theta_at_entry"))
    oi = row.get("open_interest_at_entry")
    iv = as_float(row.get("iv_at_entry"))

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{play_type} {kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        stop = round(entry * SPREAD_STOP_MULTIPLE, 2)
        target = round(entry * (1 - SPREAD_TAKE_PROFIT_PCT), 2)
        stop_pl = round((entry - stop) * 100)
        target_pl = round((entry - target) * 100)
        price_line = (
            f"**Entry:** {fmt_option_price(entry)} CR ({fmt_money(entry * 100)})\n"
            f"**Target:** {fmt_option_price(target)} DB ({fmt_money(target_pl)})\n"
            f"**Stop:** {fmt_option_price(stop)} DB ({fmt_money(stop_pl)})"
        )
        risk_line = (
            f"**Max profit:** {fmt_money(as_float(row.get('max_profit')))}\n"
            f"**Max risk:** {fmt_money(as_float(row.get('max_risk')))}\n"
            f"**Break-even:** {fmt_option_price(breakeven)}"
        )
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"{play_type} LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        if is_spy_ratchet_play_type(play_type):
            # No fixed take-profit target for a ratchet variant - the floor
            # keeps ratcheting up with every step instead. Show the base
            # stop (only in force before the first step fires) plus the
            # step size itself, not a Target line.
            variant = SPY_RATCHET_VARIANT_BY_PLAY_TYPE.get(play_type, {})
            step_pct = variant.get("step_pct", 0.0) or 0.0
            stop_pct_signed = variant.get("stop_pct", 0.0) or 0.0
            stop = round(entry * (1 + stop_pct_signed / 100), 2)
            price_line = (
                f"**Entry:** {fmt_option_price(entry)} DB ({fmt_money(entry * 100)})\n"
                f"**Stop (until first lock):** {fmt_option_price(stop)} CR ({fmt_money((stop - entry) * 100)})\n"
                f"**Ratchet floor:** locks in every {step_pct:.0f}% gain, no fixed target"
            )
        else:
            stop_pct = SPY_0DTE_STOP_PCT if is_spy_0dte_play_type(play_type) else SINGLE_STOP_PCT
            target_pct = SPY_0DTE_TARGET_PCT if is_spy_0dte_play_type(play_type) else SINGLE_TAKE_PROFIT_PCT
            stop = round(entry * (1 - stop_pct), 2)
            target = round(entry * (1 + target_pct), 2)
            price_line = (
                f"**Entry:** {fmt_option_price(entry)} DB ({fmt_money(entry * 100)})\n"
                f"**Target:** {fmt_option_price(target)} CR ({fmt_money((target - entry) * 100)})\n"
                f"**Stop:** {fmt_option_price(stop)} CR ({fmt_money((stop - entry) * 100)})"
            )
        risk_line = (
            f"**Max risk:** {fmt_money(as_float(row.get('max_risk')))}\n"
            f"**Break-even:** {fmt_option_price(breakeven)}"
        )

    lines = [
        f"## 🟦 {ticker} #{sequence} · ENTRY · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}",
        "### Entry Plan",
        price_line,
        "### Risk",
        risk_line,
    ]
    if summary_only:
        return "\n".join(lines)
    market_data = (
        f"**Delta:** {fmt_delta(delta)}\n"
        f"**IV:** {fmt_iv(iv)}\n"
        f"**OI:** {fmt_oi(oi)} *(open interest)*\n"
        f"**Volume:** {fmt_oi(row.get('option_volume_at_entry'))}\n"
        f"**Theta:** {'Unavailable' if theta is None else f'{theta:+.3f}/day'}"
    )
    lines.extend([
        "### Market Data",
        market_data,
        "### Why This Qualified",
        (
            f"**Regime:** {row.get('market_regime') or 'CONTROLLED'}\n"
            f"**Market condition:** {row.get('market_condition_at_entry') or 'UNKNOWN'}\n"
            f"**Score:** {row.get('setup_score') or '—'} *(ranking only; not a win probability)*\n"
            f"**Evidence:** {row.get('setup_reason') or 'Conservative directional filters passed'}"
        ),
    ])
    if include_link:
        lines.extend(["### Journal", f"[Open trade journal]({include_link})"])
    lines.append(trade_learning_analysis(row))
    return "\n".join(lines)


def position_update_text(
    row: dict[str, str],
    evaluation: dict[str, Any],
    include_link: str = "",
) -> str:
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_sequence(row)
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    signal = evaluation.get("signal") or row.get("last_signal") or "HOLD"
    entry = parse_entry_price(row)
    mark = as_float(evaluation.get("mark"), as_float(row.get("last_mark"), entry))
    if mark is None:
        mark = entry
    pl_dollars = as_float(evaluation.get("pl_dollars"), as_float(row.get("current_pl_dollars"), 0.0)) or 0.0
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("current_pl_pct"), 0.0)) or 0.0
    mfe = as_float(row.get("max_favorable_pct"), 0.0) or 0.0
    mae = as_float(row.get("max_adverse_pct"), 0.0) or 0.0

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{play_type} {kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        price_labels = (
            f"**Entry credit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})\n"
            f"**Current close debit:** {fmt_option_price(mark)} ({fmt_money(mark * 100)})"
        )
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"{play_type} LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        price_labels = (
            f"**Entry debit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})\n"
            f"**Current exit credit:** {fmt_option_price(mark)} ({fmt_money(mark * 100)})"
        )

    quote_note = evaluation.get("note") or ""
    state_label = "HOLD" if signal == "HOLD" else signal
    lines = [
        f"## 🟨 {ticker} #{sequence} · {state_label} · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}\n**Status:** {state_label}",
        "### Current Value",
        (
            f"{price_labels}\n"
            f"**Open P/L:** {fmt_money(pl_dollars)} ({fmt_pct(pl_pct)})"
        ),
        "### Excursion",
        f"**MFE:** {fmt_pct(mfe)}\n**MAE:** {fmt_pct(mae)}",
        "### Market Data",
        (
            f"**IV:** {fmt_iv(as_float(evaluation.get('iv'), as_float(row.get('iv_at_entry'))))}\n"
            f"**OI:** {fmt_oi(row.get('open_interest_at_entry'))} *(open interest)*\n"
            f"**Last checked:** {portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}"
        ),
    ]
    if quote_note:
        lines.extend(["### Quote Status", f"⚠️ {quote_note}"])
    if include_link:
        lines.extend(["### Journal", f"[Open trade journal]({include_link})"])
    return "\n".join(lines)


def stop_overshoot_target_pct(row: dict[str, str], close_reason: str | None = None) -> float | None:
    """The configured stop/floor target_pct a closed trade should have
    exited at, or None when the trade didn't close via a stop/floor signal
    or is a retired SPREAD row. Extracted so both the "Stop overshoot" card
    line below and a daily rollup (system_digest_job in
    local_information_engine.py) compute this from one place instead of
    two copies drifting apart. close_reason defaults to the row's stored
    last_signal (the only source available for an already-closed historical
    row); close_alert_text passes its own evaluation-preferring local
    instead, since a fresh live evaluation can be more current than what's
    been persisted yet."""
    close_reason = str(close_reason if close_reason is not None else (row.get("last_signal") or ""))
    play_type = str(row.get("play_type") or "")
    if close_reason not in ("STOP OUT", "BREAKEVEN STOP", "FLOOR STOP") or play_type == "SPREAD":
        return None
    if is_spy_0dte_play_type(play_type):
        return -(SPY_0DTE_STOP_PCT * 100) if close_reason == "STOP OUT" else SPY_0DTE_FLOOR_PCT
    if is_spy_ratchet_play_type(play_type):
        variant = SPY_RATCHET_VARIANT_BY_PLAY_TYPE.get(play_type, {})
        step_pct = variant.get("step_pct", 0.0) or 0.0
        stop_pct = variant.get("stop_pct", 0.0) or 0.0
        if close_reason == "STOP OUT":
            return stop_pct
        peak_pct = as_float(row.get("max_favorable_pct"), 0.0) or 0.0
        return (peak_pct // step_pct) * step_pct if step_pct else 0.0
    configured_stop = SWING_STOP_PCT if play_type == "SWING" else SINGLE_STOP_PCT
    return -(configured_stop * 100) if close_reason == "STOP OUT" else 0.0


def compute_stop_overshoot(row: dict[str, str]) -> float | None:
    """How far a closed stop/floor trade's realized pl_pct slipped past its
    configured target_pct. None when not applicable, or when the stop held
    (overshoot >= -0.5)."""
    target_pct = stop_overshoot_target_pct(row)
    if target_pct is None:
        return None
    pl_pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    overshoot = pl_pct - target_pct
    return overshoot if overshoot < -0.5 else None


def close_alert_text(
    row: dict[str, str], evaluation: dict[str, Any], include_link: str = "", summary_only: bool = False
) -> str:
    """summary_only trims the card to Position/Entry and Exit/Result/Timing
    (plus the journal link, if any) - what #wins/#losses/#scratches/#expired
    show. The full learning-analysis section (owner: "we have a journal for
    all of that") only appears in the full (summary_only=False) version,
    which is what actually gets posted into the trade's own journal thread -
    same split as entry_alert_text's summary_only."""
    outcome = row.get("outcome", "CLOSED")
    icon = {"WIN": "🟩", "LOSS": "🟥", "SCRATCH": "⬜"}.get(outcome, "📕")
    ticker = (row.get("ticker") or TICKER).upper()
    trade_id = row.get("trade_id") or f"{ticker}-UNKNOWN"
    sequence = trade_sequence(row)
    play_type = row.get("play_type", "PLAY").upper()
    kind = row.get("call_or_put", "").upper()
    expiration = format_expiration(row.get("expiration", ""))
    entry, closing, stored_pl = result_price_details(row)
    pl_dollars = round(as_float(evaluation.get("pl_dollars"), stored_pl) or 0.0)
    pl_pct = as_float(evaluation.get("pl_pct"), as_float(row.get("pct_gain_loss"), 0.0)) or 0.0
    close_reason = evaluation.get("signal") or row.get("last_signal") or "CLOSED"
    approx = result_is_reconstructed(row)

    if play_type == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        strategy = f"{play_type} {kind} CREDIT SPREAD"
        setup = (
            f"🔴 SELL 1 {ticker} {fmt_strike(sell_strike)} {kind}\n"
            f"🟢 BUY 1 {ticker} {fmt_strike(buy_strike)} {kind}"
        )
        entry_line = f"**Entry credit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})"
        exit_line = f"**Exit debit:** {fmt_option_price(closing, approximate=approx)} ({'≈' if approx else ''}{fmt_money(exit_contract_value(row))})"
    else:
        strike = fmt_strike(as_float(row.get("strike"), 0) or 0)
        strategy = f"{play_type} LONG {kind}"
        setup = f"🟢 BUY 1 {ticker} {strike} {kind}"
        entry_line = f"**Entry debit:** {fmt_option_price(entry)} ({fmt_money(entry * 100)})"
        exit_line = f"**Exit credit:** {fmt_option_price(closing, approximate=approx)} ({'≈' if approx else ''}{fmt_money(exit_contract_value(row))})"

    closed_at = parse_iso(row.get("closed_at"))
    closed_text = portable_strftime(closed_at, "%m/%d/%y %-I:%M %p CT") if closed_at else "—"
    approx_prefix = "≈" if approx else ""
    result_lines = [
        f"**Realized P/L:** {approx_prefix}{fmt_money(pl_dollars)}\n"
        f"**Return:** {fmt_pct(pl_pct)}\n"
        f"**Close reason:** {close_reason}\n"
        f"**MFE:** {fmt_pct(as_float(row.get('max_favorable_pct'), 0.0))}\n"
        f"**MAE:** {fmt_pct(as_float(row.get('max_adverse_pct'), 0.0))}"
    ]
    # Make stop slippage visible directly on the card instead of something
    # that has to be asked about after the fact: a stop can only react to
    # what it last observed, so a gap between checks (or a fast-moving
    # illiquid contract) can let the realized loss run past the configured
    # threshold before the exit ever fires. Showing the overshoot plainly
    # here answers "did the stop actually hold" at a glance, every time.
    target_pct = stop_overshoot_target_pct(row, close_reason)
    if target_pct is not None:
        overshoot = pl_pct - target_pct
        if overshoot < -0.5:
            result_lines.append(
                f"**Stop overshoot:** target {fmt_pct(target_pct)}, actual "
                f"{fmt_pct(pl_pct)} — slipped {abs(overshoot):.0f} points past "
                f"the stop before this could react"
            )
    lines = [
        f"## {icon} {ticker} #{sequence} · {outcome} · {strategy}",
        "### Position",
        f"{setup}\n**Expiration:** {expiration}",
        "### Entry and Exit",
        f"{entry_line}\n{exit_line}",
        "### Result",
        "\n".join(result_lines),
        "### Timing",
        f"**Closed:** {closed_text}",
    ]
    if include_link:
        lines.extend(["### Journal", f"[Open completed trade journal]({include_link})"])
    if summary_only:
        return "\n".join(lines)
    lines.append(trade_learning_analysis(row, closed=True))
    return "\n".join(lines)


def candidate_brief(candidate: dict[str, Any]) -> str:
    kind = str(candidate.get("call_or_put", "")).upper()
    play_type = str(candidate.get("play_type", "PLAY")).upper()
    expiration = format_expiration(str(candidate.get("expiration", "")))
    entry = as_float(candidate.get("entry_price"), 0.0) or 0.0
    score = as_float(candidate.get("score"), 0.0) or 0.0
    iv = as_float(candidate.get("iv"))
    oi = candidate.get("open_interest")
    if play_type == "SPREAD":
        setup = f"{kind} CREDIT {candidate.get('strike', '—')}"
        price = f"{fmt_option_price(entry)} CR"
    else:
        setup = f"{play_type} {kind} {candidate.get('strike', '—')}"
        price = f"{fmt_option_price(entry)} DB"
    return (
        f"• **{setup}** · EXP {expiration} · {price} · "
        f"IV {fmt_iv(iv)} · OI {fmt_oi(oi)} · score {score:.0f}"
    )

def thread_link(thread_id: str) -> str:
    if not thread_id or not DISCORD_GUILD_ID:
        return ""
    return f"https://discord.com/channels/{DISCORD_GUILD_ID}/{thread_id}"

# ---------------------------------------------------------------------------
# Tradier market data
# ---------------------------------------------------------------------------


class TradierError(RuntimeError):
    pass


def tradier_get(path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if not TRADIER_TOKEN:
        raise TradierError("TRADIER_TOKEN is not configured")
    try:
        response = SESSION.get(
            f"{TRADIER_BASE_URL}{path}",
            params=params or {},
            headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
            timeout=25,
        )
    except requests.RequestException as exc:
        raise TradierError(f"Tradier request failed: {exc}") from exc
    if not response.ok:
        body = response.text[:500].replace(TRADIER_TOKEN, "[REDACTED]")
        raise TradierError(f"Tradier HTTP {response.status_code} for {path}: {body}")
    try:
        return response.json()
    except ValueError as exc:
        raise TradierError(f"Tradier returned invalid JSON for {path}") from exc


def get_quotes(symbols: list[str], include_greeks: bool = True) -> dict[str, dict[str, Any]]:
    unique = list(dict.fromkeys(symbol for symbol in symbols if symbol))
    quote_map: dict[str, dict[str, Any]] = {}
    for chunk in split_chunks(unique, 50):
        data = tradier_get(
            "/markets/quotes",
            {"symbols": ",".join(chunk), "greeks": str(include_greeks).lower()},
        )
        quotes = data.get("quotes", {}).get("quote")
        if not quotes:
            continue
        if isinstance(quotes, dict):
            quotes = [quotes]
        for quote in quotes:
            symbol = quote.get("symbol")
            if symbol:
                quote_map[symbol] = quote
    return quote_map


def get_quote(symbol: str) -> dict[str, Any] | None:
    return get_quotes([symbol], include_greeks=False).get(symbol)


EARNINGS_BLACKOUT_DAYS = int(os.environ.get(
    "EARNINGS_BLACKOUT_DAYS", configured("earnings_blackout_days", 7)
))
_EARNINGS_CACHE: dict[str, tuple[float, int | None]] = {}

# Well-established, close to universal practice, not a strategy opinion:
# the opening minutes carry elevated volatility and wide spreads as the
# market digests overnight news, and the midday window sees materially
# lower participation - both distort entries in ways that have nothing to
# do with the trader's actual thesis. Times are minutes-from-open /
# minutes-from-close and a CT clock window, matching how this file already
# tracks market hours.
OPENING_RANGE_EXCLUSION_MINUTES = int(os.environ.get(
    "OPENING_RANGE_EXCLUSION_MINUTES", configured("opening_range_exclusion_minutes", 15)
))
MIDDAY_LULL_START_CT = tuple(
    int(part) for part in os.environ.get(
        "MIDDAY_LULL_START_CT", configured("midday_lull_start_ct", "10:30")
    ).split(":")
)
MIDDAY_LULL_END_CT = tuple(
    int(part) for part in os.environ.get(
        "MIDDAY_LULL_END_CT", configured("midday_lull_end_ct", "12:00")
    ).split(":")
)


def entry_window_blocked(now: datetime) -> str:
    """Returns a reason string if now falls in an excluded entry window,
    or an empty string if entries are allowed. Only gates NEW entries -
    exits, position management, and everything else run on their own
    schedule regardless of this. Computes market-open status directly from
    the passed-in now rather than calling market_is_open_now(), which reads
    the real wall clock regardless of what's passed to it - this function
    needs to be evaluable for any given moment, not just the actual
    current one."""
    if now.weekday() >= 5:
        return ""  # the normal closed-market handling already covers this
    open_time = now.replace(hour=MARKET_OPEN[0], minute=MARKET_OPEN[1], second=0, microsecond=0)
    close_time = now.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    if not (open_time <= now <= close_time):
        return ""
    minutes_since_open = (now - open_time).total_seconds() / 60
    if 0 <= minutes_since_open < OPENING_RANGE_EXCLUSION_MINUTES:
        return (
            f"within the first {OPENING_RANGE_EXCLUSION_MINUTES} minutes of the "
            "session - still settling from overnight news, not a clean read yet"
        )
    # Midday lull exclusion removed 2026-08-13 (owner: "midday spy is not
    # slow by any means... how do we test strategies if they don't fire
    # off?") - real cost was concrete, not theoretical: a real, correctly
    # parsed TradingView alert landed inside this window and was lost,
    # since by the time the window cleared the alert had already gone
    # stale (SPY_0DTE_1M_TRADINGVIEW_MAX_AGE_SECONDS). TradingView alerts
    # are already rare (roughly 1-2/day observed); losing one to this
    # window is a real cost these strategies can't afford while they're
    # still building up real trade history to learn from.
    # MIDDAY_LULL_START_CT/MIDDAY_LULL_END_CT are kept (unused) rather
    # than deleted in case this needs to come back for a specific
    # strategy later - nothing currently reads them.
    return ""


def days_until_earnings(ticker: str) -> int | None:
    """Days until this ticker's next known earnings date, or None if that
    can't be determined right now - a missing answer must never be treated
    as "no earnings coming," since this uses Tradier's beta fundamentals
    endpoint, which is less stable and less documented than the rest of
    this file's Tradier calls. Every failure mode here fails open (returns
    None, meaning the earnings gate below has nothing to block on) rather
    than fail closed, so a broken or reshaped response can never silently
    stop every trade instead of just this one safety check."""
    ticker = ticker.strip().upper()
    cached = _EARNINGS_CACHE.get(ticker)
    now = time.monotonic()
    if cached and now - cached[0] < 43200:  # 12h - a date this far out barely moves
        return cached[1]
    result: int | None = None
    try:
        beta_base = TRADIER_BASE_URL.rsplit("/", 1)[0] + "/beta"
        response = SESSION.get(
            f"{beta_base}/markets/fundamentals/calendars",
            params={"symbols": ticker},
            headers={"Authorization": f"Bearer {TRADIER_TOKEN}", "Accept": "application/json"},
            timeout=25,
        )
        if response.ok:
            payload = response.json()
            entries = payload if isinstance(payload, list) else [payload]
            candidate_dates: list[date] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                results = entry.get("results") or entry.get("tables") or [entry]
                for item in results if isinstance(results, list) else [results]:
                    if not isinstance(item, dict):
                        continue
                    for key in ("estimated_next_date", "next_earnings_date", "date", "event_date"):
                        raw = item.get(key)
                        if not raw:
                            continue
                        try:
                            candidate_dates.append(datetime.strptime(str(raw)[:10], "%Y-%m-%d").date())
                        except ValueError:
                            continue
            future = [d for d in candidate_dates if d >= now_ct().date()]
            if future:
                result = (min(future) - now_ct().date()).days
    except (requests.RequestException, ValueError, KeyError, TypeError):
        result = None
    _EARNINGS_CACHE[ticker] = (now, result)
    return result


def get_expirations(symbol: str) -> list[str]:
    data = tradier_get("/markets/options/expirations", {"symbol": symbol, "includeAllRoots": "true"})
    values = data.get("expirations", {}).get("date")
    if values is None:
        return []
    return [values] if isinstance(values, str) else list(values)


def get_strikes(symbol: str, expiration: str) -> list[float]:
    data = tradier_get("/markets/options/strikes", {"symbol": symbol, "expiration": expiration})
    values = data.get("strikes", {}).get("strike")
    if values is None:
        return []
    if isinstance(values, (int, float)):
        return [float(values)]
    return [float(value) for value in values]


def get_chain(symbol: str, expiration: str) -> list[dict[str, Any]]:
    data = tradier_get(
        "/markets/options/chains",
        {"symbol": symbol, "expiration": expiration, "greeks": "true"},
    )
    values = data.get("options", {}).get("option")
    if values is None:
        return []
    return [values] if isinstance(values, dict) else list(values)


def get_daily_history(symbol: str, days: int = 90) -> list[dict[str, Any]]:
    end = now_ct().date()
    start = end - timedelta(days=days)
    data = tradier_get(
        "/markets/history",
        {
            "symbol": symbol,
            "interval": "daily",
            "start": start.isoformat(),
            "end": end.isoformat(),
        },
    )
    history = data.get("history") or {}
    values = history.get("day") if isinstance(history, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def _et_window_str(day: date, hour: int, minute: int) -> str:
    """Convert a CT wall-clock moment on `day` to the ET-labeled string
    Tradier's timesales endpoint actually expects (see TRADIER_TIMESALES_TZ
    above)."""
    ct_dt = datetime.combine(day, dt_time(hour, minute), tzinfo=MARKET_TZ)
    et_dt = ct_dt.astimezone(TRADIER_TIMESALES_TZ)
    return et_dt.strftime("%Y-%m-%d %H:%M")


def get_intraday_history(
    symbol: str,
    interval: str = "5min",
) -> list[dict[str, Any]]:
    """Return today's intraday bars when Tradier supplies time-and-sales data."""
    today = now_ct().date()
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": _et_window_str(today, 8, 30),
            "end": _et_window_str(today, 15, 0),
            "session_filter": "open",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def get_premarket_history(symbol: str, interval: str = "5min") -> list[dict[str, Any]]:
    """Return today's premarket bars (3:00-8:30 CT / 4:00-9:30 ET). Separate
    from get_intraday_history because that function is hardcoded to
    session_filter=open starting at the regular 8:30 CT bell - premarket
    needs session_filter=all and an earlier start, which would change
    behavior for every existing caller if bolted onto the same function."""
    today = now_ct().date()
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": _et_window_str(today, 3, 0),
            "end": _et_window_str(today, 8, 30),
            "session_filter": "all",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def get_recent_intraday_history(
    symbol: str, interval: str, calendar_days: int
) -> list[dict[str, Any]]:
    """Multi-day intraday bars, not just today - get_intraday_history is
    hardcoded to a single day (today), which is enough for opening-range
    strategies but not for indicators needing real history (a 200-period
    EMA on 15-minute bars needs many trading days of bars). Tradier's
    timesales endpoint accepts a real multi-day start/end range in one
    call - confirmed live rather than assumed - so this is one request,
    not a day-by-day loop."""
    end = now_ct().date()
    start = end - timedelta(days=calendar_days)
    data = tradier_get(
        "/markets/timesales",
        {
            "symbol": symbol,
            "interval": interval,
            "start": _et_window_str(start, 8, 30),
            "end": _et_window_str(end, 15, 0),
            "session_filter": "open",
        },
    )
    series = data.get("series") or {}
    values = series.get("data") if isinstance(series, dict) else None
    if not values:
        return []
    return [values] if isinstance(values, dict) else list(values)


def simple_moving_average(values: list[float], period: int) -> float | None:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


def exponential_moving_average_series(values: list[float], period: int) -> list[float | None]:
    """Generic EMA - one value per input point, None until enough data has
    accumulated to seed the average. Seeded with a simple average of the
    first `period` values (standard EMA seeding), smoothed forward from
    there with the standard 2/(period+1) multiplier. Lives alongside
    simple_moving_average/relative_strength_index as shared math with no
    strategy identity - a full series (not just the latest value) is what a
    MACD histogram's signal line actually needs, since that's itself an EMA
    of the MACD line's own history, not just its current point."""
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    series: list[float | None] = [None] * (period - 1)
    seed = sum(values[:period]) / period
    series.append(seed)
    previous = seed
    for value in values[period:]:
        current = (value - previous) * multiplier + previous
        series.append(current)
        previous = current
    return series


def exponential_moving_average(values: list[float], period: int) -> float | None:
    series = exponential_moving_average_series(values, period)
    return series[-1] if series else None


def relative_strength_index(values: list[float], period: int = 14) -> float | None:
    if len(values) <= period:
        return None
    changes = [current - previous for previous, current in zip(values[-period - 1:-1], values[-period:])]
    gains = sum(max(change, 0) for change in changes) / period
    losses = sum(max(-change, 0) for change in changes) / period
    if losses == 0:
        return 100.0
    return 100 - (100 / (1 + gains / losses))


def average_true_range(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> float | None:
    """Wilder's ATR - true range is the largest of (high-low), (high-prior
    close), (prior close-low), which matters specifically because a gap
    (SPY opening well above/below yesterday's close) would otherwise
    understate that bar's real range using high-low alone. Needs one
    extra prior close to seed the first true-range value, so requires
    period+1 bars, not just period. Lives alongside simple_moving_average/
    exponential_moving_average/relative_strength_index as shared math
    with no strategy identity."""
    if len(closes) < period + 1 or len(highs) != len(closes) or len(lows) != len(closes):
        return None
    true_ranges = []
    for i in range(1, len(closes)):
        true_ranges.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        ))
    if len(true_ranges) < period:
        return None
    return sum(true_ranges[-period:]) / period


def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return variance ** 0.5


def bollinger_bands(
    closes: list[float], period: int = 20, num_std: float = 2.0
) -> tuple[float | None, float | None, float | None]:
    """Returns (upper, mid, lower) - mid is the plain SMA, upper/lower are
    mid +/- num_std standard deviations of the SAME lookback window (not
    the whole history), the standard definition."""
    if len(closes) < period:
        return None, None, None
    window = closes[-period:]
    mid = sum(window) / period
    deviation = standard_deviation(window)
    if deviation is None:
        return None, mid, None
    return mid + num_std * deviation, mid, mid - num_std * deviation


def directional_market_context(
    history: list[dict[str, Any]],
    spot_price: float,
    intraday: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    volumes = [value for day in history if (value := as_float(day.get("volume"))) is not None]
    sma20 = simple_moving_average(closes, 20)
    sma50 = simple_moving_average(closes, 50)
    rsi14 = relative_strength_index(closes)
    average_volume20 = simple_moving_average(volumes, 20)
    latest_volume = volumes[-1] if volumes else None
    volume_ratio = (
        latest_volume / average_volume20
        if latest_volume is not None and average_volume20 and average_volume20 > 0
        else None
    )
    intraday = intraday or []
    intraday_closes = [
        value
        for bar in intraday
        if (value := as_float(bar.get("close") or bar.get("price"))) is not None
    ]
    intraday_volumes = [
        as_float(bar.get("volume"), 0.0) or 0.0
        for bar in intraday
        if as_float(bar.get("close") or bar.get("price")) is not None
    ]
    intraday_open = intraday_closes[0] if intraday_closes else None
    intraday_change_pct = (
        ((spot_price / intraday_open) - 1) * 100
        if intraday_open and intraday_open > 0
        else None
    )
    intraday_vwap = None
    if intraday_closes and sum(intraday_volumes) > 0:
        intraday_vwap = sum(
            price * volume
            for price, volume in zip(intraday_closes, intraday_volumes)
        ) / sum(intraday_volumes)
    intraday_rsi = relative_strength_index(intraday_closes, 9)
    fast_average = simple_moving_average(intraday_closes, 5)
    slow_average = simple_moving_average(intraday_closes, 20)
    slope_pct = (
        ((intraday_closes[-1] / intraday_closes[-4]) - 1) * 100
        if len(intraday_closes) >= 4 and intraday_closes[-4] > 0
        else None
    )

    reasons: list[str] = []
    failures: list[str] = []
    regime = "NO TRADE"
    if sma20 is None or sma50 is None or rsi14 is None:
        failures.append("insufficient daily history")
    else:
        extension = (spot_price / sma20) - 1
        score = 0
        spot_vs_sma20 = (spot_price / sma20) - 1
        sma_trend_pct = (sma20 / sma50) - 1
        if spot_vs_sma20 >= 0.0025:
            score += 1
            reasons.append("price is above its 20-day average")
        elif spot_vs_sma20 <= -0.0025:
            score -= 1
            reasons.append("price is below its 20-day average")
        if sma_trend_pct >= 0.002:
            score += 1
            reasons.append("20-day trend is above the 50-day trend")
        elif sma_trend_pct <= -0.002:
            score -= 1
            reasons.append("20-day trend is below the 50-day trend")
        if rsi14 >= 55:
            score += 1
        elif rsi14 <= 45:
            score -= 1

        if intraday_change_pct is not None:
            if intraday_change_pct >= 0.35:
                score += 2
                reasons.append(f"intraday move is bullish ({intraday_change_pct:+.1f}%)")
            elif intraday_change_pct <= -0.35:
                score -= 2
                reasons.append(f"intraday move is bearish ({intraday_change_pct:+.1f}%)")
        if intraday_vwap:
            vwap_distance_pct = ((spot_price / intraday_vwap) - 1) * 100
            if vwap_distance_pct >= 0.15:
                score += 1
                reasons.append("price is holding above intraday VWAP")
            elif vwap_distance_pct <= -0.15:
                score -= 1
                reasons.append("price is holding below intraday VWAP")
        if fast_average is not None and slow_average is not None:
            momentum_gap_pct = ((fast_average / slow_average) - 1) * 100
            if momentum_gap_pct >= 0.10:
                score += 1
                reasons.append("5-bar momentum is above the 20-bar trend")
            elif momentum_gap_pct <= -0.10:
                score -= 1
                reasons.append("5-bar momentum is below the 20-bar trend")
        if intraday_rsi is not None:
            if intraday_rsi >= 60:
                score += 1
            elif intraday_rsi <= 40:
                score -= 1
        if slope_pct is not None:
            if slope_pct >= 0.35:
                score += 1
                reasons.append("recent 15-minute price slope is rising")
            elif slope_pct <= -0.35:
                score -= 1
                reasons.append("recent 15-minute price slope is falling")

        if score >= 2:
            regime = "BULLISH / CONTROLLED"
        elif score <= -2:
            regime = "BEARISH / CONTROLLED"
        elif intraday_closes:
            regime = "NEUTRAL / RANGE"
            reasons.append("combined daily and intraday evidence is balanced")
        else:
            failures.append(
                "intraday confirmation is unavailable and daily evidence is mixed"
            )
        if abs(extension) > MAX_EXTENSION_ABOVE_SMA20_PCT:
            reasons.append(
                f"price is extended {extension * 100:+.1f}% from the 20-day average; "
                "contract risk filters still apply"
            )
    return {
        "qualified": not failures,
        "sma20": sma20,
        "sma50": sma50,
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "intraday_change_pct": intraday_change_pct,
        "intraday_vwap": intraday_vwap,
        "intraday_rsi": intraday_rsi,
        "intraday_fast_average": fast_average,
        "intraday_slow_average": slow_average,
        "intraday_slope_pct": slope_pct,
        "evidence_score": score if sma20 is not None and sma50 is not None and rsi14 is not None else 0,
        "regime": regime,
        "reason": "; ".join(reasons) if reasons else "No controlled directional setup",
        "failures": failures,
    }


# Owner ask, sourced from a Reddit suggestion: track performance across
# market conditions, not just per-strategy. Distinct from market_regime
# (each strategy's own directional call) - this is one universal tag
# computed from SPY's own daily price action, applied uniformly to every
# trade regardless of which strategy opened it, so results are genuinely
# comparable across strategies ("how does the whole system do on choppy
# vs trending days"), not just within one.
MARKET_CONDITION_TREND_EFFICIENCY = float(os.environ.get(
    "MARKET_CONDITION_TREND_EFFICIENCY", configured("market_condition_trend_efficiency", 0.6)
))
MARKET_CONDITION_VOL_HIGH_RATIO = float(os.environ.get(
    "MARKET_CONDITION_VOL_HIGH_RATIO", configured("market_condition_vol_high_ratio", 1.3)
))
MARKET_CONDITION_VOL_LOW_RATIO = float(os.environ.get(
    "MARKET_CONDITION_VOL_LOW_RATIO", configured("market_condition_vol_low_ratio", 0.7)
))
MARKET_CONDITION_VOL_LOOKBACK_DAYS = int(os.environ.get(
    "MARKET_CONDITION_VOL_LOOKBACK_DAYS", configured("market_condition_vol_lookback_days", 20)
))


def classify_market_condition(history: list[dict[str, Any]]) -> dict[str, Any]:
    """Classifies today's trading session along two independent axes, using
    only the daily bars already fetched for the market chart - no extra API
    calls. Trend: how much of today's high/low range was covered as a net
    directional move (a big one-way day vs. a round trip). Volatility:
    today's range against the trailing MARKET_CONDITION_VOL_LOOKBACK_DAYS
    average range. Returns "UNKNOWN" on both axes when there isn't enough
    history to compute a trailing baseline or today's bar isn't available
    yet - never guesses."""
    unknown = {"trend": "UNKNOWN", "volatility": "UNKNOWN", "label": "UNKNOWN"}
    if len(history) < MARKET_CONDITION_VOL_LOOKBACK_DAYS + 1:
        return unknown
    today = history[-1]
    open_ = as_float(today.get("open"))
    close = as_float(today.get("close"))
    high = as_float(today.get("high"))
    low = as_float(today.get("low"))
    if None in (open_, close, high, low):
        return unknown
    day_range = high - low
    if day_range <= 0:
        return unknown

    net_move = close - open_
    efficiency = abs(net_move) / day_range
    if efficiency >= MARKET_CONDITION_TREND_EFFICIENCY:
        trend = "TRENDING_UP" if net_move > 0 else "TRENDING_DOWN"
    else:
        trend = "CHOPPY"

    prior_ranges = [
        prior_high - prior_low
        for day in history[-(MARKET_CONDITION_VOL_LOOKBACK_DAYS + 1):-1]
        if (prior_high := as_float(day.get("high"))) is not None
        and (prior_low := as_float(day.get("low"))) is not None
        and prior_high > prior_low
    ]
    average_range = (sum(prior_ranges) / len(prior_ranges)) if prior_ranges else None
    if not average_range:
        return unknown
    ratio = day_range / average_range
    if ratio >= MARKET_CONDITION_VOL_HIGH_RATIO:
        volatility = "HIGH"
    elif ratio <= MARKET_CONDITION_VOL_LOW_RATIO:
        volatility = "LOW"
    else:
        volatility = "NORMAL"

    return {
        "trend": trend,
        "volatility": volatility,
        "label": f"{trend} / {volatility} VOL",
    }



def spy_0dte_opening_range_signal(
    intraday: list[dict[str, Any]] | None, bar_minutes: int = 5
) -> dict[str, Any]:
    """Standalone SPY 0DTE entry signal - a classic, real, independently
    documented day-trading pattern (opening-range breakout), not a
    variant of regular/swing's momentum models. Waits for the first
    SPY_0DTE_OPENING_RANGE_MINUTES of the session to establish a high/low,
    then reads where price is trading RIGHT NOW relative to that range -
    the most recent bar, not the first bar that ever crossed it.

    That distinction is the fix for a real, severe bug: this used to
    scan forward from the opening range and lock onto the FIRST bar that
    broke out, then report that same direction for the rest of the
    session no matter what price did afterward. Confirmed live
    2026-08-14: SPY poked briefly above its opening range just after
    9:30am, then reversed into a real bearish trend, falling well below
    even the opening range LOW by 11am - yet the signal kept reporting
    "BULLISH... broke above... at $778.73" all morning, because that
    early, long-since-reversed poke was still the first bar found. Five
    straight CALL entries opened into that stale bullish read and
    stopped out. Reading the latest bar instead means a real reversal
    back through the range (or through the opposite side) is reflected
    immediately, the next time this gets called - which is every scan
    cycle, so there is no cost to re-checking instead of caching a
    stale first-breakout direction.

    bar_minutes is the interval of the intraday bars passed in (default 5,
    matching the original single-strategy behavior). This function is now
    shared by every SPY_0DTE-family live strategy - SPY_0DTE_5M with
    5-minute bars, SPY_0DTE_1M and all 10 SPY_RATCHET_* variants with
    1-minute bars - so the number of bars needed to cover the same
    opening-range window has to scale with whatever interval the caller
    actually fetched, not stay hardcoded to 5-minute math for all of
    them."""
    intraday = intraday or []
    bars_needed = max(SPY_0DTE_OPENING_RANGE_MINUTES // bar_minutes, 1)
    if len(intraday) <= bars_needed:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": "opening range not yet established",
            "failures": ["fewer than the opening-range window of bars available"],
        }

    opening_range = intraday[:bars_needed]
    highs = [value for bar in opening_range if (value := as_float(bar.get("high"))) is not None]
    lows = [value for bar in opening_range if (value := as_float(bar.get("low"))) is not None]
    if not highs or not lows:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": "opening range bars missing high/low data",
            "failures": ["opening range bars missing high/low data"],
        }
    range_high, range_low = max(highs), min(lows)

    latest_bar = intraday[-1]
    price = as_float(latest_bar.get("close") or latest_bar.get("price"))
    if price is None:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": "latest bar missing a usable price",
            "failures": ["latest bar missing a usable price"],
        }
    if range_low <= price <= range_high:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": f"still inside the opening range (${range_low:.2f}-${range_high:.2f})",
            "failures": ["no breakout of the opening range yet"],
        }

    regime = "BULLISH / CONTROLLED" if price > range_high else "BEARISH / CONTROLLED"
    direction = "above" if price > range_high else "below"
    return {
        "qualified": True,
        "regime": regime,
        "breakout_price": price,
        "range_high": range_high,
        "range_low": range_low,
        "reason": (
            f"trading {direction} the opening range (${range_low:.2f}-${range_high:.2f}), now ${price:.2f}"
        ),
        "failures": [],
    }


SPY_0DTE_TRADINGVIEW_BULLISH_WORDS = ("buy", "long", "call", "bull")
SPY_0DTE_TRADINGVIEW_BEARISH_WORDS = ("sell", "short", "put", "bear")


def spy_0dte_tradingview_direction(event: dict[str, Any]) -> str | None:
    """Parse a raw TradingView provider_events row into BULLISH/BEARISH,
    or None if the alert doesn't say. Checks the event_type column first
    (what the /tradingview webhook extracted from payload["event"]/
    ["action"]), then falls back to scanning common payload fields
    directly, since alert message conventions vary per Pine script."""
    haystacks: list[str] = [str(event.get("event_type") or "")]
    payload = event.get("payload")
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except (TypeError, ValueError, json.JSONDecodeError):
            payload = {}
    if isinstance(payload, dict):
        for key in ("action", "event", "side", "direction", "signal", "strategy_action", "message"):
            value = payload.get(key)
            if value:
                haystacks.append(str(value))
    text = " ".join(haystacks).casefold()
    is_bullish = any(word in text for word in SPY_0DTE_TRADINGVIEW_BULLISH_WORDS)
    is_bearish = any(word in text for word in SPY_0DTE_TRADINGVIEW_BEARISH_WORDS)
    if is_bullish and not is_bearish:
        return "BULLISH"
    if is_bearish and not is_bullish:
        return "BEARISH"
    return None


def _tradingview_event_already_consumed(play_type: str, event_id: int) -> bool:
    try:
        stored = json.loads(SPY_TRADINGVIEW_CONSUMED_EVENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False
    if not isinstance(stored, dict):
        return False
    return int((stored.get(play_type) or {}).get("event_id", -1)) == event_id


def _mark_tradingview_event_if_opened(candidate: dict[str, Any]) -> None:
    """Called from main()'s open loop for every candidate that just
    became a real row - the only correct moment to burn a TradingView
    alert for that play_type, so a candidate that scanned OK but got
    filtered out later (exposure cap, entry window, dedup) leaves the
    alert available for a later, still-fresh scan cycle to retry."""
    event_id = candidate.get("tradingview_event_id")
    if event_id is not None:
        _tradingview_event_mark_consumed(candidate["play_type"], int(event_id))


def _tradingview_event_mark_consumed(play_type: str, event_id: int) -> None:
    try:
        stored = json.loads(SPY_TRADINGVIEW_CONSUMED_EVENT_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        stored = {}
    if not isinstance(stored, dict):
        stored = {}
    stored[play_type] = {
        "event_id": event_id,
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    try:
        SPY_TRADINGVIEW_CONSUMED_EVENT_PATH.write_text(json.dumps(stored), encoding="utf-8")
    except OSError:
        pass


def spy_0dte_tradingview_signal(
    symbol: str = SPY_0DTE_TICKER, *, play_type: str = "SPY_0DTE_1M"
) -> dict[str, Any]:
    """Live TradingView-alert entry signal - this is the strategy the
    TradingView webhook was actually built for (the Pine indicator behind
    the 66.8% backtest fires the live alert here), not the Python opening-
    range breakout used by SPY_0DTE_5M below. Shared by SPY_0DTE_1M and
    every SPY_RATCHET_* variant, per owner direction: they're the same
    entry, only their exit (ratchet floor/stop vs. 1M's own exit) differs.
    A fresh, direction-parseable TradingView alert for `symbol` is the
    only thing that qualifies an entry; no alert means no trade, regardless
    of what any other price math says. Consumption is tracked per
    play_type (not globally), so the SAME alert can independently open
    SPY_0DTE_1M and every enabled ratchet variant without one consuming it
    and starving the others - each play_type can still only consume a
    given alert once, so a position that opens and closes quickly can't
    reopen off the same stale alert."""
    try:
        event = dynamic_universe.recent_tradingview_signal(
            symbol, SPY_0DTE_1M_TRADINGVIEW_MAX_AGE_SECONDS
        )
    except Exception as exc:
        return _unavailable_context(f"tradingview signal lookup failed: {exc}")
    if not event:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": "no TradingView alert received in the last "
            f"{SPY_0DTE_1M_TRADINGVIEW_MAX_AGE_SECONDS}s",
            "failures": ["no fresh TradingView alert"],
        }
    if _tradingview_event_already_consumed(play_type, int(event["id"])):
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": "the latest TradingView alert already opened a trade for this variant",
            "failures": ["TradingView alert already consumed"],
        }
    direction = spy_0dte_tradingview_direction(event)
    if direction is None:
        return {
            "qualified": False,
            "regime": "NO TRADE",
            "reason": f"TradingView alert received but direction was not recognized: {event.get('event_type')!r}",
            "failures": ["TradingView alert direction unrecognized"],
        }
    # Consumption is marked only once a candidate built from this alert
    # actually becomes a real open row (_mark_tradingview_event_if_opened,
    # called from main()'s open loop), NOT here. Marking it here - on a
    # mere successful parse - meant a fresh, correctly-parsed alert got
    # permanently burned the first time ANY scan cycle glanced at it,
    # even if scan_spy_0dte_candidates then found no real contract or a
    # later filter (exposure cap, entry window) rejected it - with no
    # way for a later, still-fresh scan cycle to ever retry it. Real
    # incident: 2026-08-13 09:01:59 alert was marked consumed by all 11
    # TradingView-gated strategies at 09:03:16, yet zero of them opened
    # a real trade that day.
    regime = "BULLISH / CONTROLLED" if direction == "BULLISH" else "BEARISH / CONTROLLED"
    return {
        "qualified": True,
        "regime": regime,
        "reason": f"TradingView alert ({event.get('event_type')}) at {event.get('received_at')}",
        "failures": [],
        "tradingview_event_id": event["id"],
    }


def spy_0dte_exit_signal(
    entry_price: float,
    mark: float,
    minutes_remaining: float,
    peak_pct: float = 0.0,
) -> tuple[str, str]:
    """Standalone SPY 0DTE exit: symmetric stop/target, a one-time-raised
    floor once the trade proves itself, and a hard close as the session
    ends - no thesis-invalidation re-read, no continuous trailing stop.
    0DTE has no next session to trail into; by design this is a single-
    session in-and-out trade, not a scaled-down version of swing's
    multi-day management.

    peak_pct is the best pl_pct% this position has reached so far -
    the caller tracks it (same pattern as every other play type's
    max_favorable_pct). The floor raises ONCE, from -SPY_0DTE_STOP_PCT
    to SPY_0DTE_FLOOR_PCT, the first time peak_pct crosses
    SPY_0DTE_FLOOR_TRIGGER_PCT, and never moves again after that - it
    does not keep chasing the peak. A continuously-trailing version was
    tested and made things worse (21 of 24 fires cut off a trade that
    would have gone on to hit the real target; only 3 were genuine
    saves) because 0DTE dips and recovers constantly on the way to a
    real move."""
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    pnl_pct = (mark - entry_price) / entry_price * 100
    stop_floor = SPY_0DTE_FLOOR_PCT if peak_pct >= SPY_0DTE_FLOOR_TRIGGER_PCT else -SPY_0DTE_STOP_PCT * 100
    if pnl_pct <= stop_floor:
        if stop_floor > -SPY_0DTE_STOP_PCT * 100:
            return "BREAKEVEN STOP", (
                f"peaked at {peak_pct:.0f}%, down to {pnl_pct:.0f}% - protecting the proven "
                f"move instead of risking a full round-trip to the {SPY_0DTE_STOP_PCT * 100:.0f}% stop"
            )
        return "STOP OUT", f"down {pnl_pct:.0f}%, past the {SPY_0DTE_STOP_PCT * 100:.0f}% 0DTE stop"
    if pnl_pct >= SPY_0DTE_TARGET_PCT * 100:
        return "TAKE PROFIT", f"up {pnl_pct:.0f}%, past the {SPY_0DTE_TARGET_PCT * 100:.0f}% 0DTE target"
    if minutes_remaining <= 15:
        return "EOD CLOSE", "closing ahead of same-day expiration - 0DTE never holds overnight"
    return "HOLD", "no exit condition met"


def spy_ratchet_exit_signal(
    entry_price: float,
    mark: float,
    minutes_remaining: float,
    peak_pct: float,
    step_pct: float,
    stop_pct: float,
) -> tuple[str, str]:
    """Shared exit for every SPY_RATCHET_* variant (see SPY_RATCHET_VARIANTS)
    - no fixed take-profit target. Once peak_pct first reaches step_pct, the
    floor locks at the highest step_pct multiple <= peak_pct and ratchets up
    every further step; stop_pct (already negative) only applies before the
    first step ever fires. Ported directly from the backtest's
    simulate_ratchet (scratch script, 2026-08-10) - same floor math, same
    stop-before-first-step behavior, now driven off the real entry_price/
    mark this evaluator already uses everywhere else instead of the
    backtest's theta-approximated synthetic premium.

    Uses distinct signal strings ("FLOOR STOP" / own "RATCHET EOD CLOSE")
    rather than reusing SPY_0DTE's "BREAKEVEN STOP"/"EOD CLOSE" - those
    names describe a different mechanism (a one-time raise vs. a
    continuously-ratcheting floor) and "EOD CLOSE" specifically is not in
    main()'s shared close-trigger set (SPY_0DTE's EOD handling is out of
    scope for every other strategy, per the same precedent
    spy_key_levels_exit_signal's "EXPIRATION CLOSE" already follows)."""
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    pnl_pct = (mark - entry_price) / entry_price * 100
    if peak_pct >= step_pct:
        floor_pct = (peak_pct // step_pct) * step_pct
        stop_level = floor_pct
    else:
        floor_pct = None
        stop_level = stop_pct
    if pnl_pct <= stop_level:
        if floor_pct is not None:
            return "FLOOR STOP", (
                f"peaked at {peak_pct:.0f}%, down to {pnl_pct:.0f}% - ratchet floor locked at "
                f"{floor_pct:.0f}% after crossing a {step_pct:.0f}% step"
            )
        return "STOP OUT", f"down {pnl_pct:.0f}%, past the {abs(stop_pct):.0f}% base stop before any step fired"
    if minutes_remaining <= 15:
        return "RATCHET EOD CLOSE", "closing ahead of same-day expiration - 0DTE never holds overnight"
    return "HOLD", "no exit condition met"


def scan_spy_0dte_candidates(
    chain: list[dict[str, Any]],
    kind: str,
    expiration: str,
    spot_price: float,
    market_context: dict[str, Any] | None = None,
    play_type: str = "SPY_0DTE_5M",
) -> list[dict[str, Any]]:
    """Candidate builder for SPY 0DTE - its own delta band and its own
    risk cap (SPY_0DTE_MAX_CONTRACT_ASK/SPY_0DTE_MAX_RISK_PER_TRADE),
    built standalone per explicit owner direction not to reuse the
    retired multi-ticker single-leg machinery.

    Shared by both independently-tracked SPY_0DTE_1M and SPY_0DTE_5M
    strategies - they differ only in the opening-range bar interval used
    by spy_0dte_opening_range_signal, not in contract selection, delta
    band, or risk cap. play_type tags which one a given candidate came
    from so the two are tracked, cooled-down, and learned from separately.

    candidate_to_row reads cost_or_credit/pop/max_profit/max_risk/
    breakeven/option_symbol directly off every candidate, so a SPY_0DTE
    candidate missing any of them would KeyError the moment a real trade
    tried to open, not just look incomplete in a report."""
    candidates: list[dict[str, Any]] = []
    for option in chain:
        if not option_has_liquidity(option):
            continue
        delta = abs(greek(option, "delta") or 0.0)
        if not SPY_0DTE_DELTA_MIN <= delta <= SPY_0DTE_DELTA_MAX:
            continue
        ask = as_float(option.get("ask"), 0.0) or 0.0
        bid = as_float(option.get("bid"), 0.0) or 0.0
        if ask <= 0:
            continue
        if ask > SPY_0DTE_MAX_CONTRACT_ASK or ask * 100 > SPY_0DTE_MAX_RISK_PER_TRADE:
            continue
        strike = float(option["strike"])
        max_profit: str | float = "UNLIMITED" if kind == "call" else round(max((strike - ask) * 100, 0), 2)
        breakeven = round(strike + ask if kind == "call" else strike - ask, 2)
        candidates.append(
            {
                "play_type": play_type,
                "call_or_put": kind,
                "strike": fmt_strike(strike),
                "expiration": expiration,
                "entry_price": round(ask, 2),
                "cost_or_credit": str(round(ask, 2)),
                "delta": round(delta, 4),
                "theta": round(greek(option, "theta") or 0.0, 4),
                "iv": round(iv_value(option), 4) if iv_value(option) is not None else "",
                "pop": round(delta * 100, 1),
                "max_profit": max_profit,
                "max_risk": round(ask * 100, 2),
                "breakeven": breakeven,
                "open_interest": open_interest_value(option),
                "option_volume": option_volume_value(option),
                "bid_ask_width": round(max(ask - bid, 0), 2),
                "option_symbol": option.get("symbol") or option_symbol(SPY_0DTE_TICKER, expiration, kind, strike),
                "spot_at_entry": spot_price,
                "score": round(delta * 100, 1),
                "setup_reason": (market_context or {}).get(
                    "reason", "Opening-range breakout confirmed"
                ),
                "market_regime": (market_context or {}).get("regime", "CONTROLLED"),
                # Carried through so a TradingView alert only gets marked
                # consumed once a candidate built from it actually becomes
                # a real open row (see _mark_tradingview_event_if_opened) -
                # not merely because it qualified and was scanned.
                "tradingview_event_id": (market_context or {}).get("tradingview_event_id"),
            }
        )
    # Nearest-to-breakeven (lowest ask) first - the cheapest real contract
    # that still clears the delta band, not the richest one.
    candidates.sort(key=lambda c: c["entry_price"])
    return candidates


# ---------------------------------------------------------------------------
# SPY Key-Levels / ORB / VWAP strategy - a second, fully independent SPY
# strategy family. Built entirely standalone per explicit owner direction:
# no constant, delta band, risk cap, stop model, or exit rule below is read
# from or shared with SPY_0DTE. It only reuses genuinely generic, already-
# shared plumbing that every play type depends on (get_chain/get_strikes/
# get_expirations/get_daily_history, simple_moving_average, option_has_
# liquidity, candidate_to_row, evaluate_open_row's dispatch, close_row) -
# the same plumbing SPY_0DTE itself sits on top of.
#
# Source strategy: premarket/prior-day/prior-week high-low, a 9:30-9:45 ET
# opening range (wick high/low), session VWAP, and the 200-day SMA are
# tracked as ten reference levels. A trade qualifies when SPY's 1m/3m/5m
# direction agrees (Bullish or Bearish, not Mixed) AND spot is currently
# interacting with one of the ten levels. Everything else (exact indicator
# math for "bullish/bearish" per timeframe, the level-interaction proximity
# band, the profit-target R-multiple, and the DTE-selection rule) is not
# specified by the source strategy and was improvised - see each function's
# docstring for the specific choice made.
# ---------------------------------------------------------------------------

SPY_KEY_LEVELS_TICKER = "SPY"
SPY_KEY_LEVELS_PLAY_TYPE = "SPY_KEY_LEVELS"

SPY_KEY_LEVELS_OPENING_RANGE_MINUTES = int(os.environ.get(
    "SPY_KEY_LEVELS_OPENING_RANGE_MINUTES", configured("spy_key_levels_opening_range_minutes", 15)
))
# Improvised: how close SPY has to be to a tracked level to count as
# "interacting with" it. 0.10% of a ~$600 SPY print is about $0.60.
SPY_KEY_LEVELS_LEVEL_PROXIMITY_PCT = float(os.environ.get(
    "SPY_KEY_LEVELS_LEVEL_PROXIMITY_PCT", configured("spy_key_levels_level_proximity_pct", 0.10)
))
SPY_KEY_LEVELS_DELTA_MIN = float(os.environ.get(
    "SPY_KEY_LEVELS_DELTA_MIN", configured("spy_key_levels_delta_min", 0.40)
))
SPY_KEY_LEVELS_DELTA_MAX = float(os.environ.get(
    "SPY_KEY_LEVELS_DELTA_MAX", configured("spy_key_levels_delta_max", 0.60)
))
SPY_KEY_LEVELS_MAX_CONTRACT_ASK = float(os.environ.get(
    "SPY_KEY_LEVELS_MAX_CONTRACT_ASK", configured("spy_key_levels_max_contract_ask", 5.0)
))
SPY_KEY_LEVELS_MAX_RISK_PER_TRADE = float(os.environ.get(
    "SPY_KEY_LEVELS_MAX_RISK_PER_TRADE", configured("spy_key_levels_max_risk_per_trade", 500.0)
))
# Improvised: the spec gives an entry + stop but no profit target. A stop
# is defined in underlying terms (the active level, past the point where
# the trade's own premise is proven wrong); the target is set as a fixed
# multiple of that same underlying-terms risk distance - a standard
# risk-defined-target convention, not something read off the source text.
SPY_KEY_LEVELS_TARGET_R_MULTIPLE = float(os.environ.get(
    "SPY_KEY_LEVELS_TARGET_R_MULTIPLE", configured("spy_key_levels_target_r_multiple", 2.0)
))
# Improvised: how far past the active level (in underlying %) counts as
# "broke the level" for the stop, rather than normal noise around it.
SPY_KEY_LEVELS_STOP_BUFFER_PCT = float(os.environ.get(
    "SPY_KEY_LEVELS_STOP_BUFFER_PCT", configured("spy_key_levels_stop_buffer_pct", 0.15)
))
# Real incident 2026-08-14: three positions opened 08-13, held overnight
# (WEEKLY tier), peaked at +10-12% the next morning, then round-tripped
# all the way to -42%/-46%/-50% before the underlying finally crossed
# its stop level (only SPY_KEY_LEVELS_STOP_BUFFER_PCT = 0.15% away) at
# 10:51am - theta plus a small adverse move ate the whole position while
# the underlying-only stop had nothing to say about it. Unlike SPY_0DTE
# (a hard -50% premium stop, plus a floor that locks in once a trade
# proves itself), Key-Levels previously had ZERO premium-based backstop
# at all - a position could bleed to any loss for however long it takes
# the underlying to reach its level. These two constants close that gap,
# same shape as SPY_0DTE_STOP_PCT/FLOOR_TRIGGER_PCT/FLOOR_PCT. Values
# are a reasoned first pass, not backtested against a real Key-Levels
# sample the way 0DTE's floor was (62 trades) - the underlying-level
# stop/target stay the strategy's primary exit; these only step in when
# real premium loss/gain has already happened regardless of level.
SPY_KEY_LEVELS_STOP_PCT = float(os.environ.get(
    "SPY_KEY_LEVELS_STOP_PCT", configured("spy_key_levels_stop_pct", 0.50)
))
SPY_KEY_LEVELS_FLOOR_TRIGGER_PCT = float(os.environ.get(
    "SPY_KEY_LEVELS_FLOOR_TRIGGER_PCT", configured("spy_key_levels_floor_trigger_pct", 10.0)
))
SPY_KEY_LEVELS_FLOOR_PCT = float(os.environ.get(
    "SPY_KEY_LEVELS_FLOOR_PCT", configured("spy_key_levels_floor_pct", 0.0)
))


def spy_key_levels_wick_range(bars: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    """Highest high / lowest low across a set of bars, using full wicks
    (not just closes) - shared math for every "high/low over a window"
    level this strategy tracks (premarket, prior day, prior week, opening
    range)."""
    highs = [value for bar in bars if (value := as_float(bar.get("high"))) is not None]
    lows = [value for bar in bars if (value := as_float(bar.get("low"))) is not None]
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)


def spy_key_levels_premarket_range(premarket_bars: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    return spy_key_levels_wick_range(premarket_bars)


def spy_key_levels_prior_day_range(
    daily_bars: list[dict[str, Any]], today_str: str
) -> tuple[float | None, float | None]:
    """daily_bars is get_daily_history()'s output, oldest-first. The most
    recent bar dated strictly before today is "previous trading day" -
    skips today's own partial bar if the provider ever includes it."""
    prior = [bar for bar in daily_bars if str(bar.get("date", ""))[:10] < today_str]
    if not prior:
        return None, None
    last = prior[-1]
    return as_float(last.get("high")), as_float(last.get("low"))


def spy_key_levels_prior_week_range(
    daily_bars: list[dict[str, Any]], today_str: str
) -> tuple[float | None, float | None]:
    """Highest high / lowest low across every daily bar that falls in the
    ISO calendar week immediately before today's ISO calendar week."""
    today = date.fromisoformat(today_str)
    this_week = today.isocalendar()[:2]
    prior_week_bars = []
    for bar in daily_bars:
        raw_date = str(bar.get("date", ""))[:10]
        try:
            bar_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        year, week, _ = bar_date.isocalendar()
        if (year, week) != this_week and bar_date < today:
            candidate_key = (year, week)
            # Only keep bars from the single ISO week immediately prior -
            # recomputed against the running max below rather than assumed,
            # since isocalendar() week numbers don't subtract cleanly across
            # a year boundary.
            prior_week_bars.append((candidate_key, bar))
    if not prior_week_bars:
        return None, None
    latest_prior_week = max(key for key, _ in prior_week_bars)
    bars_in_week = [bar for key, bar in prior_week_bars if key == latest_prior_week]
    return spy_key_levels_wick_range(bars_in_week)


def spy_key_levels_opening_range(
    session_bars: list[dict[str, Any]], bar_minutes: int = 1, window_minutes: int = 15
) -> tuple[float | None, float | None]:
    """Wick high/low of the complete first window_minutes of the regular
    session (9:30-9:45 ET by default), built from whatever intraday bar
    interval was fetched - matches the source spec's "use the complete
    candlestick and its wicks" instruction by taking the max high / min low
    across every bar inside that window rather than only its closes."""
    bars_needed = max(window_minutes // bar_minutes, 1)
    if len(session_bars) < bars_needed:
        return None, None
    return spy_key_levels_wick_range(session_bars[:bars_needed])


def spy_key_levels_vwap(session_bars: list[dict[str, Any]]) -> float | None:
    """Session VWAP using typical price (H+L+C)/3, standard VWAP
    convention - a separate implementation from the retired
    directional_market_context's close-only VWAP proxy, per explicit
    owner direction not to reuse other strategies' logic."""
    numerator = 0.0
    denominator = 0.0
    for bar in session_bars:
        high = as_float(bar.get("high"))
        low = as_float(bar.get("low"))
        close = as_float(bar.get("close") or bar.get("price"))
        volume = as_float(bar.get("volume"), 0.0) or 0.0
        if high is None or low is None or close is None or volume <= 0:
            continue
        typical_price = (high + low + close) / 3
        numerator += typical_price * volume
        denominator += volume
    if denominator <= 0:
        return None
    return numerator / denominator


def spy_key_levels_sma200(daily_bars: list[dict[str, Any]]) -> float | None:
    closes = [value for bar in daily_bars if (value := as_float(bar.get("close"))) is not None]
    return simple_moving_average(closes, 200)


def spy_key_levels_timeframe_direction(bars: list[dict[str, Any]], average_period: int = 5) -> str:
    """Improvised: a single timeframe reads Bullish when its latest close is
    above a short simple moving average of its own closes, Bearish when
    below, Mixed when exactly on it or too little data exists yet. The
    source spec names 1m/3m/5m as the inputs but never defines what makes
    one of them bullish vs bearish - this is that missing definition."""
    closes = [value for bar in bars if (value := as_float(bar.get("close") or bar.get("price"))) is not None]
    average = simple_moving_average(closes, average_period)
    if average is None or not closes:
        return "MIXED"
    last = closes[-1]
    if last > average:
        return "BULLISH"
    if last < average:
        return "BEARISH"
    return "MIXED"


def spy_key_levels_combined_direction(dir_1m: str, dir_3m: str, dir_5m: str) -> str:
    """All three timeframes must agree for a directional (non-Mixed) read -
    matches the spec's "read the three timeframes together" instruction."""
    directions = {dir_1m, dir_3m, dir_5m}
    if directions == {"BULLISH"}:
        return "BULLISH"
    if directions == {"BEARISH"}:
        return "BEARISH"
    return "MIXED"


def spy_key_levels_active_level(
    spot_price: float, levels: dict[str, float | None]
) -> tuple[str | None, float | None]:
    """Returns the name/price of the tracked level SPY is currently closest
    to, if any level is within SPY_KEY_LEVELS_LEVEL_PROXIMITY_PCT of spot -
    that's this strategy's definition of "interacting with" a level."""
    best_name: str | None = None
    best_price: float | None = None
    best_distance_pct: float | None = None
    for name, level in levels.items():
        if level is None or level <= 0 or spot_price <= 0:
            continue
        distance_pct = abs(spot_price - level) / level * 100
        if distance_pct <= SPY_KEY_LEVELS_LEVEL_PROXIMITY_PCT:
            if best_distance_pct is None or distance_pct < best_distance_pct:
                best_name, best_price, best_distance_pct = name, level, distance_pct
    return best_name, best_price


def spy_key_levels_choose_expiration(
    expirations: list[str], today_str: str, catalyst_active: bool
) -> tuple[str, str] | None:
    """Improvised DTE-selection rule - the spec lists 0DTE/1-3DTE/weekly as
    the choices but never says how to pick one automatically. Default is
    0DTE (matches the spec's "use strict risk management with 0DTE"
    framing of it as the normal case); step up to the nearest weekly
    expiration instead when a high-impact catalyst is active, trading
    through the extra event risk with more time cushion rather than 0DTE
    gamma. Falls back to the nearest 1-3 DTE listing, then any weekly
    listing, if the preferred tier isn't actually available today."""
    if not expirations:
        return None
    today = date.fromisoformat(today_str)
    days_out = {}
    for expiration in expirations:
        try:
            days_out[expiration] = (date.fromisoformat(expiration) - today).days
        except ValueError:
            continue

    def _nearest_in_range(low: int, high: int) -> str | None:
        in_range = sorted(
            (expiration for expiration, days in days_out.items() if low <= days <= high),
            key=lambda expiration: days_out[expiration],
        )
        return in_range[0] if in_range else None

    if catalyst_active:
        weekly = _nearest_in_range(5, 9)
        if weekly:
            return "WEEKLY", weekly
    if today_str in days_out and days_out[today_str] == 0:
        return "0DTE", today_str
    near = _nearest_in_range(1, 3)
    if near:
        return "1-3DTE", near
    weekly = _nearest_in_range(5, 9)
    if weekly:
        return "WEEKLY", weekly
    return None


def spy_key_levels_entry_signal(
    *,
    spot_price: float,
    direction: str,
    levels: dict[str, float | None],
    catalyst: dict[str, Any] | None,
) -> dict[str, Any]:
    """Combines direction + level-interaction into a qualify/reject read.

    catalyst is informational only, never a hard block - the source spec
    says to "display an alert when an important event or catalyst is
    active or approaching" before entering, not to refuse to trade. It's
    carried through on the result (surfaced as the spec's "Current event or
    catalyst" signal-output field) and used by spy_key_levels_choose_
    expiration to prefer a longer DTE instead of 0DTE gamma risk when one
    is active - that's the actual risk response, not blocking the trade."""
    active_level_name, active_level_price = spy_key_levels_active_level(spot_price, levels)
    if direction == "MIXED":
        return {
            "qualified": False,
            "direction": direction,
            "reason": "1m/3m/5m direction is mixed; no aligned edge",
            "active_level_name": active_level_name,
            "active_level_price": active_level_price,
            "catalyst": catalyst,
        }
    if active_level_name is None:
        return {
            "qualified": False,
            "direction": direction,
            "reason": "SPY is not currently interacting with any tracked level",
            "active_level_name": None,
            "active_level_price": None,
            "catalyst": catalyst,
        }
    side = "call" if direction == "BULLISH" else "put"
    reason = (
        f"{direction.title()} across 1m/3m/5m while interacting with "
        f"{active_level_name.replace('_', ' ')} (${active_level_price:.2f})"
    )
    if catalyst is not None:
        reason += f"; catalyst alert: {catalyst.get('title', 'unnamed event')}"
    return {
        "qualified": True,
        "direction": direction,
        "side": side,
        "active_level_name": active_level_name,
        "active_level_price": active_level_price,
        "reason": reason,
        "catalyst": catalyst,
    }


def spy_key_levels_stop_and_target(
    side: str, entry_underlying_price: float, active_level_price: float
) -> tuple[float, float]:
    """Underlying-price-level stop (the spec's own design: exit when SPY
    breaks back through the level being traded, not a % of premium), plus
    an R-multiple target off the same underlying-terms risk distance."""
    if side == "call":
        stop = active_level_price * (1 - SPY_KEY_LEVELS_STOP_BUFFER_PCT / 100)
        risk_distance = max(entry_underlying_price - stop, 0.01)
        target = entry_underlying_price + SPY_KEY_LEVELS_TARGET_R_MULTIPLE * risk_distance
    else:
        stop = active_level_price * (1 + SPY_KEY_LEVELS_STOP_BUFFER_PCT / 100)
        risk_distance = max(stop - entry_underlying_price, 0.01)
        target = entry_underlying_price - SPY_KEY_LEVELS_TARGET_R_MULTIPLE * risk_distance
    return round(stop, 2), round(target, 2)


def spy_key_levels_exit_signal(
    *,
    side: str,
    stop_underlying_price: float,
    target_underlying_price: float,
    current_underlying_price: float,
    expiration_tier: str,
    is_expiration_day: bool,
    minutes_remaining: float,
    pnl_pct: float = 0.0,
    peak_pct: float = 0.0,
) -> tuple[str, str]:
    """Underlying-price-based stop/target - this strategy's own exit model,
    not the %-of-premium model the SPY_0DTE strategies use. Only forces a
    same-day close on the actual expiration date; a 1-3DTE/weekly position
    holds overnight until it hits its stop, target, or its own expiration
    day, per the spec's "additional time, flexibility, and room for error"
    framing of the longer-dated tiers.

    pnl_pct/peak_pct back the two premium-based checks below them, added
    after a real incident (see SPY_KEY_LEVELS_STOP_PCT's own comment):
    three positions round-tripped from +12% to -42%/-46%/-50% of premium
    overnight while the underlying-level stop, only
    SPY_KEY_LEVELS_STOP_BUFFER_PCT away, stayed silent the whole time.
    Those checks are a backstop, not a replacement - the underlying-level
    read above still runs first and still owns the normal case."""
    if side == "call":
        if current_underlying_price <= stop_underlying_price:
            return "STOP OUT", (
                f"SPY broke back through the traded level to ${current_underlying_price:.2f}, "
                f"past the ${stop_underlying_price:.2f} stop"
            )
        if current_underlying_price >= target_underlying_price:
            return "TAKE PROFIT", (
                f"SPY reached ${current_underlying_price:.2f}, past the "
                f"${target_underlying_price:.2f} target"
            )
    else:
        if current_underlying_price >= stop_underlying_price:
            return "STOP OUT", (
                f"SPY broke back through the traded level to ${current_underlying_price:.2f}, "
                f"past the ${stop_underlying_price:.2f} stop"
            )
        if current_underlying_price <= target_underlying_price:
            return "TAKE PROFIT", (
                f"SPY reached ${current_underlying_price:.2f}, past the "
                f"${target_underlying_price:.2f} target"
            )
    if pnl_pct <= -SPY_KEY_LEVELS_STOP_PCT * 100:
        return "STOP OUT", (
            f"down {pnl_pct:.0f}% of premium, past the {SPY_KEY_LEVELS_STOP_PCT * 100:.0f}% "
            "backstop regardless of the underlying level"
        )
    if peak_pct >= SPY_KEY_LEVELS_FLOOR_TRIGGER_PCT and pnl_pct <= SPY_KEY_LEVELS_FLOOR_PCT:
        return "BREAKEVEN STOP", (
            f"peaked at {peak_pct:.0f}% of premium, down to {pnl_pct:.0f}% - protecting the "
            "proven move instead of riding it back through the underlying-level stop"
        )
    if is_expiration_day and minutes_remaining <= 15:
        # Named "EXPIRATION CLOSE" (not SPY_0DTE's "EOD CLOSE" string) so
        # this strategy's forced-close signal is its own distinct value in
        # the shared close-trigger set main() checks - adding "EOD CLOSE"
        # there would also change SPY_0DTE_1M/5M's own closing behavior,
        # which is explicitly out of scope for this strategy's changes.
        return "EXPIRATION CLOSE", "closing ahead of same-day expiration"
    return "HOLD", "no exit condition met"


def scan_spy_key_levels_candidates(
    chain: list[dict[str, Any]],
    entry: dict[str, Any],
    expiration: str,
    expiration_tier: str,
    spot_price: float,
) -> list[dict[str, Any]]:
    """Candidate builder for SPY Key-Levels - its own delta band and risk
    cap (SPY_KEY_LEVELS_*), independent of SPY_0DTE's. entry is a qualified
    result from spy_key_levels_entry_signal (side/active_level_name/
    active_level_price already resolved)."""
    kind = entry["side"]
    active_level_price = entry["active_level_price"]
    stop_underlying, target_underlying = spy_key_levels_stop_and_target(
        kind, spot_price, active_level_price
    )
    candidates: list[dict[str, Any]] = []
    for option in chain:
        if option.get("option_type") != kind:
            continue
        if not option_has_liquidity(option):
            continue
        delta = abs(greek(option, "delta") or 0.0)
        if not SPY_KEY_LEVELS_DELTA_MIN <= delta <= SPY_KEY_LEVELS_DELTA_MAX:
            continue
        ask = as_float(option.get("ask"), 0.0) or 0.0
        bid = as_float(option.get("bid"), 0.0) or 0.0
        if ask <= 0:
            continue
        if ask > SPY_KEY_LEVELS_MAX_CONTRACT_ASK or ask * 100 > SPY_KEY_LEVELS_MAX_RISK_PER_TRADE:
            continue
        strike = float(option["strike"])
        max_profit: str | float = "UNLIMITED" if kind == "call" else round(max((strike - ask) * 100, 0), 2)
        breakeven = round(strike + ask if kind == "call" else strike - ask, 2)
        candidates.append(
            {
                "play_type": SPY_KEY_LEVELS_PLAY_TYPE,
                "call_or_put": kind,
                "strike": fmt_strike(strike),
                "expiration": expiration,
                "entry_price": round(ask, 2),
                "cost_or_credit": str(round(ask, 2)),
                "delta": round(delta, 4),
                "theta": round(greek(option, "theta") or 0.0, 4),
                "iv": round(iv_value(option), 4) if iv_value(option) is not None else "",
                "pop": round(delta * 100, 1),
                "max_profit": max_profit,
                "max_risk": round(ask * 100, 2),
                "breakeven": breakeven,
                "open_interest": open_interest_value(option),
                "option_volume": option_volume_value(option),
                "bid_ask_width": round(max(ask - bid, 0), 2),
                "option_symbol": option.get("symbol") or option_symbol(SPY_KEY_LEVELS_TICKER, expiration, kind, strike),
                "spot_at_entry": spot_price,
                "score": round(delta * 100, 1),
                "setup_reason": entry.get("reason", ""),
                "market_regime": entry.get("direction", ""),
                "underlying_entry_price": round(spot_price, 2),
                "underlying_stop_price": stop_underlying,
                "underlying_target_price": target_underlying,
                "active_level_name": entry.get("active_level_name", ""),
                "expiration_tier": expiration_tier,
            }
        )
    candidates.sort(key=lambda c: c["entry_price"])
    return candidates


# ---------------------------------------------------------------------------
# SPY 0-1 DTE Expansion-Level strategy - a third, fully independent SPY
# strategy family. Built entirely standalone per the same owner direction
# as SPY_KEY_LEVELS: no constant, delta band, risk cap, stop model, or
# level-calculator below is shared with SPY_0DTE or SPY_KEY_LEVELS, even
# where the underlying math is similar (prior-day/prior-week high-low) -
# each strategy owns its own copy rather than reading another's. The only
# things reused are genuinely generic, strategy-agnostic primitives that
# already sit in this file for every strategy to share: get_chain/
# get_expirations/get_daily_history/get_intraday_history, simple_moving_
# average, exponential_moving_average(_series), resample_bars,
# option_has_liquidity, candidate_to_row, evaluate_open_row's dispatch.
#
# Source strategy: SPY calls/puts, 0-1 DTE, qualify when price is at/near
# one of six reference levels (prior day/week/month high/low) AND the 20/200
# EMA and MACD histogram color agree in the same direction across the
# 15-minute, 30-minute, and 1-hour timeframes. Two things the source spec
# explicitly said not to invent are handled as documented, owner-confirmed
# choices rather than silent guesses: the MACD "bright green/bright red"
# histogram color rule (standard 4-color convention: bright = extending in
# that color's direction vs. the prior bar, dark = fading back toward zero -
# confirmed acceptable since nothing here renders charts, only the
# underlying numeric condition matters), and the stop/target/floor exit
# (this strategy's own %-of-premium constants, same mechanical shape as
# SPY_0DTE's but independently defined and independently tunable, per
# explicit owner choice not to literally call spy_0dte_exit_signal()).
# ---------------------------------------------------------------------------

SPY_EXPANSION_TICKER = "SPY"
SPY_EXPANSION_PLAY_TYPE = "SPY_EXPANSION_LEVEL"

# The spec's own formula: level_distance = abs(price - level); at_or_near =
# level_distance <= configured_level_tolerance - a dollar tolerance, not a
# percent, matching that formula literally. The source trader didn't supply
# a number, so this stays a visible, tunable setting rather than a silently
# invented permanent value.
SPY_EXPANSION_LEVEL_TOLERANCE = float(os.environ.get(
    "SPY_EXPANSION_LEVEL_TOLERANCE", configured("spy_expansion_level_tolerance", 0.50)
))
SPY_EXPANSION_EMA_FAST_PERIOD = int(os.environ.get(
    "SPY_EXPANSION_EMA_FAST_PERIOD", configured("spy_expansion_ema_fast_period", 20)
))
SPY_EXPANSION_EMA_SLOW_PERIOD = int(os.environ.get(
    "SPY_EXPANSION_EMA_SLOW_PERIOD", configured("spy_expansion_ema_slow_period", 200)
))
# "Use the system's existing MACD parameters without inventing different
# settings" - the only existing MACD-adjacent code in this repo
# (local_information_engine.py's market_snapshot) uses a 12/26 fast/slow
# EMA pair for the MACD line; that's carried over here. A signal-line
# period is also required to get a histogram (line minus its own signal
# EMA), which nothing existing needed before - 9 is the universal standard
# third MACD parameter, not a strategy-specific invention.
SPY_EXPANSION_MACD_FAST_PERIOD = int(os.environ.get(
    "SPY_EXPANSION_MACD_FAST_PERIOD", configured("spy_expansion_macd_fast_period", 12)
))
SPY_EXPANSION_MACD_SLOW_PERIOD = int(os.environ.get(
    "SPY_EXPANSION_MACD_SLOW_PERIOD", configured("spy_expansion_macd_slow_period", 26)
))
SPY_EXPANSION_MACD_SIGNAL_PERIOD = int(os.environ.get(
    "SPY_EXPANSION_MACD_SIGNAL_PERIOD", configured("spy_expansion_macd_signal_period", 9)
))
SPY_EXPANSION_DELTA_MIN = float(os.environ.get(
    "SPY_EXPANSION_DELTA_MIN", configured("spy_expansion_delta_min", 0.40)
))
SPY_EXPANSION_DELTA_MAX = float(os.environ.get(
    "SPY_EXPANSION_DELTA_MAX", configured("spy_expansion_delta_max", 0.60)
))
SPY_EXPANSION_MAX_CONTRACT_ASK = float(os.environ.get(
    "SPY_EXPANSION_MAX_CONTRACT_ASK", configured("spy_expansion_max_contract_ask", 5.0)
))
SPY_EXPANSION_MAX_RISK_PER_TRADE = float(os.environ.get(
    "SPY_EXPANSION_MAX_RISK_PER_TRADE", configured("spy_expansion_max_risk_per_trade", 500.0)
))
# Own %-of-premium stop/target/floor constants - same mechanical shape as
# SPY_0DTE's exit model (a hard stop, a target, a one-time-raised breakeven
# floor, forced flat near the close), independently defined per explicit
# owner choice, not read from SPY_0DTE's own constants.
SPY_EXPANSION_STOP_PCT = float(os.environ.get(
    "SPY_EXPANSION_STOP_PCT", configured("spy_expansion_stop_pct", 0.50)
))
SPY_EXPANSION_TARGET_PCT = float(os.environ.get(
    "SPY_EXPANSION_TARGET_PCT", configured("spy_expansion_target_pct", 0.50)
))
SPY_EXPANSION_FLOOR_TRIGGER_PCT = float(os.environ.get(
    "SPY_EXPANSION_FLOOR_TRIGGER_PCT", configured("spy_expansion_floor_trigger_pct", 30.0)
))
SPY_EXPANSION_FLOOR_PCT = float(os.environ.get(
    "SPY_EXPANSION_FLOOR_PCT", configured("spy_expansion_floor_pct", -15.0)
))
# How many calendar days of 15-minute bars to fetch for the EMA200/MACD
# read - 50 comfortably covers EMA200 on all three derived timeframes
# (15m/30m/1h) within Tradier's ~60-day 15-minute retention window,
# confirmed live rather than assumed.
SPY_EXPANSION_HISTORY_DAYS = int(os.environ.get(
    "SPY_EXPANSION_HISTORY_DAYS", configured("spy_expansion_history_days", 50)
))


def spy_expansion_wick_range(bars: list[dict[str, Any]]) -> tuple[float | None, float | None]:
    highs = [value for bar in bars if (value := as_float(bar.get("high"))) is not None]
    lows = [value for bar in bars if (value := as_float(bar.get("low"))) is not None]
    if not highs or not lows:
        return None, None
    return max(highs), min(lows)


def spy_expansion_prior_day_range(
    daily_bars: list[dict[str, Any]], today_str: str
) -> tuple[float | None, float | None]:
    prior = [bar for bar in daily_bars if str(bar.get("date", ""))[:10] < today_str]
    if not prior:
        return None, None
    last = prior[-1]
    return as_float(last.get("high")), as_float(last.get("low"))


def spy_expansion_prior_week_range(
    daily_bars: list[dict[str, Any]], today_str: str
) -> tuple[float | None, float | None]:
    today = date.fromisoformat(today_str)
    this_week = today.isocalendar()[:2]
    prior_week_bars = []
    for bar in daily_bars:
        raw_date = str(bar.get("date", ""))[:10]
        try:
            bar_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        year, week, _ = bar_date.isocalendar()
        if (year, week) != this_week and bar_date < today:
            prior_week_bars.append(((year, week), bar))
    if not prior_week_bars:
        return None, None
    latest_prior_week = max(key for key, _ in prior_week_bars)
    bars_in_week = [bar for key, bar in prior_week_bars if key == latest_prior_week]
    return spy_expansion_wick_range(bars_in_week)


def spy_expansion_prior_month_range(
    daily_bars: list[dict[str, Any]], today_str: str
) -> tuple[float | None, float | None]:
    today = date.fromisoformat(today_str)
    this_month = (today.year, today.month)
    prior_month_bars = []
    for bar in daily_bars:
        raw_date = str(bar.get("date", ""))[:10]
        try:
            bar_date = date.fromisoformat(raw_date)
        except ValueError:
            continue
        month_key = (bar_date.year, bar_date.month)
        if month_key != this_month and bar_date < today:
            prior_month_bars.append((month_key, bar))
    if not prior_month_bars:
        return None, None
    latest_prior_month = max(key for key, _ in prior_month_bars)
    bars_in_month = [bar for key, bar in prior_month_bars if key == latest_prior_month]
    return spy_expansion_wick_range(bars_in_month)


def spy_expansion_nearest_level(
    spot_price: float, levels: dict[str, float | None]
) -> tuple[str | None, float | None, float | None]:
    """Returns (level_code, level_price, distance) for the closest of the
    six reference levels within SPY_EXPANSION_LEVEL_TOLERANCE dollars of
    spot, or (None, None, None) if nothing qualifies. level_code is one of
    PDH/PDL/PWH/PWL/PMH/PML, matching the spec's required signal field."""
    best_code: str | None = None
    best_price: float | None = None
    best_distance: float | None = None
    for code, level in levels.items():
        if level is None or level <= 0:
            continue
        distance = abs(spot_price - level)
        if distance <= SPY_EXPANSION_LEVEL_TOLERANCE:
            if best_distance is None or distance < best_distance:
                best_code, best_price, best_distance = code, level, distance
    return best_code, best_price, best_distance


def spy_expansion_ema_direction(
    closes: list[float],
    fast_period: int = SPY_EXPANSION_EMA_FAST_PERIOD,
    slow_period: int = SPY_EXPANSION_EMA_SLOW_PERIOD,
) -> tuple[str, float | None, float | None]:
    """One timeframe's EMA structure read: BULLISH (fast > slow), BEARISH
    (fast < slow), or UNKNOWN (not enough data / exactly equal)."""
    fast = exponential_moving_average(closes, fast_period)
    slow = exponential_moving_average(closes, slow_period)
    if fast is None or slow is None:
        return "UNKNOWN", fast, slow
    if fast > slow:
        return "BULLISH", fast, slow
    if fast < slow:
        return "BEARISH", fast, slow
    return "UNKNOWN", fast, slow


def spy_expansion_macd_histogram(
    closes: list[float],
    fast_period: int = SPY_EXPANSION_MACD_FAST_PERIOD,
    slow_period: int = SPY_EXPANSION_MACD_SLOW_PERIOD,
    signal_period: int = SPY_EXPANSION_MACD_SIGNAL_PERIOD,
) -> tuple[float | None, float | None]:
    """Returns (current_histogram, previous_histogram) - the previous value
    is needed to tell "bright" (extending) from "dark" (fading) per the
    4-color convention below."""
    fast_series = exponential_moving_average_series(closes, fast_period)
    slow_series = exponential_moving_average_series(closes, slow_period)
    macd_line = [
        f - s if f is not None and s is not None else None
        for f, s in zip(fast_series, slow_series)
    ]
    valid_macd = [value for value in macd_line if value is not None]
    if len(valid_macd) < signal_period + 1:
        return None, None
    signal_series = exponential_moving_average_series(valid_macd, signal_period)
    histogram_series = [
        m - sig if sig is not None else None
        for m, sig in zip(valid_macd, signal_series)
    ]
    valid_histogram = [value for value in histogram_series if value is not None]
    if len(valid_histogram) < 2:
        return None, None
    return valid_histogram[-1], valid_histogram[-2]


def spy_expansion_macd_color(current: float | None, previous: float | None) -> str:
    """Standard 4-color MACD histogram convention, confirmed acceptable by
    the owner since nothing here renders charts - only the underlying
    numeric condition is used, not a specific indicator's exact palette.
    BRIGHT_GREEN: above zero and extending (rising further from the prior
    bar). DARK_GREEN: above zero but fading back toward zero. BRIGHT_RED:
    below zero and extending (falling further). DARK_RED: below zero but
    fading back toward zero."""
    if current is None or previous is None:
        return "UNKNOWN"
    if current > 0:
        return "BRIGHT_GREEN" if current > previous else "DARK_GREEN"
    if current < 0:
        return "BRIGHT_RED" if current < previous else "DARK_RED"
    return "UNKNOWN"


def spy_expansion_timeframe_read(closes: list[float]) -> dict[str, Any]:
    """One timeframe's complete read: EMA direction plus MACD color,
    everything the signal-output spec asks to report per timeframe."""
    ema_direction, ema_fast, ema_slow = spy_expansion_ema_direction(closes)
    histogram, previous_histogram = spy_expansion_macd_histogram(closes)
    color = spy_expansion_macd_color(histogram, previous_histogram)
    return {
        "ema_direction": ema_direction,
        "ema_fast": ema_fast,
        "ema_slow": ema_slow,
        "macd_histogram": histogram,
        "macd_color": color,
    }


def spy_expansion_signal(
    *,
    spot_price: float,
    levels: dict[str, float | None],
    timeframe_reads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Combines level proximity + full EMA/MACD alignment across every
    required timeframe (15m/30m/1h) into the spec's five-state signal:
    NO_SETUP / WATCHING_BULLISH_LEVEL / WATCHING_BEARISH_LEVEL /
    CALL_ENTRY_QUALIFIED / PUT_ENTRY_QUALIFIED. All three timeframes must
    independently agree - not a majority vote - per the spec's "on the
    required higher timeframes" (plural, all of them) wording."""
    level_code, level_price, distance = spy_expansion_nearest_level(spot_price, levels)
    reads = list(timeframe_reads.values())
    ema_all_bullish = bool(reads) and all(read["ema_direction"] == "BULLISH" for read in reads)
    ema_all_bearish = bool(reads) and all(read["ema_direction"] == "BEARISH" for read in reads)
    macd_all_bright_green = bool(reads) and all(read["macd_color"] == "BRIGHT_GREEN" for read in reads)
    macd_all_bright_red = bool(reads) and all(read["macd_color"] == "BRIGHT_RED" for read in reads)

    base = {
        "reference_level_type": level_code,
        "reference_level_price": level_price,
        "distance_from_level": distance,
        "timeframes": timeframe_reads,
        "timeframes_aligned": False,
    }

    if level_code is None:
        return {**base, "state": "NO_SETUP", "reason": "SPY is not at or near any of the six reference levels"}

    if ema_all_bullish and macd_all_bright_green:
        return {
            **base,
            "state": "CALL_ENTRY_QUALIFIED",
            "side": "call",
            "timeframes_aligned": True,
            "reason": (
                f"At {level_code} (${level_price:.2f}); 20 EMA above 200 EMA and MACD "
                "histogram bright green across 15m/30m/1h"
            ),
        }
    if ema_all_bearish and macd_all_bright_red:
        return {
            **base,
            "state": "PUT_ENTRY_QUALIFIED",
            "side": "put",
            "timeframes_aligned": True,
            "reason": (
                f"At {level_code} (${level_price:.2f}); 200 EMA above 20 EMA and MACD "
                "histogram bright red across 15m/30m/1h"
            ),
        }
    if ema_all_bullish:
        return {
            **base,
            "state": "WATCHING_BULLISH_LEVEL",
            "reason": f"At {level_code} (${level_price:.2f}) with bullish EMA structure; awaiting bright-green MACD confirmation",
        }
    if ema_all_bearish:
        return {
            **base,
            "state": "WATCHING_BEARISH_LEVEL",
            "reason": f"At {level_code} (${level_price:.2f}) with bearish EMA structure; awaiting bright-red MACD confirmation",
        }
    return {
        **base,
        "state": "NO_SETUP",
        "reason": f"At {level_code} (${level_price:.2f}) but EMA structure is not aligned across 15m/30m/1h",
    }


def spy_expansion_choose_expiration(expirations: list[str], today_str: str) -> str | None:
    """0-1 DTE per the spec - nearest listed expiration that is today or
    tomorrow. Improvised tie-break (spec never says how to pick between the
    two): prefers 0DTE when listed, falls back to the next day out."""
    if not expirations:
        return None
    today = date.fromisoformat(today_str)
    same_day = [expiration for expiration in expirations if expiration == today_str]
    if same_day:
        return same_day[0]
    next_day = (today + timedelta(days=1)).isoformat()
    one_dte = [expiration for expiration in expirations if expiration == next_day]
    if one_dte:
        return one_dte[0]
    return None


def spy_expansion_stop_and_target(side: str, entry_price: float) -> tuple[float, float]:
    stop = round(entry_price * (1 - SPY_EXPANSION_STOP_PCT), 4)
    target = round(entry_price * (1 + SPY_EXPANSION_TARGET_PCT), 4)
    return stop, target


def spy_expansion_exit_signal(
    entry_price: float, mark: float, minutes_remaining: float, peak_pct: float = 0.0
) -> tuple[str, str]:
    """Same mechanical shape as this system's other %-premium exit models
    (hard stop, target, a one-time-raised breakeven floor, forced flat near
    the close) but its own independently-defined constants - per explicit
    owner choice not to literally call a sibling strategy's exit function."""
    if entry_price <= 0:
        return "HOLD", "no entry price to evaluate against"
    pnl_pct = (mark - entry_price) / entry_price * 100
    stop_floor = (
        SPY_EXPANSION_FLOOR_PCT if peak_pct >= SPY_EXPANSION_FLOOR_TRIGGER_PCT
        else -SPY_EXPANSION_STOP_PCT * 100
    )
    if pnl_pct <= stop_floor:
        if stop_floor > -SPY_EXPANSION_STOP_PCT * 100:
            return "BREAKEVEN STOP", (
                f"peaked at {peak_pct:.0f}%, down to {pnl_pct:.0f}% - protecting the proven "
                f"move instead of risking a full round-trip to the {SPY_EXPANSION_STOP_PCT * 100:.0f}% stop"
            )
        return "STOP OUT", f"down {pnl_pct:.0f}%, past the {SPY_EXPANSION_STOP_PCT * 100:.0f}% stop"
    if pnl_pct >= SPY_EXPANSION_TARGET_PCT * 100:
        return "TAKE PROFIT", f"up {pnl_pct:.0f}%, past the {SPY_EXPANSION_TARGET_PCT * 100:.0f}% target"
    if minutes_remaining <= 15:
        return "EXPANSION EOD CLOSE", "closing ahead of same-day expiration"
    return "HOLD", "no exit condition met"


def scan_spy_expansion_candidates(
    chain: list[dict[str, Any]],
    signal: dict[str, Any],
    expiration: str,
    spot_price: float,
) -> list[dict[str, Any]]:
    """Candidate builder for SPY Expansion-Level - its own delta band and
    risk cap (SPY_EXPANSION_*), independent of SPY_0DTE's and
    SPY_KEY_LEVELS'. signal is a qualified result from spy_expansion_signal
    (side/reference_level_type/reference_level_price already resolved)."""
    kind = signal["side"]
    candidates: list[dict[str, Any]] = []
    for option in chain:
        if option.get("option_type") != kind:
            continue
        if not option_has_liquidity(option):
            continue
        delta = abs(greek(option, "delta") or 0.0)
        if not SPY_EXPANSION_DELTA_MIN <= delta <= SPY_EXPANSION_DELTA_MAX:
            continue
        ask = as_float(option.get("ask"), 0.0) or 0.0
        bid = as_float(option.get("bid"), 0.0) or 0.0
        if ask <= 0:
            continue
        if ask > SPY_EXPANSION_MAX_CONTRACT_ASK or ask * 100 > SPY_EXPANSION_MAX_RISK_PER_TRADE:
            continue
        strike = float(option["strike"])
        max_profit: str | float = "UNLIMITED" if kind == "call" else round(max((strike - ask) * 100, 0), 2)
        breakeven = round(strike + ask if kind == "call" else strike - ask, 2)
        candidates.append(
            {
                "play_type": SPY_EXPANSION_PLAY_TYPE,
                "call_or_put": kind,
                "strike": fmt_strike(strike),
                "expiration": expiration,
                "entry_price": round(ask, 2),
                "cost_or_credit": str(round(ask, 2)),
                "delta": round(delta, 4),
                "theta": round(greek(option, "theta") or 0.0, 4),
                "iv": round(iv_value(option), 4) if iv_value(option) is not None else "",
                "pop": round(delta * 100, 1),
                "max_profit": max_profit,
                "max_risk": round(ask * 100, 2),
                "breakeven": breakeven,
                "open_interest": open_interest_value(option),
                "option_volume": option_volume_value(option),
                "bid_ask_width": round(max(ask - bid, 0), 2),
                "option_symbol": option.get("symbol") or option_symbol(SPY_EXPANSION_TICKER, expiration, kind, strike),
                "spot_at_entry": spot_price,
                "score": round(delta * 100, 1),
                "setup_reason": signal.get("reason", ""),
                "market_regime": signal.get("state", ""),
                "active_level_name": signal.get("reference_level_type", ""),
            }
        )
    candidates.sort(key=lambda c: c["entry_price"])
    return candidates


def rolling_average(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    running = 0.0
    for index, value in enumerate(values):
        running += value
        if index >= period:
            running -= values[index - period]
        output.append(running / period if index + 1 >= period else None)
    return output


def render_market_chart(history: list[dict[str, Any]], spot_price: float) -> None:
    """Render a dependency-free SVG chart that GitHub Pages and browsers can display."""
    points = [
        (str(day.get("date", "")), as_float(day.get("close")), as_float(day.get("volume")))
        for day in history
    ]
    points = [(day, close, volume) for day, close, volume in points if close is not None]
    if len(points) < 20:
        return
    dates = [point[0] for point in points]
    closes = [float(point[1]) for point in points]
    sma20 = rolling_average(closes, 20)
    sma50 = rolling_average(closes, 50)
    chart_width, chart_height = 1120, 560
    left, right, top, bottom = 72, 28, 56, 70
    plot_width = chart_width - left - right
    plot_height = chart_height - top - bottom
    visible_values = closes + [value for value in sma20 + sma50 if value is not None]
    low, high = min(visible_values), max(visible_values)
    padding = max((high - low) * 0.08, 0.10)
    low, high = low - padding, high + padding

    def xy(index: int, value: float) -> tuple[float, float]:
        x = left + (index / max(len(closes) - 1, 1)) * plot_width
        y = top + ((high - value) / max(high - low, 0.01)) * plot_height
        return x, y

    def polyline(values: list[float | None], color: str, width: int) -> str:
        segments: list[list[str]] = []
        current: list[str] = []
        for index, value in enumerate(values):
            if value is None:
                if current:
                    segments.append(current)
                    current = []
                continue
            x, y = xy(index, value)
            current.append(f"{x:.1f},{y:.1f}")
        if current:
            segments.append(current)
        return "".join(
            f'<polyline points="{" ".join(segment)}" fill="none" stroke="{color}" '
            f'stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"/>'
            for segment in segments
        )

    grid: list[str] = []
    for step in range(6):
        value = low + (high - low) * step / 5
        _, y = xy(0, value)
        grid.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{chart_width-right}" y2="{y:.1f}" '
            f'stroke="#243244" stroke-width="1"/>'
            f'<text x="{left-10}" y="{y+4:.1f}" text-anchor="end" fill="#9fb0c3" '
            f'font-size="13">${value:.2f}</text>'
        )
    context = directional_market_context(history, spot_price)
    support = min(closes[-20:])
    resistance = max(closes[-20:])
    display_name = TICKER
    title = html.escape(
        f"{display_name} market map • {dates[-1]} • {context['regime']} • RSI {context['rsi14']:.1f}"
        if context.get("rsi14") is not None
        else f"{display_name} market map • {dates[-1]}"
    )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{chart_width}" height="{chart_height}" viewBox="0 0 {chart_width} {chart_height}">
<rect width="100%" height="100%" fill="#0d1520"/>
<text x="{left}" y="30" fill="#f4f7fb" font-family="Arial,sans-serif" font-size="20" font-weight="700">{title}</text>
{"".join(grid)}
{polyline([float(value) for value in closes], "#f4f7fb", 3)}
{polyline(sma20, "#38bdf8", 2)}
{polyline(sma50, "#f59e0b", 2)}
<text x="{left}" y="{chart_height-34}" fill="#38bdf8" font-family="Arial,sans-serif" font-size="14">SMA20</text>
<text x="{left+72}" y="{chart_height-34}" fill="#f59e0b" font-family="Arial,sans-serif" font-size="14">SMA50</text>
<text x="{left+150}" y="{chart_height-34}" fill="#9fb0c3" font-family="Arial,sans-serif" font-size="14">20-day support ${support:.2f} • resistance ${resistance:.2f}</text>
<text x="{chart_width-right}" y="{chart_height-34}" text-anchor="end" fill="#9fb0c3" font-family="Arial,sans-serif" font-size="12">Decision aid, not financial advice</text>
</svg>"""
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    CHART_PATH.write_text(svg, encoding="utf-8")
    render_market_chart_png(history, spot_price, context, support, resistance, symbol=TICKER)


def render_market_chart_png(
    history: list[dict[str, Any]],
    spot_price: float,
    context: dict[str, Any],
    support: float,
    resistance: float,
    *,
    symbol: str = "F",
    output_path: Path | None = None,
) -> None:
    """Create a Discord-ready PNG screenshot without relying on a browser."""
    from PIL import Image, ImageDraw, ImageFont

    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    if len(closes) < 20:
        return
    sma20 = rolling_average(closes, 20)
    sma50 = rolling_average(closes, 50)
    width, height = 1200, 630
    left, right, top, bottom = 85, 35, 85, 95
    plot_width, plot_height = width - left - right, height - top - bottom
    values = closes + [value for value in sma20 + sma50 if value is not None]
    low, high = min(values), max(values)
    padding = max((high - low) * 0.08, 0.10)
    low, high = low - padding, high + padding
    image = Image.new("RGB", (width, height), "#0d1520")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=15)
    title_font = ImageFont.load_default(size=25)

    def xy(index: int, value: float) -> tuple[int, int]:
        x = left + int(index / max(len(closes) - 1, 1) * plot_width)
        y = top + int((high - value) / max(high - low, 0.01) * plot_height)
        return x, y

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#243244", width=1)
        draw.text((12, y - 9), f"${value:.2f}", fill="#9fb0c3", font=small)

    def draw_series(series: list[float | None], color: str, line_width: int) -> None:
        segment: list[tuple[int, int]] = []
        for index, value in enumerate(series):
            if value is None:
                if len(segment) > 1:
                    draw.line(segment, fill=color, width=line_width, joint="curve")
                segment = []
            else:
                segment.append(xy(index, value))
        if len(segment) > 1:
            draw.line(segment, fill=color, width=line_width, joint="curve")

    draw_series([float(value) for value in closes], "#f4f7fb", 4)
    draw_series(sma20, "#38bdf8", 3)
    draw_series(sma50, "#f59e0b", 3)
    rsi = context.get("rsi14")
    rsi_text = f"{rsi:.1f}" if rsi is not None else "Unavailable"
    display_name = symbol
    draw.text((left, 25), f"{display_name} Market Map | ${spot_price:.2f} | {context['regime']}", fill="#f4f7fb", font=title_font)
    draw.text((left, 55), f"RSI14 {rsi_text} | White: Price | Blue: SMA20 | Orange: SMA50", fill="#9fb0c3", font=small)
    draw.text((left, height - 66), f"20-day support ${support:.2f}  |  resistance ${resistance:.2f}", fill="#dbe7f3", font=font)
    draw.text((left, height - 36), "Decision aid only - not professional financial advice or a profit guarantee", fill="#9fb0c3", font=small)
    destination = output_path or CHART_SCREENSHOT_PATH
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def trade_intraday_history(symbol: str) -> list[dict[str, Any]]:
    """Reuse one five-minute session history across same-ticker lifecycle cards."""
    symbol = symbol.strip().upper()
    cached = INTRADAY_SNAPSHOT_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached[0] < 60:
        return cached[1]
    bars = get_intraday_history(symbol, interval="5min")
    INTRADAY_SNAPSHOT_CACHE[symbol] = (now, bars)
    return bars


def trade_daily_history(symbol: str) -> list[dict[str, Any]]:
    """Reuse daily history for 15 minutes while intraday lifecycle data stays fresh."""
    symbol = symbol.strip().upper()
    cached = DAILY_SNAPSHOT_CACHE.get(symbol)
    now = time.monotonic()
    if cached and now - cached[0] < 900:
        return cached[1]
    bars = get_daily_history(symbol, days=420)
    DAILY_SNAPSHOT_CACHE[symbol] = (now, bars)
    return bars


def render_trade_intraday_snapshot(
    row: dict[str, str],
    event: str,
    bars: list[dict[str, Any]],
) -> Path | None:
    """Render today's five-minute underlying chart for a journal entry or exit."""
    from PIL import Image, ImageDraw, ImageFont

    points: list[tuple[str, float]] = []
    for bar in bars:
        price = as_float(bar.get("close") or bar.get("price"))
        if price is None:
            continue
        label = str(bar.get("time") or bar.get("timestamp") or bar.get("date") or "")
        points.append((label[-8:-3] if len(label) >= 8 else label, price))
    if len(points) < 2:
        return None
    prices = [point[1] for point in points]
    reference = (
        as_float(row.get("entry_price"))
        if event == "entry"
        else as_float(row.get("exit_price") or row.get("last_mark"))
    )
    # The option premium is not comparable with the underlying chart. Use the
    # final underlying bar as the event marker and label the contract premium.
    marker_price = prices[-1]
    width, height = 1200, 630
    left, right, top, bottom = 85, 35, 90, 100
    plot_width, plot_height = width - left - right, height - top - bottom
    low, high = min(prices), max(prices)
    padding = max((high - low) * 0.10, 0.05)
    low, high = low - padding, high + padding
    image = Image.new("RGB", (width, height), "#0d1520")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=15)
    normal = ImageFont.load_default(size=18)
    title_font = ImageFont.load_default(size=25)

    def xy(index: int, value: float) -> tuple[int, int]:
        return (
            left + int(index / max(len(prices) - 1, 1) * plot_width),
            top + int((high - value) / max(high - low, 0.01) * plot_height),
        )

    for step in range(6):
        value = low + (high - low) * step / 5
        y = xy(0, value)[1]
        draw.line((left, y, width - right, y), fill="#243244", width=1)
        draw.text((12, y - 9), f"${value:.2f}", fill="#9fb0c3", font=small)
    draw.line([xy(i, price) for i, price in enumerate(prices)], fill="#f4f7fb", width=4, joint="curve")
    mx, my = xy(len(prices) - 1, marker_price)
    color = "#22c55e" if event == "entry" else "#ef4444"
    draw.ellipse((mx - 8, my - 8, mx + 8, my + 8), fill=color)
    symbol = row.get("ticker") or "Ticker"
    event_label = event.upper()
    draw.text((left, 25), f"{symbol} 5-Minute Session | {event_label} | ${marker_price:.2f} underlying", fill="#f4f7fb", font=title_font)
    draw.text((left, 58), f"{row.get('trade_id')} | {row.get('play_type')} | contract premium {fmt_money(reference)}", fill="#9fb0c3", font=normal)
    draw.text((left, height - 66), f"Session {points[0][0] or 'open'} to {points[-1][0] or 'now'} | marker shows snapshot time", fill="#dbe7f3", font=normal)
    draw.text((left, height - 36), "Paper-trade context only - five-minute bars can omit fast moves and are not execution prices", fill="#9fb0c3", font=small)
    destination = TRADE_SNAPSHOT_DIR / f"{row.get('trade_id', 'trade')}-{event}.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def build_trade_snapshot(row: dict[str, str], event: str) -> Path | None:
    try:
        intraday = trade_intraday_history(row.get("ticker") or TICKER)
        daily = trade_daily_history(row.get("ticker") or TICKER)
        return render_trade_multitimeframe_snapshot(
            row,
            event,
            intraday,
            daily,
        )
    except (TradierError, requests.RequestException, ValueError, OSError) as exc:
        print(f"Could not render {event} snapshot for {row.get('trade_id')}: {exc}", file=sys.stderr)
        return None


def _resample_history(
    bars: list[dict[str, Any]], period: str
) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for bar in bars:
        raw = str(bar.get("date") or bar.get("time") or "")[:10]
        try:
            observed = datetime.fromisoformat(raw).date()
        except ValueError:
            continue
        if period == "weekly":
            year, week, _ = observed.isocalendar()
            key = f"{year}-W{week:02d}"
        else:
            key = observed.strftime("%Y-%m")
        grouped.setdefault(key, []).append(bar)
    output: list[dict[str, Any]] = []
    for key, group in grouped.items():
        closes = [as_float(item.get("close")) for item in group]
        closes = [value for value in closes if value is not None]
        if closes:
            output.append({"date": key, "close": closes[-1]})
    return output


def render_trade_multitimeframe_snapshot(
    row: dict[str, str],
    event: str,
    intraday: list[dict[str, Any]],
    daily: list[dict[str, Any]],
) -> Path | None:
    """Render intraday, daily, weekly, and monthly decision context in one image."""
    from PIL import Image, ImageDraw, ImageFont

    daily_clean = [bar for bar in daily if as_float(bar.get("close")) is not None]
    panels = [
        ("INTRADAY · 5 MIN", intraday[-78:]),
        ("DAILY · 6 MONTHS", daily_clean[-126:]),
        ("WEEKLY · 18 MONTHS", _resample_history(daily_clean, "weekly")[-78:]),
        ("MONTHLY · LONG TREND", _resample_history(daily_clean, "monthly")[-36:]),
    ]
    if not any(len(bars) >= 2 for _, bars in panels):
        return None

    width, height = 1600, 1040
    image = Image.new("RGB", (width, height), "#09111d")
    draw = ImageDraw.Draw(image)
    small = ImageFont.load_default(size=16)
    normal = ImageFont.load_default(size=19)
    title_font = ImageFont.load_default(size=28)
    symbol = str(row.get("ticker") or TICKER).upper()
    style = play_style_key(row).replace("-", " ").title()
    draw.text(
        (45, 24),
        f"{symbol} MULTI-TIMEFRAME TRADE MAP · {event.upper()} · {row.get('trade_id')}",
        fill="#f8fafc",
        font=title_font,
    )
    draw.text(
        (45, 62),
        f"{style} · contract {row.get('strike')} · expiration {format_expiration(row.get('expiration', ''))}",
        fill="#a9bad0",
        font=normal,
    )

    panel_width, panel_height = 735, 375
    origins = [(45, 110), (820, 110), (45, 515), (820, 515)]

    for (label, bars), (origin_x, origin_y) in zip(panels, origins):
        draw.rounded_rectangle(
            (origin_x, origin_y, origin_x + panel_width, origin_y + panel_height),
            radius=14,
            fill="#0f1b2b",
            outline="#26384d",
            width=2,
        )
        values = [as_float(bar.get("close") or bar.get("price")) for bar in bars]
        values = [float(value) for value in values if value is not None]
        draw.text((origin_x + 20, origin_y + 16), label, fill="#e2e8f0", font=normal)
        if len(values) < 2:
            draw.text(
                (origin_x + 20, origin_y + 70),
                "Historical data unavailable for this timeframe.",
                fill="#fbbf24",
                font=normal,
            )
            continue
        left, right = origin_x + 55, origin_x + panel_width - 25
        top, bottom = origin_y + 62, origin_y + panel_height - 70
        low, high = min(values), max(values)
        padding = max((high - low) * 0.10, 0.05)
        low, high = low - padding, high + padding

        def xy(index: int, value: float) -> tuple[int, int]:
            return (
                left + int(index / max(len(values) - 1, 1) * (right - left)),
                top + int((high - value) / max(high - low, 0.01) * (bottom - top)),
            )

        for step in range(5):
            value = low + (high - low) * step / 4
            y = xy(0, value)[1]
            draw.line((left, y, right, y), fill="#203147", width=1)
            draw.text((origin_x + 5, y - 8), f"{value:.2f}", fill="#718399", font=small)
        draw.line([xy(i, value) for i, value in enumerate(values)], fill="#dce7f5", width=3)
        sma20 = rolling_average(values, min(20, max(2, len(values) // 3)))
        sma_points = [xy(i, value) for i, value in enumerate(sma20) if value is not None]
        if len(sma_points) >= 2:
            draw.line(sma_points, fill="#38bdf8", width=2)
        support = min(values[-min(20, len(values)):])
        resistance = max(values[-min(20, len(values)):])
        last = values[-1]
        trend = "ABOVE TREND" if sma20[-1] is not None and last >= sma20[-1] else "BELOW TREND"
        marker_color = "#22c55e" if event == "entry" else "#f59e0b" if event.startswith("hold") else "#ef4444"
        mx, my = xy(len(values) - 1, last)
        draw.ellipse((mx - 7, my - 7, mx + 7, my + 7), fill=marker_color)
        draw.text(
            (origin_x + 20, origin_y + panel_height - 52),
            f"Last ${last:.2f} · Support ${support:.2f} · Resistance ${resistance:.2f} · {trend}",
            fill="#b9c7d8",
            font=small,
        )

    context = directional_market_context(
        daily_clean,
        as_float((daily_clean[-1] if daily_clean else {}).get("close"), 0.0) or 0.0,
        intraday,
    ) if daily_clean else {}
    footer = (
        f"Regime {context.get('regime', 'unavailable')} · RSI14 {round_or_blank(context.get('rsi14'), 1) or '—'} · "
        f"Evidence score {context.get('evidence_score', '—')} · Blue line is rolling trend · "
        "levels require price and option-liquidity confirmation"
    )
    source_timestamp = str((intraday[-1] if intraday else {}).get("time") or (intraday[-1] if intraday else {}).get("timestamp") or now_ct().isoformat())
    draw.text((45, 930), footer, fill="#d7e2ef", font=normal)
    draw.text(
        (45, 976),
        f"Source timestamp {source_timestamp} · timeframes 5m/1d/1w/1mo · generated {now_ct().isoformat(timespec='minutes')} · paper research only.",
        fill="#8193a8",
        font=small,
    )
    safe_event = re.sub(r"[^a-zA-Z0-9_-]+", "-", event).strip("-")
    destination = TRADE_SNAPSHOT_DIR / f"{row.get('trade_id', 'trade')}-{safe_event}-multitimeframe.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)
    return destination


def market_map_text(history: list[dict[str, Any]], spot_price: float) -> str:
    context = directional_market_context(history, spot_price)
    closes = [value for day in history if (value := as_float(day.get("close"))) is not None]
    support = min(closes[-20:]) if closes else spot_price
    resistance = max(closes[-20:]) if closes else spot_price
    rsi_text = f"{context['rsi14']:.1f}" if context.get("rsi14") is not None else "Unavailable"
    display_name = TICKER
    chart_line = f"[Open the current {TICKER} chart]({CHART_PUBLIC_URL})" if CHART_PUBLIC_URL else "Chart saved to the dashboard."
    return "\n".join([
        f"## 📈 {display_name} Market Map",
        "### Trend",
        (
            f"**Regime:** {context['regime']}\n"
            f"**{TICKER}:** ${spot_price:.2f} · **SMA20:** {fmt_money(context.get('sma20'))} · "
            f"**SMA50:** {fmt_money(context.get('sma50'))} · **RSI14:** {rsi_text}"
        ),
        "### Decision Levels",
        f"**20-day support:** ${support:.2f}\n**20-day resistance:** ${resistance:.2f}",
        "### Read",
        f"{context['reason']}. A level break is confirmation only after price and option liquidity agree.",
        "### Chart",
        chart_line,
        "Educational decision support only—not professional financial advice or a profit guarantee.",
    ])


# ---------------------------------------------------------------------------
# CSV state and migration
# ---------------------------------------------------------------------------


def blank_row() -> dict[str, str]:
    return {column: "" for column in LOG_HEADER}


def read_log() -> list[dict[str, str]]:
    if not LOG_PATH.exists():
        return []
    if LOG_PATH.stat().st_size == 0:
        raise RuntimeError(
            f"Trade history {LOG_PATH} is empty; refusing to continue until it is recovered."
        )
    with LOG_PATH.open(newline="", encoding="utf-8") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows = [migrate_row(row) for row in raw_rows]
    assign_missing_trade_ids(rows)
    return rows


def write_log(rows: list[dict[str, str]]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            newline="",
            encoding="utf-8",
            dir=LOG_PATH.parent,
            prefix=f"{LOG_PATH.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            writer = csv.DictWriter(handle, fieldnames=LOG_HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in LOG_HEADER})
            handle.flush()
            os.fsync(handle.fileno())
        # Windows can transiently deny this replace if antivirus or a sync
        # client (this project lives in a OneDrive-synced folder) has the
        # target briefly open for its own read. That's normally gone within
        # a fraction of a second - a short retry survives it instead of
        # crashing whatever was writing the trade log over a lock that was
        # never really contested.
        last_error: PermissionError | None = None
        for attempt in range(5):
            try:
                os.replace(temporary_path, LOG_PATH)
                break
            except PermissionError as exc:
                last_error = exc
                if attempt < 4:
                    time.sleep(0.3)
        else:
            raise last_error
    finally:
        if temporary_path and temporary_path.exists():
            temporary_path.unlink()


def migrate_row(raw: dict[str, Any]) -> dict[str, str]:
    row = blank_row()
    for key, value in raw.items():
        if key in row and value is not None:
            row[key] = str(value)

    row["ticker"] = row.get("ticker") or TICKER
    row["outcome"] = (row.get("outcome") or "OPEN").upper()
    row["entry_price"] = round_or_blank(parse_entry_price(row), 2)
    row["discord_status"] = row.get("discord_status") or row["outcome"]
    row["last_signal"] = row.get("last_signal") or ("HOLD" if row["outcome"] == "OPEN" else row["outcome"])
    row["learning_version"] = row.get("learning_version") or "historical-unversioned"
    row["data_confidence"] = row.get("data_confidence") or (
        "CAPTURED" if row["outcome"] == "OPEN" else "HISTORICAL-PARTIAL"
    )
    if row["outcome"] == "OPEN":
        row["last_mark"] = row.get("last_mark") or round_or_blank(parse_entry_price(row), 2)
        row["current_pl_dollars"] = row.get("current_pl_dollars") or "0"
        row["current_pl_pct"] = row.get("current_pl_pct") or "0"
        row["max_favorable_pct"] = row.get("max_favorable_pct") or "0"
        row["max_adverse_pct"] = row.get("max_adverse_pct") or "0"


    if row["outcome"] in {"WIN", "LOSS", "SCRATCH"}:
        had_exit_price = bool(row.get("exit_price"))
        inferred_exit = exit_price(row)
        if inferred_exit is not None and not row.get("exit_price"):
            row["exit_price"] = round_or_blank(inferred_exit, 2)
        if not row.get("result_price_source"):
            row["result_price_source"] = "TRACKED" if had_exit_price else "RECONSTRUCTED"
        row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 0)
        row["exit_contract_value"] = round_or_blank(exit_contract_value(row), 0)
        row["realized_pl_dollars"] = round_or_blank(realized_pl_dollars(row), 0)

    try:
        if row.get("play_type") == "SPREAD":
            sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
            row["strike"] = format_spread_strike(sell_strike, buy_strike)
            row["short_symbol"] = row.get("short_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], sell_strike
            )
            row["long_symbol"] = row.get("long_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], buy_strike
            )
        elif row.get("strike") and row.get("expiration") and row.get("call_or_put"):
            row["option_symbol"] = row.get("option_symbol") or option_symbol(
                row["ticker"], row["expiration"], row["call_or_put"], float(row["strike"])
            )
    except (ValueError, TypeError):
        pass

    fill_trade_math(row)
    return row


def assign_missing_trade_ids(rows: list[dict[str, str]]) -> None:
    used: set[str] = {row["trade_id"] for row in rows if row.get("trade_id")}
    next_sequence: dict[str, int] = {}
    for row in rows:
        trade_id = row.get("trade_id", "")
        match = re.fullmatch(r"([A-Z0-9.-]+)-(\d{8})-(\d{3,})", trade_id)
        if match:
            prefix, day_key, sequence = match.group(1), match.group(2), int(match.group(3))
            next_sequence[f"{prefix}:{day_key}"] = max(
                next_sequence.get(f"{prefix}:{day_key}", 1), sequence + 1
            )

    for row in rows:
        if row.get("trade_id"):
            continue
        timestamp = parse_iso(row.get("timestamp")) or now_ct()
        day_key = timestamp.strftime("%Y%m%d")
        ticker = re.sub(r"[^A-Z0-9.-]", "", (row.get("ticker") or TICKER).upper()) or TICKER
        sequence_key = f"{ticker}:{day_key}"
        sequence = next_sequence.get(sequence_key, 1)
        candidate = f"{ticker}-{day_key}-{sequence:03d}"
        while candidate in used:
            sequence += 1
            candidate = f"{ticker}-{day_key}-{sequence:03d}"
        row["trade_id"] = candidate
        used.add(candidate)
        next_sequence[sequence_key] = sequence + 1


def next_trade_id(rows: list[dict[str, str]], timestamp: datetime) -> str:
    day_key = timestamp.strftime("%Y%m%d")
    highest = 0
    prefix = re.escape(TICKER)
    pattern = re.compile(rf"{prefix}-{day_key}-(\d+)$")
    for row in rows:
        match = pattern.match(row.get("trade_id", ""))
        if match:
            highest = max(highest, int(match.group(1)))
    return f"{TICKER}-{day_key}-{highest + 1:03d}"


def fill_trade_math(row: dict[str, str]) -> None:
    entry = parse_entry_price(row)
    delta = abs(as_float(row.get("delta_at_entry"), 0.0) or 0.0)
    kind = row.get("call_or_put", "").lower()
    play_type = row.get("play_type", "").upper()

    if play_type == "SPREAD":
        try:
            short_strike, long_strike = parse_spread_strikes(row.get("strike", ""))
        except ValueError:
            return
        width = abs(short_strike - long_strike)
        max_profit = max(entry, 0) * 100
        max_risk = max(width - entry, 0) * 100
        breakeven = short_strike - entry if kind == "put" else short_strike + entry
        row["max_profit"] = row.get("max_profit") or round_or_blank(max_profit, 2)
        row["max_risk"] = row.get("max_risk") or round_or_blank(max_risk, 2)
        row["breakeven"] = row.get("breakeven") or round_or_blank(breakeven, 2)
        row["pop_estimate"] = row.get("pop_estimate") or round_or_blank((1 - delta) * 100, 1)
    else:
        strike = as_float(row.get("strike"))
        if strike is None:
            return
        max_risk = entry * 100
        breakeven = strike + entry if kind == "call" else strike - entry
        row["max_risk"] = row.get("max_risk") or round_or_blank(max_risk, 2)
        if kind == "put":
            row["max_profit"] = row.get("max_profit") or round_or_blank(max((strike - entry) * 100, 0), 2)
        else:
            row["max_profit"] = row.get("max_profit") or "UNLIMITED"
        row["breakeven"] = row.get("breakeven") or round_or_blank(breakeven, 2)
        row["pop_estimate"] = row.get("pop_estimate") or round_or_blank(delta * 100, 1)


def open_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in rows if row.get("outcome") == "OPEN"]


def apply_ticker_exposure_cap(
    eligible: list[dict[str, Any]], rows: list[dict[str, str]], ticker: str
) -> list[dict[str, Any]]:
    """Cap total concurrent open positions on one ticker across every
    trader type combined - regular, swing, and spreads all read overlapping
    signals off the same price data, so several can independently qualify
    the same ticker in the same scan. Taking every one of them concentrates
    risk into a single market view instead of spreading it across genuinely
    different ideas. Best-scored candidates are admitted first; eligible
    must already be sorted by score, descending, before this is called."""
    existing_open_on_ticker = sum(
        1 for row in rows if row.get("outcome") == "OPEN" and row.get("ticker") == ticker
    )
    remaining_capacity = max(0, MAX_OPEN_POSITIONS_PER_TICKER - existing_open_on_ticker)
    return eligible[:remaining_capacity]


def recently_tracked(rows: list[dict[str, str]], candidate: dict[str, Any], now: datetime) -> bool:
    key = (
        TICKER,
        candidate["play_type"],
        candidate["call_or_put"],
        candidate["strike"],
        candidate["expiration"],
    )
    cooldown = timedelta(minutes=REENTRY_COOLDOWN_MINUTES)
    for row in reversed(rows):
        if row_key(row) != key:
            continue
        if row.get("outcome") == "OPEN":
            return True
        event_time = parse_iso(row.get("closed_at")) or parse_iso(row.get("timestamp"))
        if event_time and now - event_time < cooldown:
            return True
    return False


def has_open_position(rows: list[dict[str, str]], play_type: str) -> bool:
    """True if play_type already has ANY open position, regardless of
    strike/expiration/side - recently_tracked only blocks re-entering the
    EXACT same contract, so without this a strategy could stack multiple
    concurrent positions if the underlying moved enough to qualify a
    different strike (confirmed live: SPY_KEY_LEVELS had stacked up to 6
    at once, SPY_0DTE_5M up to 4). Owner: "as long as we do 1 trade at a
    time we have a 500 limit... yes it's per trader not all together, 13
    traders a max of 13 and so on." Each of the 13 live strategies is
    capped at one open trade at a time, independent of every other
    strategy."""
    return any(
        row.get("outcome") == "OPEN" and row.get("play_type") == play_type
        for row in rows
    )


def dedupe_by_play_type(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keeps only the single best-scored candidate per play_type, so a
    scan that finds multiple qualifying strikes for the same strategy in
    one cycle still opens at most one new position for it - has_open_
    position alone only stops a SECOND cycle from stacking on an already-
    open trade, not two candidates from the same strategy both opening in
    the SAME cycle. candidates must already be sorted by score,
    descending."""
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for candidate in candidates:
        play_type = candidate.get("play_type", "")
        if play_type in seen:
            continue
        seen.add(play_type)
        result.append(candidate)
    return result

# ---------------------------------------------------------------------------
# Candidate scan
# ---------------------------------------------------------------------------




def filter_strikes(strikes: list[float], spot: float) -> list[float]:
    low = spot * (1 - STRIKE_BAND_PCT)
    high = spot * (1 + STRIKE_BAND_PCT)
    return sorted(strike for strike in strikes if low <= strike <= high)




def open_interest_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(option.get(key))
        if value is not None and value > 0:
            return int(value)
    greeks = option.get("greeks") or {}
    for key in ("open_interest", "openInterest", "oi"):
        value = as_float(greeks.get(key))
        if value is not None and value > 0:
            return int(value)
    return 0


def option_volume_value(option: dict[str, Any] | None) -> int:
    if not option:
        return 0
    return int(as_float(option.get("volume"), 0.0) or 0)


def option_has_liquidity(option: dict[str, Any]) -> bool:
    bid = as_float(option.get("bid"), 0.0) or 0.0
    ask = as_float(option.get("ask"), 0.0) or 0.0
    open_interest = open_interest_value(option)
    volume = option_volume_value(option)
    midpoint = (bid + ask) / 2 if bid > 0 and ask > 0 else 0
    spread_pct = ((ask - bid) / midpoint) if midpoint > 0 else float("inf")
    return (
        bid > 0
        and ask >= bid
        and open_interest >= MIN_OPEN_INTEREST
        and volume >= MIN_OPTION_VOLUME
        and spread_pct <= MAX_BID_ASK_PCT
    )

def greek(option: dict[str, Any], key: str) -> float | None:
    return as_float((option.get("greeks") or {}).get(key))



def iv_value(option: dict[str, Any] | None) -> float | None:
    if not option:
        return None
    greeks = option.get("greeks") or {}
    for source in (greeks, option):
        for key in (
            "mid_iv",
            "smv_vol",
            "bid_iv",
            "ask_iv",
            "iv",
            "implied_volatility",
            "impliedVolatility",
        ):
            value = as_float(source.get(key))
            if value is not None and value > 0:
                return value
    return None






def save_chain_snapshot(
    row: dict[str, str], all_candidates: list[dict[str, Any]], timestamp: datetime
) -> None:
    """Records what the qualifying candidates actually looked like at the
    moment this specific trade was entered - the chosen contract plus every
    other one that also qualified in the same scan, so a strike or
    expiration that would have done better isn't lost the moment this
    contract expires. Purely a recording step: any failure here must never
    block or alter the trade itself, only mean this one snapshot is
    missing."""
    try:
        CHAIN_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "trade_id": row.get("trade_id"),
            "recorded_at": timestamp.isoformat(),
            "ticker": row.get("ticker"),
            "chosen": {
                "play_type": row.get("play_type"),
                "call_or_put": row.get("call_or_put"),
                "strike": row.get("strike"),
                "expiration": row.get("expiration"),
                "entry_price": row.get("entry_price"),
                "delta_at_entry": row.get("delta_at_entry"),
                "iv_at_entry": row.get("iv_at_entry"),
                "setup_score": row.get("setup_score"),
            },
            "other_candidates_this_cycle": [
                {
                    "play_type": c.get("play_type"),
                    "call_or_put": c.get("call_or_put"),
                    "strike": c.get("strike"),
                    "expiration": c.get("expiration"),
                    "entry_price": c.get("entry_price"),
                    "delta": c.get("delta"),
                    "score": c.get("score"),
                }
                for c in all_candidates
                if str(c.get("strike")) != row.get("strike") or c.get("expiration") != row.get("expiration")
            ],
        }
        destination = CHAIN_SNAPSHOT_DIR / f"{row.get('trade_id', 'trade')}.json"
        destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    except Exception as exc:
        print(f"Could not save chain snapshot for {row.get('trade_id')}: {exc}", file=sys.stderr)


def candidate_to_row(
    candidate: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_condition: str = "",
) -> dict[str, str]:
    row = blank_row()
    row.update(
        {
            "trade_id": next_trade_id(rows, timestamp),
            "timestamp": timestamp.isoformat(),
            "action": "SELL open" if candidate["play_type"] == "SPREAD" else "BUY open",
            "play_type": candidate["play_type"],
            "ticker": TICKER,
            "call_or_put": candidate["call_or_put"],
            "strike": candidate["strike"],
            "expiration": candidate["expiration"],
            "option_symbol": candidate.get("option_symbol", ""),
            "short_symbol": candidate.get("short_symbol", ""),
            "long_symbol": candidate.get("long_symbol", ""),
            "cost_or_credit": candidate["cost_or_credit"],
            "entry_price": round_or_blank(as_float(candidate["entry_price"]), 2),
            "delta_at_entry": str(candidate["delta"]),
            "theta_at_entry": str(candidate["theta"]),
            "iv_at_entry": "" if candidate.get("iv") in (None, "") else str(candidate["iv"]),
            "pop_estimate": str(candidate["pop"]),
            "max_profit": str(candidate["max_profit"]),
            "max_risk": str(candidate["max_risk"]),
            "breakeven": str(candidate["breakeven"]),
            "open_interest_at_entry": str(candidate["open_interest"]),
            "bid_ask_width_at_entry": str(candidate["bid_ask_width"]),
            "option_volume_at_entry": str(candidate.get("option_volume", "")),
            "setup_score": round_or_blank(as_float(candidate.get("score")), 1),
            "setup_reason": str(candidate.get("setup_reason", "")),
            "market_regime": str(candidate.get("market_regime", "")),
            "market_condition_at_entry": market_condition,
            "thesis": (
                f"{candidate['play_type'].lower()} {candidate['call_or_put'].lower()} on {TICKER}: "
                f"{candidate.get('setup_reason') or 'controlled scanner qualification'}"
                + (f"; {candidate['breakeven_moves_note']}" if candidate.get("breakeven_moves_note") else "")
            ),
            "entry_confirmation": str(candidate.get("setup_reason") or "Controlled scanner filters passed."),
            "invalidation": (
                f"Exit when the monitored contract reaches its stored stop or the underlying "
                f"{candidate.get('market_regime') or 'entry'} regime no longer supports the position."
            ),
            "risk_plan": (
                f"One paper contract; max modeled risk {fmt_money(as_float(candidate.get('max_risk')))}; "
                "no averaging down; lifecycle monitor owns target/stop exits."
            ),
            "learning_plan": (
                "Apply price action, technical confirmation, option liquidity, Greeks, volatility, "
                "position risk, execution, and post-trade journaling lessons to this trade."
            ),
            "evidence_limitations": (
                "Only evidence captured at entry is treated as fact; unavailable indicators remain unavailable."
            ),
            "learning_version": trade_intelligence.learning_version(),
            "data_confidence": "CAPTURED",
            "outcome": "OPEN",
            "last_mark": str(candidate["entry_price"]),
            "current_pl_dollars": "0",
            "current_pl_pct": "0",
            "max_favorable_pct": "0",
            "max_adverse_pct": "0",
            "last_signal": "HOLD",
            "last_evaluated_at": timestamp.isoformat(),
            "discord_status": "OPEN",
            # SPY Key-Levels only - blank string (harmless, matches
            # blank_row()'s default) for every other play type that
            # doesn't set these candidate keys.
            "underlying_entry_price": round_or_blank(as_float(candidate.get("underlying_entry_price")), 2),
            "underlying_stop_price": round_or_blank(as_float(candidate.get("underlying_stop_price")), 2),
            "underlying_target_price": round_or_blank(as_float(candidate.get("underlying_target_price")), 2),
            "active_level_name": str(candidate.get("active_level_name", "")),
            "expiration_tier": str(candidate.get("expiration_tier", "")),
        }
    )
    return row

# ---------------------------------------------------------------------------
# Open-play evaluation
# ---------------------------------------------------------------------------



def refresh_open_entry_market_data(
    rows: list[dict[str, str]],
    quotes: dict[str, dict[str, Any]],
) -> int:
    """Fill legacy missing IV/OI from the latest live quote without overwriting valid entry data."""
    updated = 0
    for row in open_rows(rows):
        oi = int(as_float(row.get("open_interest_at_entry"), 0.0) or 0)
        iv = as_float(row.get("iv_at_entry"))
        replacement_oi = 0
        replacement_iv: float | None = None

        if row.get("play_type") == "SPREAD":
            short_quote = quotes.get(row.get("short_symbol", ""))
            long_quote = quotes.get(row.get("long_symbol", ""))
            short_oi = open_interest_value(short_quote)
            long_oi = open_interest_value(long_quote)
            if short_oi > 0 and long_oi > 0:
                replacement_oi = min(short_oi, long_oi)
            replacement_iv = iv_value(short_quote)
        else:
            quote = quotes.get(row.get("option_symbol", ""))
            replacement_oi = open_interest_value(quote)
            replacement_iv = iv_value(quote)

        if oi <= 0 and replacement_oi > 0:
            row["open_interest_at_entry"] = str(replacement_oi)
            updated += 1
        if (iv is None or iv <= 0) and replacement_iv is not None and replacement_iv > 0:
            row["iv_at_entry"] = round_or_blank(replacement_iv, 4)
            updated += 1
    return updated


def symbols_for_rows(rows: list[dict[str, str]]) -> list[str]:
    symbols: list[str] = []
    for row in rows:
        symbols.append(row.get("ticker", ""))
        if row.get("play_type") == "SPREAD":
            symbols.extend([row.get("short_symbol", ""), row.get("long_symbol", "")])
        else:
            symbols.append(row.get("option_symbol", ""))
    return list(dict.fromkeys(symbol for symbol in symbols if symbol))


EXIT_MAX_BID_ASK_PCT = float(os.environ.get(
    "EXIT_MAX_BID_ASK_PCT", configured("exit_max_bid_ask_pct", 0.60)
))


def quote_is_reliable_for_exit(quote: dict[str, Any]) -> bool:
    """Entry has a liquidity/spread gate (option_has_liquidity); nothing
    re-checked that once a position was open. A contract that was liquid at
    entry can go dead by the time it's marked to close, and
    conservative_option_exit blindly trusted whatever bid came back no
    matter how wide the spread around it - which is exactly how a real
    -10% underlying-implied loss got marked and closed as -77% (CLF) and
    -98% (NIO): a thin, essentially un-traded bid quote taken at face value
    instead of being recognized as unreliable. Wider than normal at exit is
    expected and fine - full-blown implausible is not."""
    bid = as_float(quote.get("bid"), 0.0) or 0.0
    ask = as_float(quote.get("ask"), 0.0) or 0.0
    if bid <= 0 or ask <= 0:
        return True
    midpoint = (bid + ask) / 2
    spread_pct = ((ask - bid) / midpoint) if midpoint > 0 else float("inf")
    return spread_pct <= EXIT_MAX_BID_ASK_PCT


def conservative_option_exit(quote: dict[str, Any]) -> float:
    bid = as_float(quote.get("bid"), 0.0) or 0.0
    ask = as_float(quote.get("ask"), 0.0) or 0.0
    last = as_float(quote.get("last"), 0.0) or 0.0
    if bid > 0:
        return bid
    if bid >= 0 and ask > 0:
        return (bid + ask) / 2
    return last






def evaluate_open_spy_key_levels_row(
    row: dict[str, str],
    quotes: dict[str, dict[str, Any]],
    timestamp: datetime,
    underlying_spot_price: float | None,
) -> dict[str, Any]:
    """SPY Key-Levels exit: still marks/reports P&L off the real option
    premium quote like every other play type (that's what realized money
    actually is), but the exit TRIGGER is the underlying-price-level stop/
    target stored on the row at entry, not a % of premium. Independent of
    evaluate_open_row's SPY_0DTE branch entirely."""
    entry = parse_entry_price(row)
    quote = quotes.get(row.get("option_symbol", ""))
    if not quote or not quote_is_reliable_for_exit(quote):
        return {
            "signal": "HOLD",
            "note": "Live option quote unavailable; showing last tracked values.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    if underlying_spot_price is None:
        return {
            "signal": "HOLD",
            "note": "SPY spot price unavailable; cannot evaluate the underlying-level stop/target.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    mark = conservative_option_exit(quote)
    stop_underlying = as_float(row.get("underlying_stop_price"))
    target_underlying = as_float(row.get("underlying_target_price"))
    expiration_tier = row.get("expiration_tier") or "0DTE"
    is_expiration_day = row.get("expiration") == timestamp.date().isoformat()
    close_time = timestamp.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    # Computed before the exit-signal call (not after, like the original
    # version) - the premium-based backstop/floor checks inside
    # spy_key_levels_exit_signal need pnl_pct/peak_pct to evaluate
    # against, on top of the underlying-level read.
    pnl_pct = ((mark - entry) / entry * 100) if entry else 0.0
    previous_peak = as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct
    peak_pct = max(previous_peak, pnl_pct)
    row["max_favorable_pct"] = round_or_blank(peak_pct, 0)
    if stop_underlying is None or target_underlying is None:
        signal, exit_note = "EXPIRATION CLOSE", "fallback: forced close (missing stored stop/target level)"
    else:
        try:
            signal, exit_note = spy_key_levels_exit_signal(
                side=row.get("call_or_put", "call"),
                stop_underlying_price=stop_underlying,
                target_underlying_price=target_underlying,
                current_underlying_price=underlying_spot_price,
                expiration_tier=expiration_tier,
                is_expiration_day=is_expiration_day,
                minutes_remaining=minutes_remaining,
                pnl_pct=pnl_pct,
                peak_pct=peak_pct,
            )
        except Exception as exc:
            print(f"spy_key_levels_exit_signal errored, forcing EOD close: {exc}", file=sys.stderr)
            signal = "EXPIRATION CLOSE"
            exit_note = "fallback: forced close (smart exit errored)"
    rounded_mark = round(mark, 2)
    rounded_pnl = rounded_mark - entry
    rounded_pnl_pct = (rounded_pnl / entry * 100) if entry else 0.0
    result = {
        "signal": signal,
        "mark": rounded_mark,
        "pl_dollars": round(rounded_pnl * 100),
        "pl_pct": round(rounded_pnl_pct),
        "delta": greek(quote, "delta"),
        "theta": greek(quote, "theta"),
        "iv": iv_value(quote),
        "minutes_remaining": round(minutes_remaining),
        "exit_note": exit_note,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result


def evaluate_open_spy_expansion_row(
    row: dict[str, str], quotes: dict[str, dict[str, Any]], timestamp: datetime
) -> dict[str, Any]:
    """SPY Expansion-Level exit: same %-of-premium shape as SPY_0DTE's own
    evaluator, but calls spy_expansion_exit_signal with its own independent
    constants - never spy_0dte_exit_signal. Independent of evaluate_open_row's
    SPY_0DTE/SPY_KEY_LEVELS branches entirely."""
    entry = parse_entry_price(row)
    quote = quotes.get(row.get("option_symbol", ""))
    if not quote or not quote_is_reliable_for_exit(quote):
        return {
            "signal": "HOLD",
            "note": "Live option quote unavailable; showing last tracked values.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    mark = conservative_option_exit(quote)
    pnl_pct = ((mark - entry) / entry * 100) if entry else 0.0
    previous_peak = as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct
    peak_pct = max(previous_peak, pnl_pct)
    close_time = timestamp.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    try:
        signal, exit_note = spy_expansion_exit_signal(entry, mark, minutes_remaining, peak_pct)
    except Exception as exc:
        print(f"spy_expansion_exit_signal errored, forcing EOD close: {exc}", file=sys.stderr)
        signal = "EXPANSION EOD CLOSE"
        exit_note = "fallback: forced close (smart exit errored)"
    row["max_favorable_pct"] = round_or_blank(peak_pct, 0)
    rounded_mark = round(mark, 2)
    rounded_pnl = rounded_mark - entry
    rounded_pnl_pct = (rounded_pnl / entry * 100) if entry else 0.0
    result = {
        "signal": signal,
        "mark": rounded_mark,
        "pl_dollars": round(rounded_pnl * 100),
        "pl_pct": round(rounded_pnl_pct),
        "delta": greek(quote, "delta"),
        "theta": greek(quote, "theta"),
        "iv": iv_value(quote),
        "minutes_remaining": round(minutes_remaining),
        "exit_note": exit_note,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result


def evaluate_open_spy_ratchet_row(
    row: dict[str, str], quotes: dict[str, dict[str, Any]], timestamp: datetime
) -> dict[str, Any]:
    """Ratchet-floor SPY variants: same %-of-premium shape as SPY_0DTE's own
    evaluator, but calls spy_ratchet_exit_signal with the row's own
    play_type's (step_pct, stop_pct) from SPY_RATCHET_VARIANT_BY_PLAY_TYPE -
    never spy_0dte_exit_signal. Independent of evaluate_open_row's SPY_0DTE/
    SPY_KEY_LEVELS/SPY_EXPANSION branches entirely."""
    entry = parse_entry_price(row)
    quote = quotes.get(row.get("option_symbol", ""))
    if not quote or not quote_is_reliable_for_exit(quote):
        return {
            "signal": "HOLD",
            "note": "Live option quote unavailable; showing last tracked values.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    mark = conservative_option_exit(quote)
    pnl_pct = ((mark - entry) / entry * 100) if entry else 0.0
    previous_peak = as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct
    peak_pct = max(previous_peak, pnl_pct)
    close_time = timestamp.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0)
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    variant = SPY_RATCHET_VARIANT_BY_PLAY_TYPE.get(row.get("play_type"))
    try:
        if variant is None:
            raise KeyError(f"unknown ratchet play_type {row.get('play_type')!r}")
        signal, exit_note = spy_ratchet_exit_signal(
            entry, mark, minutes_remaining, peak_pct, variant["step_pct"], variant["stop_pct"]
        )
    except Exception as exc:
        print(f"spy_ratchet_exit_signal errored, forcing EOD close: {exc}", file=sys.stderr)
        signal = "RATCHET EOD CLOSE"
        exit_note = "fallback: forced close (smart exit errored)"
    row["max_favorable_pct"] = round_or_blank(peak_pct, 0)
    rounded_mark = round(mark, 2)
    rounded_pnl = rounded_mark - entry
    rounded_pnl_pct = (rounded_pnl / entry * 100) if entry else 0.0
    result = {
        "signal": signal,
        "mark": rounded_mark,
        "pl_dollars": round(rounded_pnl * 100),
        "pl_pct": round(rounded_pnl_pct),
        "delta": greek(quote, "delta"),
        "theta": greek(quote, "theta"),
        "iv": iv_value(quote),
        "minutes_remaining": round(minutes_remaining),
        "exit_note": exit_note,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result


def evaluate_open_new_strategy_row(
    row: dict[str, str], quotes: dict[str, dict[str, Any]], timestamp: datetime
) -> dict[str, Any]:
    """Exit evaluator for the 14 strategies promoted from the locked top 15.

    Same %-of-premium shape every live strategy uses, but calls
    spy_live_new_strategies.new_strategy_exit_signal - a wider target and
    deeper stop than the retired 0DTE +50/-50, which Phase 5 measured
    losing money on every strategy tested."""
    import spy_live_new_strategies as lns

    entry = parse_entry_price(row)
    quote = quotes.get(row.get("option_symbol", ""))
    if not quote or not quote_is_reliable_for_exit(quote):
        return {
            "signal": "HOLD",
            "note": "Live option quote unavailable; showing last tracked values.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    mark = conservative_option_exit(quote)
    pnl_pct = ((mark - entry) / entry * 100) if entry else 0.0
    previous_peak = as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct
    peak_pct = max(previous_peak, pnl_pct)
    close_time = timestamp.replace(hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1],
                                   second=0, microsecond=0)
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    # How long this position has been open, so a strategy with a measured
    # time stop can actually use it.
    minutes_held: float | None = None
    opened = row.get("timestamp") or row.get("entry_timestamp")
    if opened:
        try:
            opened_at = datetime.fromisoformat(str(opened))
            minutes_held = max((timestamp - opened_at).total_seconds() / 60, 0)
        except (TypeError, ValueError):
            minutes_held = None

    try:
        signal, exit_note = lns.new_strategy_exit_signal(
            entry, mark, minutes_remaining, peak_pct,
            play_type=row.get("play_type"), minutes_held=minutes_held,
        )
    except Exception as exc:
        print(f"new_strategy_exit_signal errored, forcing EOD close: {exc}", file=sys.stderr)
        signal, exit_note = "EOD CLOSE", "fallback: forced close (smart exit errored)"
    row["max_favorable_pct"] = round_or_blank(peak_pct, 0)
    rounded_mark = round(mark, 2)
    rounded_pnl = rounded_mark - entry
    rounded_pnl_pct = (rounded_pnl / entry * 100) if entry else 0.0
    result = {
        "signal": signal,
        "mark": rounded_mark,
        "pl_dollars": round(rounded_pnl * 100),
        "pl_pct": round(rounded_pnl_pct),
        "delta": greek(quote, "delta"),
        "theta": greek(quote, "theta"),
        "iv": iv_value(quote),
        "minutes_remaining": round(minutes_remaining),
        "exit_note": exit_note,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result


def evaluate_open_row(
    row: dict[str, str],
    quotes: dict[str, dict[str, Any]],
    timestamp: datetime,
    *,
    underlying_spot_price: float | None = None,
) -> dict[str, Any]:
    entry = parse_entry_price(row)
    play_type = row.get("play_type")

    if play_type == SPY_KEY_LEVELS_PLAY_TYPE:
        return evaluate_open_spy_key_levels_row(row, quotes, timestamp, underlying_spot_price)

    if play_type == SPY_EXPANSION_PLAY_TYPE:
        return evaluate_open_spy_expansion_row(row, quotes, timestamp)

    if is_spy_ratchet_play_type(play_type):
        return evaluate_open_spy_ratchet_row(row, quotes, timestamp)

    import spy_live_new_strategies as _lns
    if _lns.is_new_strategy_play_type(play_type):
        return evaluate_open_new_strategy_row(row, quotes, timestamp)

    if not is_spy_0dte_play_type(play_type):
        # Every play type this system opens is one of the two independently
        # tracked SPY 0DTE strategies, a manually-forced entry (SPY_MANUAL -
        # see /force-trade, which shares this exact exit rule "based off the
        # trader's rules" per owner direction), or SPY Key-Levels / SPY
        # Expansion-Level (handled above) - anything else (including the
        # bare "SPY_0DTE" from before the 1m/5m split) is a historical row
        # from a retired strategy and has nothing live to evaluate against.
        return {
            "signal": "HOLD",
            "note": f"Unrecognized or retired play_type {play_type!r}; nothing to evaluate.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }

    quote = quotes.get(row.get("option_symbol", ""))
    if not quote or not quote_is_reliable_for_exit(quote):
        return {
            "signal": "HOLD",
            "note": "Live option quote unavailable; showing last tracked values.",
            "mark": as_float(row.get("last_mark"), entry),
            "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
            "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        }
    mark = conservative_option_exit(quote)
    pnl_pct = ((mark - entry) / entry * 100) if entry else 0.0
    previous_peak = as_float(row.get("max_favorable_pct"), pnl_pct) or pnl_pct
    peak_pct = max(previous_peak, pnl_pct)
    close_time = timestamp.replace(
        hour=MARKET_CLOSE[0], minute=MARKET_CLOSE[1], second=0, microsecond=0
    )
    minutes_remaining = max((close_time - timestamp).total_seconds() / 60, 0)
    try:
        signal, exit_note = spy_0dte_exit_signal(entry, mark, minutes_remaining, peak_pct)
    except Exception as exc:
        print(f"spy_0dte_exit_signal errored, forcing EOD close: {exc}", file=sys.stderr)
        signal = "EOD CLOSE"
        exit_note = "fallback: forced close (smart exit errored) - 0DTE never holds overnight"
    row["max_favorable_pct"] = round_or_blank(peak_pct, 0)
    details = {
        "delta": greek(quote, "delta"),
        "theta": greek(quote, "theta"),
        "iv": iv_value(quote),
        "minutes_remaining": round(minutes_remaining),
        "exit_note": exit_note,
    }

    # Derive the reported dollars/percent from the same rounded mark that
    # gets stored and later re-derived from in close_row, rather than from
    # the raw unrounded mark - conservative_option_exit can return a
    # sub-cent midpoint (e.g. 0.015 when bid=0), and rounding that before
    # vs after the *100 contract multiplier can land on a different dollar
    # figure. Without this, the P&L Discord announces at close time (which
    # prefers this live evaluation) can disagree with the number actually
    # stored and summed into performance totals for the same trade.
    rounded_mark = round(mark, 2)
    rounded_pnl = rounded_mark - entry
    rounded_pnl_pct = (rounded_pnl / entry * 100) if entry else 0.0

    result = {
        "signal": signal,
        "mark": rounded_mark,
        "pl_dollars": round(rounded_pnl * 100),
        "pl_pct": round(rounded_pnl_pct),
        **details,
    }
    apply_evaluation_to_row(row, result, timestamp)
    return result



def apply_evaluation_to_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> None:
    pnl_pct = as_float(evaluation.get("pl_pct"))
    row["last_evaluated_at"] = timestamp.isoformat()
    row["last_signal"] = evaluation.get("signal", "HOLD")
    row["last_mark"] = round_or_blank(as_float(evaluation.get("mark")), 2)
    row["current_pl_dollars"] = round_or_blank(as_float(evaluation.get("pl_dollars")), 0)
    row["current_pl_pct"] = round_or_blank(pnl_pct, 0)

    if pnl_pct is not None:
        current_mfe = as_float(row.get("max_favorable_pct"), 0.0) or 0.0
        current_mae = as_float(row.get("max_adverse_pct"), 0.0) or 0.0
        row["max_favorable_pct"] = round_or_blank(max(current_mfe, pnl_pct), 0)
        row["max_adverse_pct"] = round_or_blank(min(current_mae, pnl_pct), 0)


def close_row(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> str:
    tracked_exit = as_float(evaluation.get("mark"))
    tracked_exit = None if tracked_exit is None else round(tracked_exit, 2)
    entry = parse_entry_price(row)

    if tracked_exit is None:
        realized = round(as_float(evaluation.get("pl_dollars"), 0.0) or 0.0)
    else:
        realized = round((tracked_exit - entry) * 100)

    pnl_pct = (realized / (entry * 100) * 100) if entry else 0.0
    # Outcome always reflects the actual realized result, never the signal
    # name alone. A signal describes which rule fired the exit, not whether
    # money was actually made - trusting the name let a real loss get
    # recorded as a WIN when price moved between checks. This must stay
    # unconditional so no future signal name can reintroduce that gap.
    outcome = "WIN" if pnl_pct > 0 else "LOSS"

    row["outcome"] = outcome
    row["pct_gain_loss"] = round_or_blank(pnl_pct, 0)
    row["exit_price"] = round_or_blank(tracked_exit, 2)
    row["entry_contract_value"] = round_or_blank(entry_contract_value(row), 0)
    row["exit_contract_value"] = round_or_blank(
        None if tracked_exit is None else tracked_exit * 100,
        0,
    )
    row["realized_pl_dollars"] = round_or_blank(realized, 0)
    row["result_price_source"] = "TRACKED"
    row["closed_at"] = timestamp.isoformat()
    row["discord_status"] = outcome
    trade_intelligence.record_event(
        row,
        "exit-decision",
        timestamp.isoformat(),
        observed_at=timestamp.isoformat(),
        extra={"evaluation": evaluation},
    )
    return outcome


CARD_COLORS = {
    "entry": 0x3498DB,
    "qualified": 0x9B59B6,
    "hold": 0xF1C40F,
    "win": 0x2ECC71,
    "loss": 0xE74C3C,
    "scratch": 0x95A5A6,
    "scanner": 0x00A8E8,
    "performance": 0x5865F2,
    "error": 0xE74C3C,
    "status": 0x607D8B,
}



def card_color_for_text(content: str) -> int:
    title = next((line for line in content.splitlines() if line.strip()), content).upper()
    if "ERROR" in title or "FAILED" in title or "🚨" in title:
        return CARD_COLORS["error"]
    if "QUALIFIED" in title:
        return CARD_COLORS["qualified"]
    if "ENTRY" in title:
        return CARD_COLORS["entry"]
    if "· WIN" in title or "WINS SUMMARY" in title or "🏆" in title or "🟩" in title:
        return CARD_COLORS["win"]
    if "· LOSS" in title or "LOSSES SUMMARY" in title or "🟥" in title:
        return CARD_COLORS["loss"]
    if "SCRATCH" in title:
        return CARD_COLORS["scratch"]
    if "HOLD" in title or "POSITION" in title:
        return CARD_COLORS["hold"]
    if "SCAN" in title:
        return CARD_COLORS["scanner"]
    if "PERFORMANCE" in title or "STRATEGY" in title or "REPORT" in title or "RECAP" in title:
        return CARD_COLORS["performance"]
    return CARD_COLORS["status"]

def discord_card(content: str, *, footer_suffix: str = "") -> dict[str, Any]:
    """Convert scanner markdown into a native Discord embed card.

    footer_suffix appends a searchable identifier (a trade_id) to the
    footer text. Per-trade cards (entry/position/result) render only a
    human sequence label like "SPY #4" in their visible title, never the
    raw trade_id - so search_token-based lookups (used both to find an
    existing card to update and, in delete_trade_message's fallback path,
    to find a card to delete once its tracked message-id is lost) can
    never match on trade_id without this. The footer is real embed text
    Discord renders (small, at the bottom) so it's genuinely searchable,
    not a comment that gets thrown away."""
    raw_lines = [line.rstrip() for line in content.strip().splitlines()]
    title = "Tradysquids TradeBot"
    description_lines: list[str] = []
    fields: list[dict[str, Any]] = []
    current_name = ""
    current_value: list[str] = []

    def flush_field() -> None:
        nonlocal current_name, current_value
        if not current_name:
            return
        value = "\n".join(current_value).strip() or "—"
        fields.append({
            "name": current_name[:256],
            "value": value[:1024],
            "inline": False,
        })
        current_name = ""
        current_value = []

    for line in raw_lines:
        if line.startswith("## ") and title == "Tradysquids TradeBot":
            title = line[3:].strip()
            continue
        if line.startswith("# ") and title == "Tradysquids TradeBot":
            title = line[2:].strip()
            continue
        if line.startswith("### "):
            flush_field()
            current_name = line[4:].strip()
            continue
        if current_name:
            current_value.append(line)
        else:
            description_lines.append(line)
    flush_field()

    description = "\n".join(description_lines).strip()
    footer_text = f"Tradysquids TradeBot · Card format {DISCORD_FORMAT_VERSION}"
    if footer_suffix:
        footer_text = f"{footer_text} · {footer_suffix}"
    embed: dict[str, Any] = {
        "title": title[:256],
        "color": card_color_for_text(content),
        "footer": {"text": footer_text[:2048]},
    }
    if description:
        embed["description"] = description[:4096]
    if fields:
        embed["fields"] = fields[:25]
    return embed


def message_search_text(message: dict[str, Any]) -> str:
    parts = [str(message.get("content") or "")]
    for embed in message.get("embeds") or []:
        parts.append(str(embed.get("title") or ""))
        parts.append(str(embed.get("description") or ""))
        for field in embed.get("fields") or []:
            parts.append(str(field.get("name") or ""))
            parts.append(str(field.get("value") or ""))
        parts.append(str((embed.get("footer") or {}).get("text") or ""))
    return "\n".join(parts)


class DiscordError(RuntimeError):
    pass


def discord_route_is_missing(exc: Exception) -> bool:
    message = str(exc)
    return "HTTP 403" in message or "HTTP 404" in message or "Missing Access" in message


class DiscordTracker:
    API_BASE = "https://discord.com/api/v10"
    _discovery_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _discovery_lock = threading.Lock()
    _discovery_ttl_seconds = 300.0

    def __init__(self, token: str, guild_id: str):
        self.token = token
        self.guild_id = guild_id
        self.ready = False
        self.channels: dict[str, str] = {}
        self.tag_ids: dict[str, str] = {}
        self.forum_id = ""
        self.missing_channels: list[str] = []
        self.private_system_channels: set[str] = set()
        self._channel_message_cache: dict[str, list[dict[str, Any]]] = {}

    @property
    def enabled(self) -> bool:
        return bool(self.token and self.guild_id)

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        if not self.enabled:
            raise DiscordError("Discord bot token or guild ID is missing")
        headers = {
            "Authorization": f"Bot {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
        }
        url = f"{self.API_BASE}{path}"
        for attempt in range(4):
            try:
                response = SESSION.request(method, url, headers=headers, json=payload, timeout=20)
            except requests.RequestException as exc:
                if attempt == 3:
                    raise DiscordError(f"Discord request failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429:
                try:
                    retry_after = float(response.json().get("retry_after", 1.0))
                except (ValueError, TypeError):
                    retry_after = 1.0
                # Discord can impose a guild-wide cooldown longer than ten
                # seconds during chart/card bursts.  Sleeping for less than
                # the advertised window only burns every retry immediately.
                time.sleep(min(max(retry_after, 0.0) + 0.25, 65))
                continue
            if response.status_code >= 500 and attempt < 3:
                time.sleep(2**attempt)
                continue
            if not response.ok:
                body = response.text[:700].replace(self.token, "[REDACTED]")
                raise DiscordError(f"Discord HTTP {response.status_code} for {path}: {body}")
            if response.status_code == 204 or not response.content:
                return None
            return response.json()
        raise DiscordError(f"Discord rate limit retries exhausted for {path}")

    def discover(self) -> None:
        if not self.enabled:
            return
        now = time.monotonic()
        with self._discovery_lock:
            cached = self._discovery_cache.get(self.guild_id)
        if cached and now - cached[0] < self._discovery_ttl_seconds:
            guild_channels = cached[1]
        else:
            guild_channels = self._request("GET", f"/guilds/{self.guild_id}/channels")
            with self._discovery_lock:
                self._discovery_cache[self.guild_id] = (now, guild_channels)
        by_name: dict[str, dict[str, Any]] = {}
        for channel in guild_channels:
            name = channel.get("name")
            if name and name.lower() not in by_name:
                by_name[name.lower()] = channel

        forum = next(
            (channel for channel in guild_channels
             if channel.get("name", "").lower() == CHANNEL_NAMES["forum"] and channel.get("type") == 15),
            None,
        )
        if not forum:
            raise DiscordError(
                "Could not find a Discord forum channel named 'trade-journal'. "
                "Confirm it is a Forum channel, not a normal text channel."
            )
        self.forum_id = forum["id"]

        for key, channel_name in CHANNEL_NAMES.items():
            channel = by_name.get(channel_name)
            if channel:
                self.channels[key] = channel["id"]

        channel_by_id = {str(channel.get("id")): channel for channel in guild_channels}

        def denies_everyone_view(channel: dict[str, Any] | None) -> bool:
            if not channel:
                return False
            for overwrite in channel.get("permission_overwrites") or []:
                if str(overwrite.get("id")) != self.guild_id or int(overwrite.get("type", -1)) != 0:
                    continue
                deny = int(overwrite.get("deny", 0))
                return bool(deny & 1024)  # VIEW_CHANNEL
            return False

        for key in SYSTEM_CHANNEL_KEYS:
            channel = by_name.get(CHANNEL_NAMES[key])
            parent = channel_by_id.get(str(channel.get("parent_id"))) if channel else None
            if denies_everyone_view(channel) or denies_everyone_view(parent):
                self.private_system_channels.add(key)

        for tag in forum.get("available_tags") or []:
            normalized = normalized_name(tag.get("name", ""))
            for key in TAG_KEYS:
                if normalized == key or normalized.endswith(f" {key}") or key in normalized:
                    self.tag_ids.setdefault(key, tag["id"])

        missing_tags = sorted(key for key in ("OPEN", "HOLDING", "WIN", "LOSS", "SCRATCH") if key not in self.tag_ids)
        if missing_tags:
            raise DiscordError(f"Missing required trade-journal forum tags: {', '.join(missing_tags)}")
        # CHANNEL_NAMES.get, not CHANNEL_NAMES[key]. Retiring a strategy
        # removes its routing entry, and a stale key left in
        # AUTOMATED_CHANNEL_KEYS then raised KeyError here - taking down
        # initialize_discord() entirely, so every Discord-touching job failed
        # rather than just skipping one dead channel. A key with no route has
        # nothing to check, which is not an error.
        self.missing_channels = [
            name
            for key in AUTOMATED_CHANNEL_KEYS
            if (name := CHANNEL_NAMES.get(key)) and key not in self.channels
        ]
        self.ready = True

    def ensure_private_system_route(self, logical_name: str) -> None:
        if logical_name in SYSTEM_CHANNEL_KEYS and logical_name not in self.private_system_channels:
            raise DiscordError(
                f"Refusing to post system data to #{CHANNEL_NAMES[logical_name]} "
                "because @everyone can view the channel or its privacy could not be verified"
            )

    def send_channel(
        self,
        logical_name: str,
        *,
        content: str = "",
        embed: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return None
        self.ensure_private_system_route(logical_name)
        payload: dict[str, Any] = {"allowed_mentions": {"parse": []}}
        if embed is None and content:
            embed = discord_card(content)
            content = ""
        if content:
            payload["content"] = content[:2000]
        if embed:
            payload["embeds"] = [embed]
        return self._request("POST", f"/channels/{channel_id}/messages", payload)

    def send_channel_file(
        self,
        logical_name: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id or not file_path.exists():
            return None
        self.ensure_private_system_route(logical_name)
        return self._send_file_to_channel(channel_id, file_path, content=content)

    def send_thread_file(
        self,
        thread_id: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        if not self.ready or not thread_id or not file_path.exists():
            return None
        return self._send_file_to_channel(thread_id, file_path, content=content)

    def _send_file_to_channel(
        self,
        channel_id: str,
        file_path: Path,
        *,
        content: str,
    ) -> dict[str, Any] | None:
        url = f"{self.API_BASE}/channels/{channel_id}/messages"
        headers = {
            "Authorization": f"Bot {self.token}",
            "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
        }
        payload = {
            "content": content[:2000],
            "allowed_mentions": {"parse": []},
        }
        for attempt in range(4):
            try:
                with file_path.open("rb") as handle:
                    response = SESSION.post(
                        url,
                        headers=headers,
                        data={"payload_json": json.dumps(payload)},
                        files={"files[0]": (file_path.name, handle, "image/png")},
                        timeout=30,
                    )
            except requests.RequestException as exc:
                if attempt == 3:
                    raise DiscordError(f"Discord chart upload failed: {exc}") from exc
                time.sleep(2**attempt)
                continue
            if response.status_code == 429 and attempt < 3:
                retry_after = as_float(response.json().get("retry_after"), 1.0) or 1.0
                time.sleep(min(retry_after + 0.25, 65))
                continue
            if response.status_code >= 500 and attempt < 3:
                time.sleep(2**attempt)
                continue
            if not response.ok:
                body = response.text[:700].replace(self.token, "[REDACTED]")
                raise DiscordError(f"Discord chart upload HTTP {response.status_code}: {body}")
            return response.json()
        raise DiscordError("Discord chart upload retries exhausted")

    def upsert_channel_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        state_key: str,
        content: str,
        search_token: str = "",
    ) -> str:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return ""
        self.ensure_private_system_route(logical_name)
        messages = state.setdefault("messages", {})
        hashes = state.setdefault("message_hashes", {})
        message_id = str(messages.get(state_key) or "")
        clipped_content = content[:6000]
        # search_token doubles as the footer marker so a card can still be
        # found (both here and by delete_trade_message's fallback) after its
        # tracked message-id is lost from state - the visible card content
        # itself never renders a raw trade_id, only a human sequence label.
        embed = discord_card(clipped_content, footer_suffix=search_token)
        serialized = json.dumps(embed, sort_keys=True, separators=(",", ":"))
        content_hash = hashlib.sha256(
            f"{DISCORD_FORMAT_VERSION}:{serialized}".encode("utf-8")
        ).hexdigest()
        payload = {
            "content": "",
            "embeds": [embed],
            "allowed_mentions": {"parse": []},
        }
        def remove_matching_duplicates(keep_id: str) -> None:
            if not search_token:
                return
            recent = self._request("GET", f"/channels/{channel_id}/messages?limit=100")
            for message in recent if isinstance(recent, list) else []:
                candidate_id = str(message.get("id") or "")
                author = message.get("author") or {}
                if (
                    candidate_id
                    and candidate_id != keep_id
                    and (author.get("bot") or message.get("webhook_id"))
                    and search_token in message_search_text(message)
                ):
                    self._request("DELETE", f"/channels/{channel_id}/messages/{candidate_id}")
        if message_id and hashes.get(state_key) == content_hash:
            remove_matching_duplicates(message_id)
            return message_id
        if message_id:
            try:
                self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
                remove_matching_duplicates(message_id)
                hashes[state_key] = content_hash
                return message_id
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise

        if search_token:
            recent = self._request("GET", f"/channels/{channel_id}/messages?limit=100")
            if isinstance(recent, list):
                matches = []
                for message in recent:
                    author = message.get("author") or {}
                    if (author.get("bot") or message.get("webhook_id")) and search_token in message_search_text(message):
                        matches.append(message)
                if matches:
                    message_id = str(matches[0].get("id") or "")
                    if message_id:
                        self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
                        for duplicate in matches[1:]:
                            duplicate_id = str(duplicate.get("id") or "")
                            if duplicate_id:
                                self._request("DELETE", f"/channels/{channel_id}/messages/{duplicate_id}")
                        messages[state_key] = message_id
                        hashes[state_key] = content_hash
                        return message_id

        created = self._request("POST", f"/channels/{channel_id}/messages", payload)
        if isinstance(created, dict) and created.get("id"):
            message_id = str(created["id"])
            messages[state_key] = message_id
            hashes[state_key] = content_hash
        return message_id

    def upsert_singleton_message(
        self,
        channel_id: str,
        content: str,
        search_token: str,
        components: list[dict[str, Any]] | None = None,
    ) -> tuple[str, int]:
        """Keep exactly one bot-authored card for a stable title in a channel."""
        if not channel_id or not search_token:
            return "", 0
        payload = {
            "content": "",
            "embeds": [discord_card(content[:6000])],
            "allowed_mentions": {"parse": []},
        }
        if components:
            payload["components"] = components
        recent = self._request("GET", f"/channels/{channel_id}/messages?limit=100")
        if not isinstance(recent, list):
            recent = []
        matches = [
            message
            for message in recent
            if ((message.get("author") or {}).get("bot") or message.get("webhook_id"))
            and search_token in message_search_text(message)
        ]
        if matches:
            message_id = str(matches[0].get("id") or "")
            self._request("PATCH", f"/channels/{channel_id}/messages/{message_id}", payload)
            removed = 0
            for duplicate in matches[1:]:
                duplicate_id = str(duplicate.get("id") or "")
                if duplicate_id:
                    self._request("DELETE", f"/channels/{channel_id}/messages/{duplicate_id}")
                    removed += 1
            return message_id, removed
        created = self._request("POST", f"/channels/{channel_id}/messages", payload)
        return str((created or {}).get("id") or ""), 0

    def upsert_trade_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        namespace: str,
        trade_id: str,
        content: str,
    ) -> str:
        if not trade_id:
            return ""
        return self.upsert_channel_message(
            logical_name,
            state,
            f"{namespace}:{logical_name}:{trade_id}",
            content,
            search_token=trade_id,
        )

    def upsert_trade_result(
        self,
        logical_name: str,
        state: dict[str, Any],
        trade_id: str,
        content: str,
    ) -> None:
        self.upsert_trade_message(logical_name, state, "result", trade_id, content)

    def wipe_channel_messages(self, logical_name: str, *, preserve_pinned: bool = False) -> int:
        """Delete every bot-authored message in a channel directly, without
        depending on the local log or trade-id tracking to know what's
        there. Built specifically for reset: trade-id-driven deletion only
        knows about trades still present in the current log, so anything
        orphaned by an earlier, less complete reset attempt is invisible to
        it. This asks Discord what's actually in the channel instead.
        Never touches a message a real person posted - only ones Discord
        itself marks as bot- or webhook-authored.

        preserve_pinned skips any message Discord's own pins list for this
        channel currently includes - built for a channel that's mostly
        command-reply clutter but has one deliberately pinned card (a
        welcome message, a rules summary) that clearing history shouldn't
        touch. Pins are re-read once per call, not cached, so an unpin
        between calls is never accidentally respected.

        Runs as several passes, not one: a single list-then-delete pass can
        come up short if a burst of deletes hits a rate limit partway
        through. Repeating until a pass finds genuinely nothing left is
        more reliable than trusting any single pass was complete - and one
        message failing to delete no longer aborts the rest of that pass,
        it just gets picked up on the next one."""
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return 0
        pinned_ids: set[str] = set()
        if preserve_pinned:
            try:
                pins = self._request("GET", f"/channels/{channel_id}/pins")
                pinned_ids = {
                    str(item.get("id") or "")
                    for item in (pins if isinstance(pins, list) else [])
                }
            except DiscordError as exc:
                print(f"Could not read pinned messages in {logical_name}: {exc}", file=sys.stderr)
        removed = 0
        for _ in range(5):
            deleted_this_pass = 0
            before = ""
            for _ in range(50):
                suffix = f"&before={before}" if before else ""
                page = self._request("GET", f"/channels/{channel_id}/messages?limit=100{suffix}")
                if not isinstance(page, list) or not page:
                    break
                for message in page:
                    author = message.get("author") or {}
                    if not (author.get("bot") or message.get("webhook_id")):
                        continue
                    message_id = str(message.get("id") or "")
                    if not message_id or message_id in pinned_ids:
                        continue
                    try:
                        self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
                        removed += 1
                        deleted_this_pass += 1
                    except DiscordError as exc:
                        if "HTTP 404" not in str(exc):
                            print(f"Could not delete message {message_id} in {logical_name}: {exc}", file=sys.stderr)
                before = str(page[-1].get("id") or "")
                if len(page) < 100 or not before:
                    break
            self._channel_message_cache.pop(channel_id, None)
            if deleted_this_pass == 0:
                break
        return removed

    def wipe_channel_threads(self, logical_name: str) -> int:
        """Delete every thread in a forum channel outright - active and
        archived both - same reasoning as wipe_channel_messages: this asks
        Discord directly instead of relying on which trade-journal threads
        the current log still remembers creating.

        Runs as several passes, not one: a single list-then-delete pass can
        come up short if a burst of deletes hits a rate limit partway
        through, or a thread gets created in the moment between listing and
        deleting. Repeating until a pass finds genuinely nothing left is
        more reliable than trusting any single pass was complete."""
        removed = 0
        for _ in range(5):
            found = self._list_channel_threads(logical_name)
            if not found:
                break
            for thread_id in found:
                try:
                    self._request("DELETE", f"/channels/{thread_id}")
                    removed += 1
                except DiscordError as exc:
                    if "HTTP 404" not in str(exc):
                        print(f"Could not delete thread {thread_id}: {exc}", file=sys.stderr)
        return removed

    def _list_channel_threads(self, logical_name: str) -> set[str]:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id:
            return set()
        thread_ids: set[str] = set()
        try:
            # This must be a guild-level call, not a channel-level one -
            # Discord's own API confirms /channels/{id}/threads/active
            # returns a 404, it was never a valid endpoint. The guild-wide
            # list has to be filtered down to just this channel's threads
            # afterward.
            active = self._request("GET", f"/guilds/{self.guild_id}/threads/active")
            for thread in (active or {}).get("threads", []) if isinstance(active, dict) else []:
                if str(thread.get("parent_id") or "") != str(channel_id):
                    continue
                thread_id = str(thread.get("id") or "")
                if thread_id:
                    thread_ids.add(thread_id)
        except DiscordError as exc:
            print(f"Could not list active threads in {logical_name}: {exc}", file=sys.stderr)
        before = ""
        for _ in range(50):
            suffix = f"?before={before}" if before else ""
            try:
                archived = self._request(
                    "GET", f"/channels/{channel_id}/threads/archived/public{suffix}"
                )
            except DiscordError as exc:
                print(f"Could not list archived threads in {logical_name}: {exc}", file=sys.stderr)
                break
            page = (archived or {}).get("threads", []) if isinstance(archived, dict) else []
            if not page:
                break
            for thread in page:
                thread_id = str(thread.get("id") or "")
                if thread_id:
                    thread_ids.add(thread_id)
            if not (archived or {}).get("has_more"):
                break
            before = str(page[-1].get("thread_metadata", {}).get("archive_timestamp") or "")
            if not before:
                break
        return thread_ids

    def delete_trade_message(
        self,
        logical_name: str,
        state: dict[str, Any],
        namespace: str,
        trade_id: str,
    ) -> None:
        channel_id = self.channels.get(logical_name)
        if not self.ready or not channel_id or not trade_id:
            return
        messages = state.setdefault("messages", {})
        state_key = f"{namespace}:{logical_name}:{trade_id}"
        message_id = str(messages.get(state_key) or "")
        if message_id:
            try:
                self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}")
            except DiscordError as exc:
                if "HTTP 404" not in str(exc):
                    raise
        else:
            # Runtime state can be deleted or predate message tracking. Search
            # the channel itself so stale legacy cards do not become permanent.
            recent = self._channel_message_cache.get(channel_id)
            if recent is None:
                recent = []
                before = ""
                for _ in range(10):
                    suffix = f"&before={before}" if before else ""
                    page = self._request(
                        "GET", f"/channels/{channel_id}/messages?limit=100{suffix}"
                    )
                    if not isinstance(page, list) or not page:
                        break
                    recent.extend(page)
                    before = str(page[-1].get("id") or "")
                    if len(page) < 100 or not before:
                        break
                self._channel_message_cache[channel_id] = recent
            for message in list(recent):
                author = message.get("author") or {}
                if author.get("bot") and trade_id in message_search_text(message):
                    stale_id = str(message.get("id") or "")
                    if stale_id:
                        try:
                            self._request(
                                "DELETE", f"/channels/{channel_id}/messages/{stale_id}"
                            )
                        except DiscordError as exc:
                            if "HTTP 404" not in str(exc):
                                raise
                    recent.remove(message)
        messages.pop(state_key, None)
        state.setdefault("message_hashes", {}).pop(state_key, None)

    def create_trade_thread(self, row: dict[str, str], status: str = "OPEN") -> str:
        if not self.ready:
            return ""
        tag_id = self.tag_ids.get(status) or self.tag_ids.get("OPEN")
        # One card per trade - just the scope and exit price (Position,
        # Entry Plan, Risk through Break-even). Ongoing status posts via
        # post_material_update below it in the same thread.
        payload = {
            "name": trade_title(row)[:100],
            "auto_archive_duration": 1440,
            "applied_tags": [tag_id] if tag_id else [],
            "message": {
                "content": "",
                "embeds": [discord_card(entry_alert_text(row, summary_only=True))],
                "allowed_mentions": {"parse": []},
            },
        }
        created = self._request("POST", f"/channels/{self.forum_id}/threads", payload)
        thread_id = created.get("id", "")
        if thread_id:
            row["discord_thread_id"] = thread_id
            row["discord_status"] = status
            row["discord_format_version"] = DISCORD_FORMAT_VERSION
            row["last_discord_signal"] = "OPEN"
            row["last_discord_pl_pct"] = row.get("current_pl_pct") or "0"
            row["last_discord_update_at"] = now_ct().isoformat()
        return thread_id

    def refresh_trade_thread(self, row: dict[str, str]) -> None:
        thread_id = row.get("discord_thread_id", "")
        if not self.ready or not thread_id:
            return
        self._request("PATCH", f"/channels/{thread_id}", {"name": trade_title(row)[:100]})
        self._request(
            "PATCH",
            f"/channels/{thread_id}/messages/{thread_id}",
            {"content": "", "embeds": [discord_card(entry_alert_text(row, summary_only=True))], "allowed_mentions": {"parse": []}},
        )
        row["discord_format_version"] = DISCORD_FORMAT_VERSION

    def send_thread(self, thread_id: str, content: str) -> None:
        if not self.ready or not thread_id:
            return
        self._request(
            "POST",
            f"/channels/{thread_id}/messages",
            {"content": "", "embeds": [discord_card(content)], "allowed_mentions": {"parse": []}},
        )

    def set_thread_status(self, thread_id: str, status: str, archive: bool = False) -> None:
        if not self.ready or not thread_id:
            return
        payload: dict[str, Any] = {}
        tag_id = self.tag_ids.get(status)
        if tag_id:
            payload["applied_tags"] = [tag_id]
        if archive:
            payload["archived"] = True
        if payload:
            self._request("PATCH", f"/channels/{thread_id}", payload)



def migrate_recent_bot_messages_to_cards(
    discord: DiscordTracker,
    state: dict[str, Any],
    *,
    limit_per_channel: int = 50,
) -> int:
    """One-time conversion of recent TradeBot plain messages into embed cards."""
    if not discord.ready or state.get("card_migration_version") == DISCORD_FORMAT_VERSION:
        return 0

    converted = 0
    visited_channel_ids: set[str] = set()
    for logical_name in AUTOMATED_CHANNEL_KEYS:
        channel_id = discord.channels.get(logical_name)
        if not channel_id or channel_id in visited_channel_ids:
            continue
        visited_channel_ids.add(channel_id)
        recent = discord._request(
            "GET",
            f"/channels/{channel_id}/messages?limit={max(1, min(limit_per_channel, 100))}",
        )
        if not isinstance(recent, list):
            continue
        for message in recent:
            author = message.get("author") or {}
            content = str(message.get("content") or "").strip()
            if not author.get("bot") or not content or message.get("embeds"):
                continue
            message_id = str(message.get("id") or "")
            if not message_id:
                continue
            discord._request(
                "PATCH",
                f"/channels/{channel_id}/messages/{message_id}",
                {
                    "content": "",
                    "embeds": [discord_card(content)],
                    "allowed_mentions": {"parse": []},
                },
            )
            converted += 1

    state["card_migration_version"] = DISCORD_FORMAT_VERSION
    return converted


def safe_discord_call(label: str, callback: Any) -> None:
    try:
        callback()
    except DiscordError as exc:
        print(f"Discord {label} failed: {exc}", file=sys.stderr)


def notify_webhook(lines: list[str], title: str | None = None) -> None:
    if not DISCORD_WEBHOOK_URL or not lines:
        return
    content = (f"**{title}**\n" if title else "") + "\n".join(lines)
    try:
        response = SESSION.post(
            DISCORD_WEBHOOK_URL,
            json={"content": content[:1900], "allowed_mentions": {"parse": []}},
            timeout=15,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"Discord webhook fallback failed: {exc}", file=sys.stderr)


def sync_existing_open_threads(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    *,
    refresh_existing: bool = True,
) -> int:
    if not DISCORD_SYNC_EXISTING_OPEN or not discord.ready:
        return 0
    created = 0
    for row in open_rows(rows):
        try:
            if row.get("discord_thread_id"):
                if (
                    refresh_existing
                    and row.get("discord_format_version") != DISCORD_FORMAT_VERSION
                ):
                    discord.refresh_trade_thread(row)
                continue
            thread_id = discord.create_trade_thread(row, "OPEN")
            if thread_id:
                created += 1
        except DiscordError as exc:
            print(f"Could not sync Discord thread for {row.get('trade_id')}: {exc}", file=sys.stderr)
    return created


def refresh_all_summary_dashboards(
    discord: DiscordTracker, report_state: dict[str, Any], rows: list[dict[str, str]]
) -> None:
    """Rebuild the summary dashboards this function still owns - ticker
    results and wins/losses/scratches - directly against Discord, using the
    same low-level upsert primitive throughout rather than delegating to
    update_performance_pages. That function gets replaced with a no-op by a
    separate reconciliation system (performance_reconciliation.py) once it
    installs itself in the real running system, on purpose, to stop two
    systems fighting over the same cards.

    This function does NOT post per-strategy performance/results content
    (performance_1m/results_1m/performance_5m/results_5m) - that's owned
    exclusively by performance_reconciliation.py's sync_reports once it
    installs, via the exact same logical channel keys. Posting the same
    content from both places would be the "two systems fighting over the
    same cards" problem the original design explicitly avoided, just
    reintroduced for the new per-strategy channels instead of the old
    combined ones. format_strategy_performance/format_strategy_results
    still exist for anything that wants a simple, single-message read
    outside of that paginated ledger system, they're just not wired to
    fire from here."""
    summary_channels = [
        ("ticker_results", "ticker-results", format_ticker_results, "Ticker Results"),
    ]
    for logical_name, token, formatter, search_text in summary_channels:
        try:
            discord.upsert_channel_message(
                logical_name, report_state, token, formatter(rows), search_token=search_text
            )
        except DiscordError as exc:
            print(f"Could not refresh {logical_name}: {exc}", file=sys.stderr)

    for logical_name, token, outcome_label, search_text in (
        ("wins", "wins-summary", "WIN", "Wins Summary"),
        ("losses", "losses-summary", "LOSS", "Losses Summary"),
        ("scratches", "scratches-summary", "SCRATCH", "Scratches Summary"),
    ):
        try:
            discord.upsert_channel_message(
                logical_name,
                report_state,
                token,
                format_result_channel_summary(rows, outcome_label),
                search_token=search_text,
            )
        except DiscordError as exc:
            print(f"Could not refresh {logical_name}: {exc}", file=sys.stderr)


def reset_all_trade_data(discord: DiscordTracker, *, archive: bool) -> dict[str, Any]:
    """Owner-triggered wipe of every tracked trade: paper data only, never
    touches a real account, but this is the one genuinely destructive action
    in the whole system, so it earns real care.

    Deliberately channel-driven, not log-driven: earlier versions of this
    function found what to delete by walking the current log's rows and
    trade IDs, which only works for trades the log still remembers. A trade
    already cleared by an earlier, less complete reset attempt - or removed
    from the log for any other reason - was invisible to that approach,
    leaving its Discord messages orphaned forever. This version asks
    Discord directly what's sitting in each live-trading-desk channel and
    clears that, so "reset means zero" holds regardless of what the log
    currently contains.

    Every trade-journal thread is deleted outright - not archived. An
    archived thread can still surface in Discord's own UI depending on how
    it's filtered, and "reset means zero, no scrollbar" means genuinely
    gone. Data safety for a reset is handled separately: if archive=True,
    the full pre-reset log is saved to a timestamped file first. This is
    deliberately optional, not automatic - a reset run while testing and
    discarding a failed configuration isn't something the owner wants
    preserved as a permanent record of "why this failed so hard," and
    forcing an archive on every reset would do exactly that. Choose
    archive=True when the data itself is worth keeping, not by default."""
    rows = read_log()
    backup_path: str | None = None
    if archive and rows:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        backup_dir = STATE_DIR / "archive"
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_ct().strftime("%Y%m%d-%H%M%S")
        backup_file = backup_dir / f"plays-log-{stamp}.csv"
        with backup_file.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=LOG_HEADER, extrasaction="ignore")
            writer.writeheader()
            for row in rows:
                writer.writerow({column: row.get(column, "") for column in LOG_HEADER})
        backup_path = str(backup_file)

    deleted_threads = 0
    try:
        deleted_threads = discord.wipe_channel_threads("forum")
    except DiscordError as exc:
        print(f"Could not wipe trade-journal threads: {exc}", file=sys.stderr)

    report_state = read_report_state()
    cleared_cards = 0
    for logical_name in ("qualified", "entry", "updates", "wins", "losses", "scratches", "expired"):
        try:
            cleared_cards += discord.wipe_channel_messages(logical_name)
        except DiscordError as exc:
            print(f"Could not wipe {logical_name}: {exc}", file=sys.stderr)

    # Zero out every summary dashboard through the same reliable, shared
    # helper every caller uses now - see refresh_all_summary_dashboards for
    # why this can never depend on update_performance_pages directly.
    refresh_all_summary_dashboards(discord, report_state, [])
    # Fresh state means genuinely fresh - nothing left marked "already
    # routed" from before the reset.
    report_state["routed_closed_trade_ids"] = []
    write_report_state(report_state)

    write_log([])
    # Guard against the one real race here: a different process (the scanner
    # or the position tracker, each in their own process, so no in-process
    # lock reaches them) could be mid read-modify-write on this same file
    # right now and overwrite the empty log with stale data a moment later.
    # Re-checking once and clearing again is a cheap, honest mitigation, not
    # a guarantee - this command is meant to be run when things are quiet.
    time.sleep(0.5)
    if read_log():
        write_log([])

    return {
        "cleared_trades": len(rows),
        "deleted_threads": deleted_threads,
        "cleared_cards": cleared_cards,
        "backup_path": backup_path,
    }


def archive_trade_for_comparison(trade_id: str) -> str:
    """Save one specific closed trade to a standing comparison file, kept
    separate from the live log and from reset-time backups, so results from
    different generations of trading logic can be compared later. Idempotent
    - archiving the same trade twice (e.g. a double-click) is a harmless
    no-op rather than a duplicate row."""
    trade_id = str(trade_id or "").strip()
    if not trade_id:
        return "no trade id provided"
    rows = read_log()
    match = next(
        (row for row in rows if str(row.get("trade_id") or "") == trade_id), None
    )
    if not match:
        return "trade not found - it may have already been cleared by a reset"

    archive_path = STATE_DIR / "archive" / "comparison-trades.csv"
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    if archive_path.exists():
        with archive_path.open("r", newline="", encoding="utf-8") as handle:
            for existing_row in csv.DictReader(handle):
                existing_ids.add(str(existing_row.get("trade_id") or ""))
    if trade_id in existing_ids:
        return "already archived"

    write_header = not archive_path.exists()
    with archive_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=LOG_HEADER, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow({column: match.get(column, "") for column in LOG_HEADER})
    return "archived"


def sync_all_trade_journals(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
) -> dict[str, int]:
    """Backfill one canonical lifecycle thread per trade without inventing history."""
    counts = {"created": 0, "refreshed": 0, "closed_reviews": 0}
    if not discord.ready:
        return counts
    for row in sorted(rows, key=lambda item: item.get("timestamp") or ""):
        trade_id = str(row.get("trade_id") or "")
        if not trade_id:
            continue
        outcome = str(row.get("outcome") or "OPEN")
        thread_id = str(row.get("discord_thread_id") or "")
        created_now = False
        refreshed_now = False
        try:
            if (
                thread_id
                and row.get("discord_format_version") == DISCORD_FORMAT_VERSION
                and row.get("discord_status") == outcome
                and not trade_intelligence.needs_sync(row, "journal")
            ):
                continue
            if not thread_id:
                thread_id = discord.create_trade_thread(
                    row, outcome if outcome != "OPEN" else "OPEN"
                )
                created_now = bool(thread_id)
                if thread_id:
                    counts["created"] += 1
            elif row.get("discord_format_version") != DISCORD_FORMAT_VERSION:
                discord._request("PATCH", f"/channels/{thread_id}", {"archived": False})
                discord.refresh_trade_thread(row)
                refreshed_now = True
                counts["refreshed"] += 1
            if thread_id and outcome == "OPEN":
                trade_intelligence.acknowledge(
                    trade_id, "journal", trade_intelligence.trade_version(row)
                )
                continue
            if not thread_id:
                continue
            if not created_now and not refreshed_now and thread_id:
                discord._request("PATCH", f"/channels/{thread_id}", {"archived": False})
                discord.refresh_trade_thread(row)
                refreshed_now = True
                counts["refreshed"] += 1
            discord._request("PATCH", f"/channels/{thread_id}", {"archived": False})
            sequence = trade_sequence(row)
            token = f"{str(row.get('ticker') or TICKER).upper()} #{sequence} · {outcome}"
            discord.upsert_singleton_message(
                thread_id,
                close_alert_text(row, stored_close_evaluation(row)),
                token,
                components=[
                    {
                        "type": 1,
                        "components": [
                            {
                                "type": 2,
                                "style": 2,
                                "label": "📦 Archive for comparison",
                                "custom_id": f"archive-trade:{trade_id}",
                            }
                        ],
                    }
                ],
            )
            discord.set_thread_status(thread_id, outcome, archive=True)
            row["discord_status"] = outcome
            row["discord_format_version"] = DISCORD_FORMAT_VERSION
            counts["closed_reviews"] += 1
            trade_intelligence.acknowledge(
                trade_id, "journal", trade_intelligence.trade_version(row)
            )
        except DiscordError as exc:
            print(f"Could not synchronize journal for {trade_id}: {exc}", file=sys.stderr)
    return counts

def should_post_update(row: dict[str, str], evaluation: dict[str, Any], timestamp: datetime) -> bool:
    signal = evaluation.get("signal", "HOLD")
    previous_signal = row.get("last_discord_signal") or ""
    if signal != previous_signal:
        return True
    current_pct = as_float(evaluation.get("pl_pct"))
    previous_pct = as_float(row.get("last_discord_pl_pct"))
    if current_pct is not None and previous_pct is not None:
        if abs(current_pct - previous_pct) >= DISCORD_PL_CHANGE_THRESHOLD:
            return True
    previous_update = parse_iso(row.get("last_discord_update_at"))
    return previous_update is None or timestamp - previous_update >= timedelta(minutes=DISCORD_HEARTBEAT_MINUTES)


def post_material_update(row: dict[str, str], evaluation: dict[str, Any], discord: DiscordTracker, timestamp: datetime) -> None:
    if not discord.ready or not row.get("discord_thread_id") or not should_post_update(row, evaluation, timestamp):
        return
    content = position_update_text(row, evaluation)
    status = "HOLDING"
    signal = evaluation.get("signal")
    if signal == "TAKE PROFIT":
        status = "TARGET HIT"
    elif signal in {"STOP OUT", "BREAKEVEN STOP", "THESIS INVALIDATED", "FLOOR STOP"}:
        status = "STOP WARNING"
    try:
        discord.send_thread(row["discord_thread_id"], content)
    except DiscordError as exc:
        if not discord_route_is_missing(exc):
            raise
        row["discord_thread_id"] = ""
        row["discord_status"] = ""
        row["discord_format_version"] = ""
        return
    event_key = f"hold-{timestamp.strftime('%Y%m%d-%H%M')}"
    trade_intelligence.record_event(
        row, "hold-evaluation", event_key, observed_at=timestamp.isoformat(),
        extra={"evaluation": evaluation},
    )
    snapshot = build_trade_snapshot(row, event_key)
    if snapshot and trade_intelligence.register_snapshot(
        row, event_key, snapshot, source_timestamp=timestamp.isoformat()
    ):
        try:
            discord.send_thread_file(
                row["discord_thread_id"], snapshot,
                content=(
                    f"📍 **HOLD TIMELINE · {row.get('trade_id')} · {timestamp.strftime('%m/%d %I:%M %p CT')}**\n"
                    f"Fresh 5m/1d/1w/1mo evidence · signal **{evaluation.get('signal', 'HOLD')}** · "
                    f"open P/L {fmt_money(as_float(evaluation.get('pl_dollars')))}"
                ),
            )
        except DiscordError as exc:
            trade_intelligence.forget_snapshot(str(row.get("trade_id") or ""), event_key)
            trade_intelligence.acknowledge(
                str(row.get("trade_id") or ""), "journal-hold-chart", timestamp.isoformat(),
                status="RETRY", detail=str(exc),
            )
            raise
        else:
            trade_intelligence.acknowledge(
                str(row.get("trade_id") or ""), "journal-hold-chart", timestamp.isoformat()
            )
    try:
        discord.set_thread_status(row["discord_thread_id"], status)
    except DiscordError as exc:
        print(f"Could not update optional forum status for {row.get('trade_id')}: {exc}", file=sys.stderr)
    row["discord_status"] = status
    row["last_discord_signal"] = evaluation.get("signal", "HOLD")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 0)
    row["last_discord_update_at"] = timestamp.isoformat()


def stored_open_evaluation(row: dict[str, str]) -> dict[str, Any]:
    return {
        "signal": row.get("last_signal") or "HOLD",
        "mark": as_float(row.get("last_mark"), parse_entry_price(row)),
        "pl_dollars": as_float(row.get("current_pl_dollars"), 0.0),
        "pl_pct": as_float(row.get("current_pl_pct"), 0.0),
        "note": "",
        "iv": as_float(row.get("iv_at_entry")),
    }

def sync_open_trade_cards(
    row: dict[str, str],
    discord: DiscordTracker,
    report_state: dict[str, Any],
    evaluation: dict[str, Any] | None = None,
    *,
    include_entry: bool = False,
) -> None:
    if not discord.ready or row.get("outcome") != "OPEN":
        return
    trade_id = row.get("trade_id", "")
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    current = evaluation or stored_open_evaluation(row)
    if include_entry:
        # Qualification reasoning lives in the trade's own journal thread
        # (posted as its opening message by create_trade_thread), not as a
        # separate standalone card in the shared new-positions channel.
        discord.upsert_trade_message(
            "entry",
            report_state,
            "entry",
            trade_id,
            entry_alert_text(row, link, summary_only=True),
        )
    discord.upsert_trade_message(
        "updates",
        report_state,
        "position",
        trade_id,
        position_update_text(row, current, link),
    )
    if thread_id and row.get("discord_status") != "HOLDING":
        try:
            discord.set_thread_status(thread_id, "HOLDING")
            row["discord_status"] = "HOLDING"
        except DiscordError as exc:
            print(f"Could not update optional forum status for {trade_id}: {exc}", file=sys.stderr)


def sync_all_open_trade_cards(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> int:
    synced_open = 0
    for row in rows:
        trade_id = row.get("trade_id", "")
        if not trade_id:
            continue
        link = thread_link(row.get("discord_thread_id", ""))
        discord.upsert_trade_message(
            "entry",
            report_state,
            "entry",
            trade_id,
            entry_alert_text(row, link, summary_only=True),
        )
        if row.get("outcome") == "OPEN":
            sync_open_trade_cards(row, discord, report_state)
            synced_open += 1
    return synced_open

def mark_closed_result_routed(row: dict[str, str], report_state: dict[str, Any]) -> None:
    trade_id = row.get("trade_id", "")
    if not trade_id:
        return
    routed = report_state.setdefault("routed_closed_trade_ids", [])
    if trade_id not in routed:
        routed.append(trade_id)


def stored_close_evaluation(row: dict[str, str]) -> dict[str, Any]:
    pl_pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    return {
        "pl_pct": pl_pct,
        "pl_dollars": realized_pl_dollars(row),
        "mark": exit_price(row),
        "signal": row.get("last_signal") or "CLOSED",
    }


def sync_closed_result_channels(
    rows: list[dict[str, str]],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> int:
    """Refresh exit alerts and outcome channels with complete entry/exit structures."""
    if not discord.ready:
        return 0
    updated = 0
    routed = set(report_state.get("routed_closed_trade_ids") or [])
    for row in sorted(closed_rows(rows), key=lambda item: item.get("closed_at") or item.get("timestamp") or ""):
        trade_id = row.get("trade_id", "")
        result_channel = {
            "WIN": "wins",
            "LOSS": "losses",
            "SCRATCH": "scratches",
            "EXPIRED": "expired",
        }.get(row.get("outcome", ""))
        if not trade_id or not result_channel:
            continue
        if trade_id in routed:
            # A completed destination card may predate held-card cleanup.  Do
            # not repost the result, but keep enforcing the channel lifecycle.
            discord.delete_trade_message("entry", report_state, "entry", trade_id)
            discord.delete_trade_message(
                "updates", report_state, "position", trade_id
            )
            discord.delete_trade_message("exit", report_state, "exit", trade_id)
            trade_intelligence.acknowledge(
                trade_id, "result-channel", trade_intelligence.trade_version(row)
            )
            continue
        link = thread_link(row.get("discord_thread_id", ""))
        content = close_alert_text(row, stored_close_evaluation(row), link, summary_only=True)
        discord.upsert_trade_result(result_channel, report_state, trade_id, content)
        discord.delete_trade_message("entry", report_state, "entry", trade_id)
        discord.delete_trade_message("updates", report_state, "position", trade_id)
        discord.delete_trade_message("exit", report_state, "exit", trade_id)
        mark_closed_result_routed(row, report_state)
        trade_intelligence.acknowledge(
            trade_id, "result-channel", trade_intelligence.trade_version(row)
        )
        updated += 1
    return updated

def post_close(row: dict[str, str], evaluation: dict[str, Any], discord: DiscordTracker, report_state: dict[str, Any]) -> None:
    if not discord.ready:
        return
    thread_id = row.get("discord_thread_id", "")
    link = thread_link(thread_id)
    content = close_alert_text(row, evaluation, link, summary_only=True)
    if thread_id:
        try:
            sequence = trade_sequence(row)
            token = f"{str(row.get('ticker') or TICKER).upper()} #{sequence} · {row.get('outcome')}"
            discord.upsert_singleton_message(
                thread_id, close_alert_text(row, evaluation), token
            )
            snapshot = build_trade_snapshot(row, "exit")
            if snapshot and trade_intelligence.register_snapshot(
                row, "exit", snapshot,
                source_timestamp=row.get("closed_at") or now_ct().isoformat(),
            ):
                discord.send_thread_file(
                    thread_id,
                    snapshot,
                    content=(
                        f"📉 **EXIT SNAPSHOT · {row.get('trade_id')} · {row.get('outcome')}**\n"
                        f"5-minute underlying session · contract return "
                        f"{fmt_pct(as_float(evaluation.get('pl_pct')))}"
                    ),
                )
        except DiscordError as exc:
            if not discord_route_is_missing(exc):
                raise
            row["discord_thread_id"] = ""
            row["discord_status"] = ""
            link = ""
            content = close_alert_text(row, evaluation, summary_only=True)
        else:
            try:
                discord.set_thread_status(thread_id, row["outcome"], archive=True)
            except DiscordError as exc:
                print(f"Could not update optional forum status for {row.get('trade_id')}: {exc}", file=sys.stderr)
    result_channel = {
        "WIN": "wins",
        "LOSS": "losses",
        "SCRATCH": "scratches",
        "EXPIRED": "expired",
    }.get(row["outcome"])
    if result_channel:
        discord.upsert_trade_result(result_channel, report_state, row.get("trade_id", ""), content)
        mark_closed_result_routed(row, report_state)
    # Once closed, the full record lives in this trade's own journal thread
    # and the result channel above - the new-positions/held-positions
    # channel cards have no reason to sit there permanently after that.
    discord.delete_trade_message("entry", report_state, "entry", row.get("trade_id", ""))
    discord.delete_trade_message("updates", report_state, "position", row.get("trade_id", ""))
    discord.delete_trade_message("exit", report_state, "exit", row.get("trade_id", ""))
    row["discord_status"] = row["outcome"]
    row["last_discord_signal"] = evaluation.get("signal", "CLOSE")
    row["last_discord_pl_pct"] = round_or_blank(as_float(evaluation.get("pl_pct")), 0)
    row["last_discord_update_at"] = row.get("closed_at") or now_ct().isoformat()

def post_new_trade(
    row: dict[str, str],
    discord: DiscordTracker,
    report_state: dict[str, Any],
) -> None:
    if not discord.ready:
        return
    if not row.get("discord_thread_id"):
        discord.create_trade_thread(row, "OPEN")
    sync_open_trade_cards(row, discord, report_state, include_entry=True)
    thread_id = row.get("discord_thread_id", "")
    snapshot = build_trade_snapshot(row, "entry")
    if thread_id and snapshot and trade_intelligence.register_snapshot(
        row, "entry", snapshot,
        source_timestamp=row.get("timestamp") or now_ct().isoformat(),
    ):
        discord.send_thread_file(
            thread_id,
            snapshot,
            content=(
                f"📸 **ENTRY SNAPSHOT · {row.get('trade_id')}**\n"
                f"5-minute underlying session · {row.get('play_type')} · "
                f"{row.get('strike')} · contract entry "
                f"{fmt_money(as_float(row.get('entry_price')))}"
            ),
        )
    trade_intelligence.record_event(
        row, "entry", "entry", observed_at=row.get("timestamp") or now_ct().isoformat(),
        extra={"journal_thread_id": thread_id},
    )

# ---------------------------------------------------------------------------
# Discord server pages and performance reporting
# ---------------------------------------------------------------------------


def closed_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [
        row for row in rows
        if row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}
    ]


def rows_closed_on(rows: list[dict[str, str]], target_date: date) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in closed_rows(rows):
        closed_at = parse_iso(row.get("closed_at"))
        if closed_at and closed_at.date() == target_date:
            selected.append(row)
    return selected


def rows_closed_between(
    rows: list[dict[str, str]],
    start_date: date,
    end_date: date,
) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for row in closed_rows(rows):
        closed_at = parse_iso(row.get("closed_at"))
        if closed_at and start_date <= closed_at.date() <= end_date:
            selected.append(row)
    return selected


def result_metrics(rows: list[dict[str, str]]) -> dict[str, float]:
    wins = [row for row in rows if row.get("outcome") == "WIN"]
    losses = [row for row in rows if row.get("outcome") == "LOSS"]
    scratches = [row for row in rows if row.get("outcome") == "SCRATCH"]
    decided = wins + losses

    pct_values = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in rows)
        if value is not None
    ]
    win_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in wins)
        if value is not None
    ]
    loss_pcts = [
        value for value in (as_float(row.get("pct_gain_loss")) for row in losses)
        if value is not None
    ]

    win_dollars = [realized_pl_dollars(row) for row in wins]
    loss_dollars = [realized_pl_dollars(row) for row in losses]
    scratch_dollars = [realized_pl_dollars(row) for row in scratches]
    all_dollars = win_dollars + loss_dollars + scratch_dollars

    gross_won = sum(value for value in win_dollars if value > 0)
    gross_lost = abs(sum(value for value in loss_dollars if value < 0))
    holding_hours: list[float] = []
    for row in rows:
        opened = parse_iso(row.get("timestamp"))
        closed = parse_iso(row.get("closed_at"))
        if opened and closed and closed >= opened:
            holding_hours.append((closed - opened).total_seconds() / 3600)
    mfe_values = [
        value for value in (as_float(row.get("max_favorable_pct")) for row in rows)
        if value is not None
    ]
    mae_values = [
        value for value in (as_float(row.get("max_adverse_pct")) for row in rows)
        if value is not None
    ]

    return {
        "wins": float(len(wins)),
        "losses": float(len(losses)),
        "scratches": float(len(scratches)),
        "closed": float(len(rows)),
        "win_rate": (len(wins) / len(decided) * 100) if decided else 0.0,
        "gross_won": gross_won,
        "gross_lost": gross_lost,
        "total_pnl": sum(all_dollars),
        "profit_factor": (gross_won / gross_lost) if gross_lost else (math.inf if gross_won else 0.0),
        "average_holding_hours": (sum(holding_hours) / len(holding_hours)) if holding_hours else 0.0,
        "average_mfe_pct": (sum(mfe_values) / len(mfe_values)) if mfe_values else 0.0,
        "average_mae_pct": (sum(mae_values) / len(mae_values)) if mae_values else 0.0,
        "reconstructed": float(sum(result_is_reconstructed(row) for row in rows)),
        "average_pct": (sum(pct_values) / len(pct_values)) if pct_values else 0.0,
        "average_win_pct": (sum(win_pcts) / len(win_pcts)) if win_pcts else 0.0,
        "average_loss_pct": (sum(loss_pcts) / len(loss_pcts)) if loss_pcts else 0.0,
        "expectancy_pct": (
            sum(as_float(row.get("pct_gain_loss"), 0.0) or 0.0 for row in decided) / len(decided)
        ) if decided else 0.0,
    }


def compact_result_line(row: dict[str, str]) -> str:
    trade_id = row.get("trade_id", "F-UNKNOWN")
    outcome = row.get("outcome", "CLOSED")
    kind = row.get("call_or_put", "").upper()
    entry, closing, dollars = result_price_details(row)
    pct = as_float(row.get("pct_gain_loss"), 0.0) or 0.0
    approx = result_is_reconstructed(row)
    prefix = "≈" if approx else ""

    if row.get("play_type") == "SPREAD":
        sell_strike, buy_strike = parse_spread_strikes(row.get("strike", ""))
        setup = f"{kind} CREDIT {fmt_strike(sell_strike)}/{fmt_strike(buy_strike)}"
        price_move = (
            f"{fmt_option_price(entry)} CR → "
            f"{fmt_option_price(closing, approximate=approx)} DB"
        )
    else:
        setup = f"LONG {kind} {fmt_strike(as_float(row.get('strike'), 0) or 0)}"
        price_move = (
            f"{fmt_option_price(entry)} DB → "
            f"{fmt_option_price(closing, approximate=approx)} CR"
        )

    return (
        f"• **{trade_id}** · {setup}\n"
        f"  {price_move} · **{outcome} {prefix}{fmt_money(dollars)} ({fmt_pct(pct)})**"
    )

def fmt_metric_money(metrics: dict[str, float], key: str) -> str:
    prefix = "≈" if metrics.get("reconstructed", 0) else ""
    return f"{prefix}{fmt_money(metrics[key])}"


def format_performance_stats(rows: list[dict[str, str]]) -> str:
    completed = closed_rows(rows)
    metrics = result_metrics(completed)
    open_count = len(open_rows(rows))
    return "\n".join([
        "## 📊 Performance Dashboard",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])} Wins** · 🔴 **{int(metrics['losses'])} Losses** · "
            f"➖ **{int(metrics['scratches'])} Scratches**"
        ),
        f"Win rate **{metrics['win_rate']:.0f}%** · Closed trades **{int(metrics['closed'])}**",
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%** · "
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%**"
        ),
        "### Current Exposure",
        f"⏸️ Open/HOLD positions **{open_count}** · Results use **1 contract per trade**",
        f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
    ])[:2000]


def format_strategy_breakdown(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        play_type = row.get("play_type", "PLAY").upper()
        kind = row.get("call_or_put", "").upper()
        label = f"{play_type} {kind}".strip()
        groups.setdefault(label, []).append(row)

    lines = [
        "## 🧠 Strategy Breakdown",
        "Strategies ranked by net result, then expectancy.",
    ]
    if not groups:
        lines.extend(["### Results", "No completed trades yet."])
    else:
        ranked: list[tuple[float, float, str, dict[str, float]]] = []
        for label, group in groups.items():
            metrics = result_metrics(group)
            ranked.append((metrics["total_pnl"], metrics["expectancy_pct"], label, metrics))
        medals = ["🥇", "🥈", "🥉"]
        for index, (_, _, label, metrics) in enumerate(
            sorted(ranked, key=lambda item: (item[0], item[1]), reverse=True)[:8]
        ):
            badge = medals[index] if index < len(medals) else "▫️"
            lines.extend([
                f"### {badge} {label}",
                (
                    f"**Record:** {int(metrics['wins'])}W · {int(metrics['losses'])}L · "
                    f"{int(metrics['scratches'])}S\n"
                    f"**Win rate:** {metrics['win_rate']:.0f}%\n"
                    f"**Won / Lost / Net:** {fmt_metric_money(metrics, 'gross_won')} / "
                    f"{fmt_metric_money(metrics, 'gross_lost')} / "
                    f"{fmt_metric_money(metrics, 'total_pnl')}\n"
                    f"**Avg win / Avg loss:** {metrics['average_win_pct']:+.0f}% / "
                    f"{metrics['average_loss_pct']:+.0f}%\n"
                    f"**Expectancy:** {metrics['expectancy_pct']:+.0f}%"
                ),
            ])
    lines.extend(["### Updated", portable_strftime(now_ct(), "%m/%d/%y %-I:%M %p CT")])
    return "\n".join(lines)



def format_strategy_performance(rows: list[dict[str, str]], play_type: str, label: str) -> str:
    """Per-strategy version of format_performance_stats, filtered to one of
    the two independently-tracked SPY 0DTE variants so each gets its own
    dashboard instead of one combined number that hides which one is
    actually working."""
    completed = [row for row in closed_rows(rows) if row.get("play_type") == play_type]
    open_count = len([row for row in open_rows(rows) if row.get("play_type") == play_type])
    metrics = result_metrics(completed)
    return "\n".join([
        f"## 📊 {label} Performance",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])} Wins** · 🔴 **{int(metrics['losses'])} Losses** · "
            f"➖ **{int(metrics['scratches'])} Scratches**"
        ),
        f"Win rate **{metrics['win_rate']:.0f}%** · Closed trades **{int(metrics['closed'])}**",
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%** · "
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%**"
        ),
        "### Current Exposure",
        f"⏸️ Open/HOLD positions **{open_count}** · Results use **1 contract per trade**",
        f"Updated **{portable_strftime(now_ct(), '%m\\%d\\%y %-I:%M %p CT')}**",
    ])[:2000]


def format_strategy_results(rows: list[dict[str, str]], play_type: str, label: str) -> str:
    """Per-strategy breakdown by direction (call/put) and market regime at
    entry, so the two SPY 0DTE variants can be compared on more than just a
    single headline number - if they're only ever splitting evenly on
    direction and regime too, that's a real signal they aren't actually
    diverging enough to be worth tracking separately."""
    completed = [row for row in closed_rows(rows) if row.get("play_type") == play_type]
    lines = [f"## 🧠 {label} Results", "By direction and entry regime."]
    if not completed:
        lines.append("No completed trades yet.")
        lines.append(f"Updated **{portable_strftime(now_ct(), '%m\\%d\\%y %-I:%M %p CT')}**")
        return "\n".join(lines)[:2000]

    by_direction: dict[str, list[dict[str, str]]] = {}
    by_regime: dict[str, list[dict[str, str]]] = {}
    for row in completed:
        kind = (row.get("call_or_put") or "UNKNOWN").upper()
        by_direction.setdefault(kind, []).append(row)
        regime = (row.get("market_regime") or "UNKNOWN").upper()
        by_regime.setdefault(regime, []).append(row)

    lines.append("### By direction")
    for kind, group in sorted(by_direction.items(), key=lambda item: -result_metrics(item[1])["total_pnl"]):
        metrics = result_metrics(group)
        lines.append(
            f"**{kind}** — {int(metrics['wins'])}W / {int(metrics['losses'])}L · "
            f"{metrics['win_rate']:.0f}% win rate · Net {fmt_metric_money(metrics, 'total_pnl')}"
        )
    lines.append("### By entry regime")
    for regime, group in sorted(by_regime.items(), key=lambda item: -result_metrics(item[1])["total_pnl"]):
        metrics = result_metrics(group)
        lines.append(
            f"**{regime}** — {int(metrics['wins'])}W / {int(metrics['losses'])}L · "
            f"{metrics['win_rate']:.0f}% win rate · Net {fmt_metric_money(metrics, 'total_pnl')}"
        )
    lines.append(f"Updated **{portable_strftime(now_ct(), '%m\\%d\\%y %-I:%M %p CT')}**")
    return "\n".join(lines)[:2000]


def format_market_condition_breakdown(rows: list[dict[str, str]]) -> str:
    """Owner ask, sourced from a Reddit suggestion: how does the whole
    system perform across different market conditions, not just per
    strategy. Groups every closed trade (any play_type) by its universal
    market_condition_at_entry tag - unlike format_strategy_results' "by
    entry regime" section above, this is comparable across every strategy
    since the tag doesn't come from any one strategy's own signal."""
    completed = closed_rows(rows)
    lines = ["**By Market Condition**"]
    tagged = [row for row in completed if row.get("market_condition_at_entry")]
    if not tagged:
        lines.append("No completed trades with a recorded market condition yet.")
        return "\n".join(lines)

    by_condition: dict[str, list[dict[str, str]]] = {}
    for row in tagged:
        condition = row.get("market_condition_at_entry") or "UNKNOWN"
        by_condition.setdefault(condition, []).append(row)

    for condition, group in sorted(by_condition.items(), key=lambda item: -result_metrics(item[1])["total_pnl"]):
        metrics = result_metrics(group)
        lines.append(
            f"**{condition}** — {int(metrics['wins'])}W / {int(metrics['losses'])}L · "
            f"{metrics['win_rate']:.0f}% win rate · Net {fmt_metric_money(metrics, 'total_pnl')}"
        )
    return "\n".join(lines)


def format_ticker_results(rows: list[dict[str, str]]) -> str:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in closed_rows(rows):
        ticker = str(row.get("ticker") or "F").upper()
        groups.setdefault(ticker, []).append(row)
    lines = [
        "## Ticker Results",
        "Every completed tracked trade, grouped by underlying.",
    ]
    if not groups:
        lines.append("No completed trades yet.")
    else:
        ranked = sorted(
            groups.items(),
            key=lambda item: result_metrics(item[1])["total_pnl"],
            reverse=True,
        )
        for ticker, group in ranked:
            metrics = result_metrics(group)
            lines.append(
                f"**{ticker}** — {int(metrics['wins'])}W / {int(metrics['losses'])}L "
                f"/ {int(metrics['scratches'])}S · {metrics['win_rate']:.0f}% win rate · "
                f"Net {fmt_metric_money(metrics, 'total_pnl')}"
            )
    lines.append(f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**")
    return "\n".join(lines)[:2000]


def format_daily_recap(
    rows: list[dict[str, str]],
    report_date: date,
    *,
    market_open: bool,
) -> str:
    completed = rows_closed_on(rows, report_date)
    metrics = result_metrics(completed)
    status = "🟢 LIVE" if market_open else "✅ FINAL"
    lines = [
        f"## 📅 Daily Recap · {report_date.strftime('%m/%d/%y')} · {status}",
        "### Results",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Closed Trades",
    ]
    if completed:
        lines.extend(compact_result_line(row) for row in completed[-8:])
    else:
        lines.append("• No trades closed today.")
    carried = open_rows(rows)
    lines.extend([
        "### Positions Carried",
        f"⏸️ **{len(carried)} open/HOLD position(s)**",
        f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**",
    ])
    return "\n".join(lines)[:2000]

def format_weekly_report(
    rows: list[dict[str, str]], report_date: date, *, final: bool = False
) -> str:
    monday = report_date - timedelta(days=report_date.weekday())
    completed = rows_closed_between(rows, monday, report_date)
    metrics = result_metrics(completed)
    lines = [
        f"## 📆 Weekly Report · {monday.strftime('%m/%d')}–{report_date.strftime('%m/%d/%y')}",
        "### Record",
        (
            f"🏆 **{int(metrics['wins'])}W** · 🔴 **{int(metrics['losses'])}L** · "
            f"➖ **{int(metrics['scratches'])}S** · Win rate **{metrics['win_rate']:.0f}%**"
        ),
        "### Money",
        (
            f"Won **{fmt_metric_money(metrics, 'gross_won')}** · "
            f"Lost **{fmt_metric_money(metrics, 'gross_lost')}** · "
            f"Net **{fmt_metric_money(metrics, 'total_pnl')}**"
        ),
        "### Trade Quality",
        (
            f"Expectancy **{metrics['expectancy_pct']:+.0f}%** · "
            f"Avg win **{metrics['average_win_pct']:+.0f}%** · "
            f"Avg loss **{metrics['average_loss_pct']:+.0f}%**"
        ),
    ]
    if completed:
        best = max(completed, key=lambda row: as_float(row.get("pct_gain_loss"), -math.inf) or -math.inf)
        worst = min(completed, key=lambda row: as_float(row.get("pct_gain_loss"), math.inf) or math.inf)
        lines.extend([
            "### Best / Worst",
            f"Best: {compact_result_line(best)[2:]}",
            f"Worst: {compact_result_line(worst)[2:]}",
        ])
    else:
        lines.append("No trades closed this week.")
    lines.append(f"Updated **{portable_strftime(now_ct(), '%m/%d/%y %-I:%M %p CT')}**")
    lines.insert(1, f"**Status:** {'FINAL' if final else 'LIVE'}")
    return "\n".join(lines)[:2000]

def static_server_pages() -> dict[str, str]:
    """Manual channels are intentionally excluded from automation."""
    return {}

def ensure_static_server_pages(
    discord: DiscordTracker,
    state: dict[str, Any],
) -> None:
    if not discord.ready:
        return
    for logical_name, content in static_server_pages().items():
        discord.upsert_channel_message(
            logical_name,
            state,
            f"page:{logical_name}",
            content,
        )
    state["guide_version"] = "1"



def update_scanner_status(
    discord: DiscordTracker,
    state: dict[str, Any],
    *,
    market_open: bool,
    summary: str,
    rows: list[dict[str, str]],
    timestamp: datetime,
) -> None:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    status = "🟢 MARKET OPEN" if market_open else "⚫ MARKET CLOSED"
    content = "\n".join([
        f"## {status}",
        "### Current State",
        summary,
        "### Workflow",
        (
            f"**Open trades:** {len(open_rows(rows))}\n"
            f"**Trigger:** {event_name}\n"
            f"**Run:** #{run_number}\n"
            f"**Last check:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M:%S %p CT')}"
        ),
    ])
    discord.upsert_channel_message("status", state, "scanner-status", content)

def post_workflow_log(
    discord: DiscordTracker,
    *,
    timestamp: datetime,
    result: str,
) -> None:
    if not discord.ready:
        return
    event_name = os.environ.get("GITHUB_EVENT_NAME", "local")
    run_number = os.environ.get("GITHUB_RUN_NUMBER", "—")
    icon = "✅" if result.startswith("OK") else "⚠️"
    discord.send_channel(
        "workflow_log",
        content=(
            f"{icon} `{timestamp.strftime('%m/%d %H:%M:%S CT')}` "
            f"#{run_number} {event_name} · {result}"
        ),
    )



def format_result_channel_summary(rows: list[dict[str, str]], outcome: str) -> str:
    selected = [row for row in closed_rows(rows) if row.get("outcome") == outcome]
    metrics = result_metrics(selected)
    if outcome == "WIN":
        title = "## 🟩 Wins Summary"
        total_label = "Total won"
        total_value = fmt_metric_money(metrics, "gross_won")
        average = f"{metrics['average_win_pct']:+.0f}%"
    elif outcome == "LOSS":
        title = "## 🟥 Losses Summary"
        total_label = "Total lost"
        total_value = fmt_metric_money(metrics, "gross_lost")
        average = f"{metrics['average_loss_pct']:+.0f}%"
    else:
        title = "## ⬜ Scratches Summary"
        total_label = "Net"
        total_value = fmt_metric_money(metrics, "total_pnl")
        average = f"{metrics['average_pct']:+.0f}%"
    return "\n".join([
        title,
        "### Record",
        f"**Trades:** {len(selected)}\n**Average result:** {average}",
        "### Money",
        f"**{total_label}:** {total_value}",
        "### Updated",
        portable_strftime(now_ct(), "%m/%d/%y %-I:%M %p CT"),
    ])

def format_channel_audit(discord: DiscordTracker, timestamp: datetime) -> str:
    connected = len(AUTOMATED_CHANNEL_KEYS) - len(discord.missing_channels)
    private_systems = sorted(
        CHANNEL_NAMES[key] for key in SYSTEM_CHANNEL_KEYS
        if key in discord.private_system_channels
    )
    privacy_issues = sorted(
        CHANNEL_NAMES[key] for key in SYSTEM_CHANNEL_KEYS
        if key in discord.channels and key not in discord.private_system_channels
    )
    lines = [
        "## 🔌 Discord Routing Audit",
        "### Connections",
        (
            f"**Automated channels:** {connected}/{len(AUTOMATED_CHANNEL_KEYS)} connected\n"
            f"**Trade journal forum:** Connected\n"
            f"**Required tags:** Connected\n"
            f"**Card format:** Version {DISCORD_FORMAT_VERSION}\n"
            f"**Private system channels:** {len(private_systems)}/{len(SYSTEM_CHANNEL_KEYS)} verified"
        ),
        "### Result",
    ]
    if privacy_issues:
        lines.append(
            "❌ Unsafe system visibility: "
            + ", ".join(f"#{name}" for name in privacy_issues)
            + ". Technical posts to these channels are blocked."
        )
    elif discord.missing_channels:
        lines.append("❌ Missing: " + ", ".join(f"#{name}" for name in discord.missing_channels))
    else:
        lines.append("✅ Trading content is public-facing; diagnostics remain in the private SYSTEM category.")
    lines.extend([
        "### Manual Channels",
        "Welcome, rules, risk management, server guide, and admin notes are not modified.",
        "### Checked",
        portable_strftime(timestamp, "%m/%d/%y %-I:%M %p CT"),
    ])
    return "\n".join(lines)

def publish_channel_audit(
    discord: DiscordTracker,
    state: dict[str, Any],
    timestamp: datetime,
) -> None:
    if not discord.ready:
        return
    content = format_channel_audit(discord, timestamp)
    discord.upsert_channel_message(
        "status",
        state,
        "channel-audit",
        content,
        search_token="Discord Routing Audit",
    )
    if discord.missing_channels:
        discord.upsert_channel_message(
            "errors",
            state,
            "missing-discord-channels",
            "🚨 **Discord routing audit failed**\nMissing: "
            + ", ".join(f"#{name}" for name in discord.missing_channels),
            search_token="Discord routing audit failed",
        )



def format_qualified_scan(
    qualified: list[dict[str, Any]],
    eligible: list[dict[str, Any]],
    selected: list[dict[str, Any]],
    timestamp: datetime,
) -> str:
    lines = [
        f"## ✅ Qualified {TICKER} Option Setups",
        "### Filter Results",
        (
            f"**Passed all filters:** {len(qualified)}\n"
            f"**New eligible:** {len(eligible)}\n"
            f"**Opened:** {len(selected)}"
        ),
        "### Highest-Ranked Setups",
    ]
    if qualified:
        ranked = sorted(qualified, key=lambda candidate: candidate.get("score", 0), reverse=True)
        lines.extend(candidate_brief(candidate) for candidate in ranked[:8])
        if len(ranked) > 8:
            lines.append(f"…and **{len(ranked) - 8}** additional qualified setup(s).")
    else:
        lines.append("No setup passed every filter on this run.")
    lines.extend(["### Scan Time", portable_strftime(timestamp, "%m/%d/%y %-I:%M %p CT")])
    return "\n".join(lines)


def format_scanner_feed(
    stats: dict[str, Any],
    *,
    spot_price: float,
    eligible_count: int,
    selected_count: int,
    closed_count: int,
    hold_count: int,
    open_count: int,
    timestamp: datetime,
) -> str:
    expirations = stats.get("expirations") or []
    expiration_text = "\n".join(
        f"• **{item['bucket']}:** {format_expiration(item['expiration'])}"
        for item in expirations
    ) or "None available"
    by_strategy = stats.get("candidate_counts") or {}
    spy_0dte_contexts = stats.get("spy_0dte_market_context") or {}
    trend_lines = []
    for play_type in ("SPY_0DTE_1M", "SPY_0DTE_5M"):
        ctx = spy_0dte_contexts.get(play_type) or {}
        trend_lines.append(
            f"**{play_type} regime:** {ctx.get('regime', 'Unavailable')} "
            f"({'Passed' if ctx.get('qualified') else 'Blocked'})\n"
            f"**Read:** {ctx.get('reason', '—')}"
        )
        blocked_by = list(ctx.get("failures") or [])
        if blocked_by:
            trend_lines[-1] += "\n**Blocked by:** " + "; ".join(blocked_by)
    key_levels_ctx = stats.get("spy_key_levels_context") or {}
    if key_levels_ctx:
        trend_lines.append(
            f"**SPY_KEY_LEVELS regime:** {key_levels_ctx.get('regime', 'Unavailable')} "
            f"({'Passed' if key_levels_ctx.get('qualified') else 'Blocked'})\n"
            f"**Read:** {key_levels_ctx.get('reason', '—')}"
        )
        blocked_by = list(key_levels_ctx.get("failures") or [])
        if blocked_by:
            trend_lines[-1] += "\n**Blocked by:** " + "; ".join(blocked_by)
    expansion_ctx = stats.get("spy_expansion_context") or {}
    if expansion_ctx:
        trend_lines.append(
            f"**SPY_EXPANSION_LEVEL regime:** {expansion_ctx.get('regime', 'Unavailable')} "
            f"({'Passed' if expansion_ctx.get('qualified') else 'Blocked'})\n"
            f"**Read:** {expansion_ctx.get('reason', '—')}"
        )
        blocked_by = list(expansion_ctx.get("failures") or [])
        if blocked_by:
            trend_lines[-1] += "\n**Blocked by:** " + "; ".join(blocked_by)
    trend_text = "\n\n".join(trend_lines)
    strategy_text = "\n".join(
        f"• **{label}:** {count}" for label, count in by_strategy.items() if count
    ) or "None"
    return "\n".join([
        f"## 📡 {TICKER} Options Scanner",
        "### Market",
        (
            f"**Time:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M %p CT')}\n"
            f"**{TICKER} spot:** {fmt_option_price(spot_price)}"
        ),
        "### Expirations",
        expiration_text,
        "### Market Regime Gate",
        trend_text,
        "### Contracts",
        (
            f"**Received:** {stats.get('raw_contracts', 0)}\n"
            f"**Inside strike band:** {stats.get('band_contracts', 0)}\n"
            f"**Calls / Puts:** {stats.get('calls', 0)} / {stats.get('puts', 0)}"
        ),
        "### Filter Results",
        (
            f"**Passed:** {stats.get('qualified_candidates', 0)}\n"
            f"**New eligible:** {eligible_count}\n"
            f"**Opened:** {selected_count}"
        ),
        "### Qualified Mix",
        strategy_text,
        "### Lifecycle",
        (
            f"**HOLD:** {hold_count}\n"
            f"**Closed this run:** {closed_count}\n"
            f"**Open total:** {open_count}"
        ),
    ])


def format_closed_scanner_feed(rows: list[dict[str, str]], timestamp: datetime) -> str:
    return "\n".join([
        f"## 📡 {TICKER} Options Scanner",
        "### Market",
        (
            f"**Status:** Closed\n"
            f"**Time:** {portable_strftime(timestamp, '%m/%d/%y %-I:%M %p CT')}"
        ),
        "### Maintenance Sync",
        (
            "No option-chain scan was performed.\n"
            f"**Open/HOLD positions:** {len(open_rows(rows))}"
        ),
    ])

def update_performance_pages(
    discord: DiscordTracker,
    state: dict[str, Any],
    rows: list[dict[str, str]],
) -> None:
    if not discord.ready:
        return
    # Built from the LIVE roster, not hardcoded.
    #
    # This list previously named performance_1m/results_1m/performance_5m/
    # results_5m/performance_expansion outright. Retiring those strategies
    # removed their CHANNEL_NAMES entries, so this raised
    # KeyError: 'performance_1m' - which surfaced as "/force-all-strategies
    # Command failed safely" in Discord. A hardcoded roster in a file whose
    # roster changes is a standing trap; deriving it means retiring a
    # strategy cannot leave a dangling reference behind.
    strategy_variants = [
        (SPY_KEY_LEVELS_PLAY_TYPE, "performance_key_levels",
         "results_key_levels", "Key-Levels Strategy"),
    ]
    for variant in SPY_RATCHET_VARIANTS:
        suffix = variant["play_type"].removeprefix("SPY_RATCHET_").lower()
        strategy_variants.append((
            variant["play_type"],
            f"performance_ratchet_{suffix}",
            f"results_ratchet_{suffix}",
            f"{variant['label']} Strategy",
        ))
    try:
        import spy_live_new_strategies as _live_roster
        for _spec in _live_roster.NEW_STRATEGY_SPECS:
            strategy_variants.append((
                _spec["play_type"],
                _live_roster.performance_key(_spec["play_type"]),
                _live_roster.results_key(_spec["play_type"]),
                _spec["label"],
            ))
    except Exception as _exc:   # pragma: no cover - import guard only
        print(f"new-strategy report roster unavailable: {_exc}", file=sys.stderr)

    # Belt and braces: never attempt a logical name with no route. A card
    # sent nowhere is silently lost, and a missing key here previously took
    # down the whole command.
    strategy_variants = [
        entry for entry in strategy_variants
        if entry[1] in CHANNEL_NAMES and entry[2] in CHANNEL_NAMES
    ]
    for play_type, logical_stats, logical_results, label in strategy_variants:
        discord.upsert_channel_message(
            logical_stats,
            state,
            f"{logical_stats}-stats",
            format_strategy_performance(rows, play_type, label),
            search_token=f"{label} Performance",
        )
        discord.upsert_channel_message(
            logical_results,
            state,
            f"{logical_results}-results",
            format_strategy_results(rows, play_type, label),
            search_token=f"{label} Results",
        )
    discord.upsert_channel_message(
        "ticker_results",
        state,
        "ticker-results",
        format_ticker_results(rows),
        search_token="Ticker Results",
    )
    discord.upsert_channel_message(
        "wins",
        state,
        "wins-summary",
        format_result_channel_summary(rows, "WIN"),
        search_token="Wins Summary",
    )
    discord.upsert_channel_message(
        "losses",
        state,
        "losses-summary",
        format_result_channel_summary(rows, "LOSS"),
        search_token="Losses Summary",
    )
    discord.upsert_channel_message(
        "scratches",
        state,
        "scratches-summary",
        format_result_channel_summary(rows, "SCRATCH"),
        search_token="Scratches Summary",
    )


def sync_reports(
    discord: DiscordTracker,
    state: dict[str, Any],
    rows: list[dict[str, str]],
    timestamp: datetime,
    *,
    market_open: bool,
) -> None:
    if not discord.ready:
        return

    today = timestamp.date()
    historical_dates = {
        parsed.date()
        for row in closed_rows(rows)
        if (parsed := parse_iso(row.get("closed_at"))) is not None
    }
    daily_dates = [today]
    for report_date in daily_dates:
        date_key = report_date.isoformat()
        daily = format_daily_recap(
            rows,
            report_date,
            market_open=market_open and report_date == today,
        )
        discord.upsert_channel_message(
            "daily_recap",
            state,
            f"daily-recap:{date_key}",
            daily,
            search_token=f"Daily Recap · {report_date.strftime('%m/%d/%y')}",
        )

    week_starts = {
        report_date - timedelta(days=report_date.weekday())
        for report_date in daily_dates
    }
    for monday in sorted(week_starts)[-12:]:
        current_week = monday <= today <= monday + timedelta(days=6)
        friday = monday + timedelta(days=4)
        report_end = min(today, friday) if current_week else friday
        iso_year, iso_week, _ = monday.isocalendar()
        week_key = f"{iso_year}-W{iso_week:02d}"
        weekly = format_weekly_report(
            rows, report_end, final=(not current_week or today >= friday)
        )
        discord.upsert_channel_message(
            "weekly_report",
            state,
            f"weekly-report:{week_key}",
            weekly,
            search_token=f"Weekly Report · {monday.strftime('%m/%d')}",
        )

    state["daily_report_date"] = today.isoformat()
    iso_year, iso_week, _ = today.isocalendar()
    state["weekly_report_key"] = f"{iso_year}-W{iso_week:02d}"


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


def render_dashboard(
    spot_quote: dict[str, Any] | None,
    rows: list[dict[str, str]],
    latest_summary: str,
) -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    last = as_float((spot_quote or {}).get("last"))
    previous_close = as_float((spot_quote or {}).get("prevclose"))
    change = last - previous_close if last is not None and previous_close is not None else None
    change_pct = change / previous_close * 100 if change is not None and previous_close else None

    def esc(value: Any) -> str:
        return html.escape(str(value))

    open_items: list[str] = []
    watch_items: list[str] = []
    closed_items: list[str] = []

    for row in rows:
        outcome = row.get("outcome", "OPEN")
        kind = row.get("call_or_put", "").upper()
        if row.get("play_type") == "SPREAD":
            sell_strike, buy_strike = parse_spread_strikes(row["strike"])
            title = f"{esc(row['trade_id'])} · {kind} CREDIT {sell_strike:g}/{buy_strike:g} · {esc(row['expiration'])}"
            legs = f"<div class='legrow'><b>SELL</b> {sell_strike:g} {kind}</div><div class='legrow'><b>BUY</b> {buy_strike:g} {kind}</div>"
        else:
            title = f"{esc(row['trade_id'])} · {esc(row['play_type'])} {kind} {esc(row['strike'])} · {esc(row['expiration'])}"
            legs = ""

        risk_line = (
            f"Entry {esc(row.get('cost_or_credit',''))} · Max profit {esc(row.get('max_profit','—'))} · "
            f"Max risk {esc(row.get('max_risk','—'))} · BE {esc(row.get('breakeven','—'))}"
        )
        watch_items.append(
            f"<div class='play-group'><div class='play-title'>{title}</div>"
            f"<div class='plsub'>{risk_line}</div>{legs}</div>"
        )

        if outcome == "OPEN":
            pnl_pct = as_float(row.get("current_pl_pct"))
            pnl_dollars = as_float(row.get("current_pl_dollars"))
            pnl_class = "pos" if (pnl_pct or 0) > 0 else "neg" if (pnl_pct or 0) < 0 else "zero"
            open_items.append(
                f"<div class='play-group'><div class='play-head'><div class='play-title'>{title}</div>"
                f"<div class='pl {pnl_class}'>{fmt_money(pnl_dollars)} ({fmt_pct(pnl_pct)})</div></div>"
                f"<div class='plsub'>Signal: <b>{esc(row.get('last_signal','HOLD'))}</b> · "
                f"MFE {fmt_pct(as_float(row.get('max_favorable_pct')))} · MAE {fmt_pct(as_float(row.get('max_adverse_pct')))}</div>"
                f"{legs}</div>"
            )
        else:
            badge_class = "badge-win" if outcome == "WIN" else "badge-loss" if outcome == "LOSS" else "badge-scratch"
            closed_items.append(
                f"<div class='play-group closed'><div class='play-head'><div class='play-title'>{title}</div>"
                f"<div><span class='badge {badge_class}'>{esc(outcome)}</span> "
                f"<span class='pl'>{fmt_money(realized_pl_dollars(row))} "
                f"({fmt_pct(as_float(row.get('pct_gain_loss')))})</span></div></div>"
                f"<div class='plsub'>"
                f"Entry ${parse_entry_price(row):.2f} ({fmt_money(entry_contract_value(row))}) · "
                f"Exit {'≈' if result_is_reconstructed(row) else ''}${(exit_price(row) or 0):.2f} "
                f"({'≈' if result_is_reconstructed(row) else ''}{fmt_money(exit_contract_value(row))}) · "
                f"Opened {esc((row.get('timestamp') or '')[:16].replace('T',' '))} · "
                f"Closed {esc((row.get('closed_at') or '')[:16].replace('T',' '))} · "
                f"MFE {fmt_pct(as_float(row.get('max_favorable_pct')))} · MAE {fmt_pct(as_float(row.get('max_adverse_pct')))}</div>"
                f"{legs}</div>"
            )

    closed_rows = [row for row in rows if row.get("outcome") in {"WIN", "LOSS", "SCRATCH"}]
    wins = sum(row.get("outcome") == "WIN" for row in closed_rows)
    losses = sum(row.get("outcome") == "LOSS" for row in closed_rows)
    scratches = sum(row.get("outcome") == "SCRATCH" for row in closed_rows)
    win_rate = wins / (wins + losses) * 100 if wins + losses else None

    spot_html = "<div class='muted'>Quote unavailable</div>"
    if last is not None:
        direction = "up" if (change or 0) > 0 else "down" if (change or 0) < 0 else "flat"
        spot_html = f"<div class='price'>${last:.2f}</div><div class='chg {direction}'>{change:+.2f} ({change_pct:+.2f}%)</div>" if change is not None else f"<div class='price'>${last:.2f}</div>"

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><meta http-equiv='refresh' content='900'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<style>
:root {{ color-scheme: dark; }}
body {{ font-family: Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background:#0f1117; color:#e7e9ee; padding:20px; max-width:900px; margin:0 auto; }}
h1 {{ font-size:22px; margin:0 0 4px; }} .sub,.plsub,.muted,.footer {{ color:#9aa3b2; }} .sub {{ font-size:13px; margin-bottom:16px; }}
.card,.play-group {{ background:#171a22; border:1px solid #2a3040; border-radius:12px; }} .card {{ padding:16px; margin-bottom:16px; }}
.card h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.08em; color:#9aa3b2; margin:0 0 10px; }}
.price {{ font-size:30px; font-weight:750; }} .chg,.pl {{ font-weight:700; }} .up,.pos {{ color:#3ddc97; }} .down,.neg {{ color:#ff6b6b; }} .flat,.zero {{ color:#b8bfcc; }}
.tabs {{ display:flex; flex-wrap:wrap; gap:6px; margin:0 0 14px; border-bottom:1px solid #2a3040; }}
.tab-btn {{ border:0; background:none; color:#8c95a5; padding:10px 12px; cursor:pointer; font-weight:700; border-bottom:2px solid transparent; }}
.tab-btn.active {{ color:#fff; border-bottom-color:#7c6cf2; }} .tab-panel {{ display:none; }} .tab-panel.active {{ display:block; }}
.play-group {{ border-left:4px solid #7c6cf2; padding:12px 14px; margin-bottom:10px; }} .play-group.closed {{ border-left-color:#657080; }}
.play-head {{ display:flex; justify-content:space-between; align-items:baseline; flex-wrap:wrap; gap:8px; }} .play-title {{ font-size:13px; font-weight:750; }}
.plsub,.legrow {{ font-size:12px; margin-top:5px; }} .badge {{ border-radius:999px; padding:2px 8px; font-size:11px; font-weight:800; }}
.badge-win {{ background:#173d2e; color:#57e5a1; }} .badge-loss {{ background:#462328; color:#ff8a91; }} .badge-scratch {{ background:#343945; color:#c1c7d0; }}
.footer {{ font-size:11px; margin-top:10px; }}
</style></head><body>
<h1>Tradysquids · SPY Options Desk</h1>
<div class='sub'>Tradier market data · refreshed every 15 minutes · last build {now_ct().strftime('%Y-%m-%d %H:%M %Z')}</div>
<div class='card'><h2>SPY spot</h2>{spot_html}</div>
<div class='tabs'>
<button class='tab-btn active' data-tab='open'>Open ({len(open_items)})</button>
<button class='tab-btn' data-tab='watch'>All plays ({len(watch_items)})</button>
<button class='tab-btn' data-tab='closed'>Closed · {wins}W-{losses}L-{scratches}S ({'—' if win_rate is None else f'{win_rate:.0f}%'})</button>
</div>
<div id='tab-open' class='tab-panel active'>{''.join(open_items) if open_items else "<div class='muted'>No open plays.</div>"}</div>
<div id='tab-watch' class='tab-panel'>{''.join(watch_items) if watch_items else "<div class='muted'>No plays logged.</div>"}</div>
<div id='tab-closed' class='tab-panel'>{''.join(reversed(closed_items)) if closed_items else "<div class='muted'>No closed results.</div>"}</div>
<div class='card'><h2>Latest run</h2><div class='muted'>{esc(latest_summary)}</div><div class='footer'>GitHub Actions schedule: every 15 minutes. GitHub can delay scheduled jobs; protective exits must not rely on this scanner.</div></div>
<script>
document.querySelectorAll('.tab-btn').forEach(btn => btn.addEventListener('click', () => {{
 document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
 document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));
 btn.classList.add('active'); document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
}}));
</script></body></html>"""
    DASHBOARD_PATH.write_text(html_doc, encoding="utf-8")

# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def initialize_discord() -> DiscordTracker:
    tracker = DiscordTracker(DISCORD_BOT_TOKEN, DISCORD_GUILD_ID)
    if tracker.enabled:
        tracker.discover()
    return tracker


DEFAULT_TRADE_TYPES_ENABLED = {
    "regular_calls": True,
    "regular_puts": True,
    "swing_calls": True,
    "swing_puts": True,
    "bull_put_spreads": True,
    "bear_call_spreads": True,
    # Defaults to paused even in code, not just config - a brand-new,
    # single-regime-backtested, real-leverage play type should never
    # silently go live just because a config key went missing. Split into
    # two independently-toggleable strategies (1-minute vs 5-minute opening
    # range bar interval) that trade fully independently of each other.
    "spy_0dte_1m": False,
    "spy_0dte_5m": False,
    # SPY Key-Levels/ORB/VWAP strategy - a second, independent SPY strategy.
    # Same paused-by-default rule applies: never goes live just because a
    # config key went missing.
    "spy_key_levels": False,
    # SPY 0-1 DTE Expansion-Level strategy - a third, independent SPY
    # strategy. Same paused-by-default rule.
    "spy_expansion_level": False,
}
# 10 ratchet-floor strategies - same paused-by-default rule as every other
# play type above: trade_types_enabled() only reads a config key that
# already exists here, so these have to be added by name, not just set in
# config/scanner.json, or the config flags would be silently ignored.
for _default_variant in SPY_RATCHET_VARIANTS:
    DEFAULT_TRADE_TYPES_ENABLED[_default_variant["play_type"].lower()] = False

# The 14 strategies promoted from the locked top 15. Registered here by name
# for the same reason as the ratchets above, and it is a real trap rather
# than a formality: trade_types_enabled() only applies a config override to
# a key that ALREADY exists in this dict. Setting these in
# config/scanner.json alone left all 14 silently disabled - the scan
# reported them off while the config said on.
try:
    import spy_live_new_strategies as _new_strategies
    for _flag, _default in _new_strategies.default_flags().items():
        DEFAULT_TRADE_TYPES_ENABLED[_flag] = _default
except Exception as _exc:   # pragma: no cover - import guard only
    print(f"new-strategy flags unavailable: {_exc}", file=sys.stderr)


def trade_types_enabled() -> dict[str, bool]:
    configured_value = configured("trade_types_enabled", {})
    merged = dict(DEFAULT_TRADE_TYPES_ENABLED)
    if isinstance(configured_value, dict):
        for key in merged:
            if key in configured_value:
                merged[key] = bool(configured_value[key])
    return merged


def _unavailable_context(reason: str) -> dict[str, Any]:
    return {
        "qualified": False,
        "regime": "NO TRADE",
        "reason": reason,
        "failures": [reason],
    }


def _refresh_spot_price(fallback: float) -> float:
    """scan_candidates() fetches one spot_price at the top of a scan cycle
    and used to pass that same, increasingly stale value all the way
    through 2 SPY_0DTE variants, 10 ratchet variants, Key-Levels, and
    Expansion-Level - each doing its own sequential network round-trip, so
    by the time the later groups ran, the strike selection and journaled
    spot_at_entry could be tens of seconds behind the real market. Fails
    open: any quote error keeps the caller's existing value rather than
    ever blocking a scan on a single flaky refresh."""
    try:
        quote = get_quote(TICKER)
        fresh = as_float(quote.get("last")) if quote else None
        return fresh if fresh else fallback
    except (TradierError, requests.RequestException):
        return fallback


def _run_spy_0dte_variant(
    *,
    play_type: str,
    bar_minutes: int,
    intraday_history: list[dict[str, Any]],
    today_str: str,
    spot_price: float,
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
    add_candidates,
) -> dict[str, Any]:
    """Run one SPY 0DTE variant's signal + candidate build in isolation.
    Two variants (SPY_0DTE_1M, SPY_0DTE_5M) call this independently with
    their own intraday bar interval - each gets its own market-context
    read, its own chain fetch, its own candidates tagged with its own
    play_type, and neither one's failure or signal state can affect the
    other's. They trade fully independently: both can be open at once,
    each under its own $500/trade risk cap, by owner decision.

    Both variants use the same self-contained Python opening-range
    breakout signal, differing only in bar interval - SPY_0DTE_1M
    previously read the live TradingView webhook alert instead
    (spy_0dte_tradingview_signal), but that path proved to be this
    system's single most bug-prone dependency (secret mismatches,
    malformed Pine alert payloads, an alert-freshness window shorter
    than the scan cadence, and alerts marked "consumed" on parse rather
    than on actually opening a trade - four separate real incidents).
    Owner, after all of it: "make them fire off something else because
    I'm sick of seeing them all dead." spy_0dte_tradingview_signal and
    the /tradingview webhook still exist and still work, just unused by
    the live entry path now."""
    try:
        context = spy_0dte_opening_range_signal(intraday_history, bar_minutes=bar_minutes)
    except Exception as exc:
        context = _unavailable_context(f"spy 0dte ({play_type}) signal errored: {exc}")
    if not context.get("qualified"):
        return context
    try:
        allowed_strikes = set(filter_strikes(get_strikes(TICKER, today_str), spot_price))
        raw_chain = get_chain(TICKER, today_str)
        chain = [option for option in raw_chain if float(option.get("strike", -1)) in allowed_strikes]
        for option in chain:
            if option.get("symbol"):
                quote_map[option["symbol"]] = option
        calls = [option for option in chain if option.get("option_type") == "call"]
        puts = [option for option in chain if option.get("option_type") == "put"]
        regime = context["regime"]
        if regime == "BULLISH / CONTROLLED":
            add_candidates(
                f"{play_type} calls",
                scan_spy_0dte_candidates(calls, "call", today_str, spot_price, context, play_type=play_type),
            )
        elif regime == "BEARISH / CONTROLLED":
            add_candidates(
                f"{play_type} puts",
                scan_spy_0dte_candidates(puts, "put", today_str, spot_price, context, play_type=play_type),
            )
    except Exception as exc:
        print(f"SPY 0DTE ({play_type}) scan step failed: {exc}", file=sys.stderr)
    return context


def _run_spy_ratchet_variants(
    *,
    today_str: str,
    spot_price: float,
    intraday_1m: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
    add_candidates,
    enabled: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Run all 10 ratchet-floor variants off ONE shared read of the same
    self-contained Python opening-range breakout signal SPY_0DTE_1M uses
    (spy_0dte_opening_range_signal on 1-minute bars) - computed once here,
    not once per variant, since it's identical for all 10. They previously
    shared SPY_0DTE_1M's live TradingView alert instead
    (spy_0dte_tradingview_signal), but that path proved to be this
    system's single most bug-prone dependency across four separate real
    incidents (secret mismatches, malformed Pine payloads, a freshness
    window shorter than the scan cadence, alerts marked consumed on parse
    rather than on actually opening a trade). Owner: "make them fire off
    something else because I'm sick of seeing them all dead." Each
    variant still gets its own chain fetch, its own play_type-tagged
    candidates, and its own independent trade_types_enabled gate - fully
    independent trades sharing one entry source. Uses
    scan_spy_0dte_candidates as-is (already generic over play_type, same
    delta band/risk cap as SPY_0DTE - only the exit shape is new for
    these variants)."""
    spot_price = _refresh_spot_price(spot_price)
    try:
        shared_context = spy_0dte_opening_range_signal(intraday_1m, bar_minutes=1)
    except Exception as exc:
        shared_context = _unavailable_context(f"spy ratchet signal errored: {exc}")
    results: dict[str, dict[str, Any]] = {}
    for variant in SPY_RATCHET_VARIANTS:
        play_type = variant["play_type"]
        config_key = play_type.lower()
        if not enabled.get(config_key):
            results[play_type] = _unavailable_context(f"{play_type} disabled in trade_types_enabled")
            continue
        context = dict(shared_context)
        results[play_type] = context
        if not context.get("qualified"):
            continue
        try:
            allowed_strikes = set(filter_strikes(get_strikes(TICKER, today_str), spot_price))
            raw_chain = get_chain(TICKER, today_str)
            chain = [option for option in raw_chain if float(option.get("strike", -1)) in allowed_strikes]
            for option in chain:
                if option.get("symbol"):
                    quote_map[option["symbol"]] = option
            kind = "call" if context["regime"] == "BULLISH / CONTROLLED" else "put"
            pool = [option for option in chain if option.get("option_type") == kind]
            add_candidates(
                f"{play_type} {kind}s",
                scan_spy_0dte_candidates(pool, kind, today_str, spot_price, context, play_type=play_type),
            )
        except Exception as exc:
            print(f"SPY ratchet ({play_type}) scan step failed: {exc}", file=sys.stderr)
    return results


def resample_bars(bars: list[dict[str, Any]], group_size: int) -> list[dict[str, Any]]:
    """Aggregate consecutive fine-grained bars into coarser ones (open of
    the first bar, high/low across all, close of the last, volume summed).
    Tradier's timesales interval only accepts 1min/5min/15min - there is no
    native 3-minute bar to request, so the Key-Levels strategy's 3-minute
    read is built by resampling 1-minute bars instead."""
    if group_size <= 1:
        return list(bars)
    resampled: list[dict[str, Any]] = []
    for start in range(0, len(bars), group_size):
        group = bars[start:start + group_size]
        if not group:
            continue
        highs = [value for bar in group if (value := as_float(bar.get("high"))) is not None]
        lows = [value for bar in group if (value := as_float(bar.get("low"))) is not None]
        close = as_float(group[-1].get("close") or group[-1].get("price"))
        volume = sum(as_float(bar.get("volume"), 0.0) or 0.0 for bar in group)
        if close is None or not highs or not lows:
            continue
        resampled.append({"high": max(highs), "low": min(lows), "close": close, "volume": volume})
    return resampled


def _run_new_strategy_variants(
    *,
    today_str: str,
    spot_price: float,
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
    add_candidates,
    enabled: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Run the 14 strategies promoted from the locked top 15.

    All 14 share ONE feature computation - the same
    spy_intraday_features.compute_session_features the backtest used - and
    one chain fetch, since recomputing 94 feature columns fourteen times
    per cycle would be pure waste for an identical result. Each still gets
    its own play_type-tagged candidates and its own independent config
    gate, so any one can be paused without touching the others.

    Signals are read off the newest closed bar only. A setup that completed
    earlier in the session has already passed, and acting on it is the
    stale-signal bug that once had the old ORB reporting a long-since-
    reversed breakout all morning."""
    import spy_live_new_strategies as lns

    results: dict[str, dict[str, Any]] = {}
    active = [p for p in lns.NEW_STRATEGY_PLAY_TYPES if enabled.get(lns.config_flag(p))]

    # A strategy holding a position stops looking for a new one. Owner: "we
    # only need them to scan until they pick up a play then we focus on its
    # held positions until they are closed."
    #
    # has_open_position/dedupe_by_play_type already prevent a second entry,
    # but they do so at the END of the pipeline - after the signal was
    # computed and a chain fetched. Skipping here means an occupied strategy
    # costs nothing per cycle, which is what makes a 2-minute entry scan
    # affordable, and it keeps entry work away from the position it is
    # already managing.
    try:
        open_rows_now = read_log()
        occupied = [p for p in active if has_open_position(open_rows_now, p)]
    except Exception as exc:      # pragma: no cover - log read guard
        print(f"new-strategy open-position check failed: {exc}", file=sys.stderr)
        occupied = []
    for play_type in occupied:
        results[play_type] = {
            "qualified": False,
            "regime": "HOLDING",
            "reason": "already holding a position - managing it until it closes",
            "failures": [],
        }
    active = [p for p in active if p not in occupied]

    if not active:
        for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
            results[play_type] = _unavailable_context(
                f"{lns.config_flag(play_type)} disabled in trade_types_enabled"
            )
        return results

    try:
        intraday = get_intraday_history(TICKER, interval="1min")
        daily = get_daily_history(TICKER)
        rows = lns.live_feature_rows(intraday or [], daily or [])
    except Exception as exc:
        context = _unavailable_context(f"new-strategy feature build failed: {exc}")
        return {play_type: context for play_type in lns.NEW_STRATEGY_PLAY_TYPES}

    if not rows:
        context = _unavailable_context("no intraday bars yet for the current session")
        return {play_type: context for play_type in lns.NEW_STRATEGY_PLAY_TYPES}

    # Both entry paths share one dedupe record. The 15-minute full scan and
    # the 1-minute entry scan can both act, and has_open_position only stops
    # a SECOND position while one is open - it does not stop the full scan
    # re-entering a signal bar the fast scan already traded and closed.
    _scan_state = read_entry_scan_state()
    _last_bar = _scan_state.setdefault("last_signal_bar", {})
    fired = {
        signal["play_type"]: signal
        for signal in lns.signals_on_latest_bar(rows, enabled)
        if _last_bar.get(signal["play_type"]) != signal["bar_time"]
    }

    chain: list[dict[str, Any]] = []
    if fired:
        try:
            expirations = get_expirations(TICKER)
            expiration = today_str if today_str in (expirations or []) else (
                (expirations or [today_str])[0]
            )
            allowed = set(filter_strikes(get_strikes(TICKER, expiration), spot_price))
            chain = [o for o in get_chain(TICKER, expiration)
                     if float(o.get("strike", -1)) in allowed]
            for option in chain:
                if option.get("symbol"):
                    quote_map[option["symbol"]] = option
        except Exception as exc:
            print(f"new-strategy chain fetch failed: {exc}", file=sys.stderr)
            chain, expiration = [], today_str

    for play_type in lns.NEW_STRATEGY_PLAY_TYPES:
        if play_type not in active:
            results[play_type] = _unavailable_context(
                f"{lns.config_flag(play_type)} disabled in trade_types_enabled"
            )
            continue
        signal = fired.get(play_type)
        if signal is None:
            results[play_type] = {
                "qualified": False,
                "regime": "NO TRADE",
                "reason": "no setup on the latest bar",
                "failures": ["entry conditions not met on the newest closed bar"],
            }
            continue
        results[play_type] = {
            "qualified": True,
            "regime": signal.get("regime") or "CONTROLLED",
            "reason": signal["reason"],
            "failures": [],
        }
        if chain:
            add_candidates(
                f"{play_type} {signal['side']}s",
                lns.scan_new_strategy_candidates(chain, signal, expiration, spot_price),
            )
    return results


def _run_spy_key_levels_variant(
    *,
    spot_price: float,
    today_str: str,
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
    add_candidates,
) -> dict[str, Any]:
    """Run the SPY Key-Levels/ORB/VWAP strategy's full signal + candidate
    build in isolation - its own data fetch, its own levels/direction/
    catalyst read, its own candidates, independent of SPY_0DTE entirely."""
    spot_price = _refresh_spot_price(spot_price)
    try:
        premarket_bars = get_premarket_history(SPY_KEY_LEVELS_TICKER, interval="5min")
        daily_bars = get_daily_history(SPY_KEY_LEVELS_TICKER, days=260)
        intraday_1m = get_intraday_history(SPY_KEY_LEVELS_TICKER, interval="1min")
        intraday_5m = get_intraday_history(SPY_KEY_LEVELS_TICKER, interval="5min")
        intraday_3m = resample_bars(intraday_1m, 3)
    except (TradierError, requests.RequestException) as exc:
        return _unavailable_context(f"spy key-levels data fetch failed: {exc}")

    premarket_high, premarket_low = spy_key_levels_premarket_range(premarket_bars)
    prior_day_high, prior_day_low = spy_key_levels_prior_day_range(daily_bars, today_str)
    prior_week_high, prior_week_low = spy_key_levels_prior_week_range(daily_bars, today_str)
    opening_range_high, opening_range_low = spy_key_levels_opening_range(
        intraday_1m, bar_minutes=1, window_minutes=SPY_KEY_LEVELS_OPENING_RANGE_MINUTES
    )
    vwap = spy_key_levels_vwap(intraday_1m)
    sma_200 = spy_key_levels_sma200(daily_bars)
    levels = {
        "premarket_high": premarket_high,
        "premarket_low": premarket_low,
        "prior_day_high": prior_day_high,
        "prior_day_low": prior_day_low,
        "prior_week_high": prior_week_high,
        "prior_week_low": prior_week_low,
        "opening_range_high": opening_range_high,
        "opening_range_low": opening_range_low,
        "vwap": vwap,
        "sma_200": sma_200,
    }

    dir_1m = spy_key_levels_timeframe_direction(intraday_1m)
    dir_3m = spy_key_levels_timeframe_direction(intraday_3m)
    dir_5m = spy_key_levels_timeframe_direction(intraday_5m)
    direction = spy_key_levels_combined_direction(dir_1m, dir_3m, dir_5m)

    try:
        catalyst = economic_calendar.active_or_upcoming_catalyst()
    except Exception:
        catalyst = None

    entry = spy_key_levels_entry_signal(
        spot_price=spot_price, direction=direction, levels=levels, catalyst=catalyst
    )
    context = {
        "qualified": entry.get("qualified", False),
        "regime": entry.get("direction", "MIXED"),
        "reason": entry.get("reason", ""),
        "failures": [] if entry.get("qualified") else [entry.get("reason", "not qualified")],
        "levels": levels,
        "directions": {"1m": dir_1m, "3m": dir_3m, "5m": dir_5m},
        "catalyst": catalyst,
    }
    if not entry.get("qualified"):
        return context

    try:
        expirations = get_expirations(SPY_KEY_LEVELS_TICKER)
        choice = spy_key_levels_choose_expiration(
            expirations, today_str, catalyst_active=catalyst is not None
        )
        if choice is None:
            context["qualified"] = False
            context["reason"] = "no tradeable expiration (0DTE/1-3DTE/weekly) currently listed"
            context["failures"] = [context["reason"]]
            return context
        expiration_tier, expiration = choice
        raw_chain = get_chain(SPY_KEY_LEVELS_TICKER, expiration)
        for option in raw_chain:
            if option.get("symbol"):
                quote_map[option["symbol"]] = option
        found = scan_spy_key_levels_candidates(raw_chain, entry, expiration, expiration_tier, spot_price)
        add_candidates(f"SPY_KEY_LEVELS {entry['side']}s ({expiration_tier})", found)
    except Exception as exc:
        print(f"SPY Key-Levels scan step failed: {exc}", file=sys.stderr)
    return context


def _run_spy_expansion_variant(
    *,
    spot_price: float,
    today_str: str,
    candidates: list[dict[str, Any]],
    quote_map: dict[str, dict[str, Any]],
    add_candidates,
) -> dict[str, Any]:
    """Run the SPY 0-1 DTE Expansion-Level strategy's full signal + candidate
    build in isolation - its own data fetch, its own level/EMA/MACD read,
    its own candidates, independent of SPY_0DTE and SPY_KEY_LEVELS."""
    spot_price = _refresh_spot_price(spot_price)
    try:
        daily_bars = get_daily_history(SPY_EXPANSION_TICKER, days=260)
        bars_15m = get_recent_intraday_history(
            SPY_EXPANSION_TICKER, "15min", SPY_EXPANSION_HISTORY_DAYS
        )
    except (TradierError, requests.RequestException) as exc:
        return {"state": "NO_SETUP", "reason": f"spy expansion data fetch failed: {exc}"}

    if len(bars_15m) < SPY_EXPANSION_EMA_SLOW_PERIOD:
        return {
            "state": "NO_SETUP",
            "reason": f"fewer than {SPY_EXPANSION_EMA_SLOW_PERIOD} 15-minute bars available for EMA200",
        }

    bars_30m = resample_bars(bars_15m, 2)
    bars_1h = resample_bars(bars_15m, 4)

    def _closes(bars: list[dict[str, Any]]) -> list[float]:
        return [value for bar in bars if (value := as_float(bar.get("close") or bar.get("price"))) is not None]

    timeframe_reads = {
        "15m": spy_expansion_timeframe_read(_closes(bars_15m)),
        "30m": spy_expansion_timeframe_read(_closes(bars_30m)),
        "1h": spy_expansion_timeframe_read(_closes(bars_1h)),
    }

    prior_day_high, prior_day_low = spy_expansion_prior_day_range(daily_bars, today_str)
    prior_week_high, prior_week_low = spy_expansion_prior_week_range(daily_bars, today_str)
    prior_month_high, prior_month_low = spy_expansion_prior_month_range(daily_bars, today_str)
    levels = {
        "PDH": prior_day_high,
        "PDL": prior_day_low,
        "PWH": prior_week_high,
        "PWL": prior_week_low,
        "PMH": prior_month_high,
        "PML": prior_month_low,
    }

    signal = spy_expansion_signal(spot_price=spot_price, levels=levels, timeframe_reads=timeframe_reads)
    context = {
        "qualified": signal["state"] in ("CALL_ENTRY_QUALIFIED", "PUT_ENTRY_QUALIFIED"),
        "regime": signal["state"],
        "reason": signal.get("reason", ""),
        "failures": [] if signal["state"] not in ("NO_SETUP",) else [signal.get("reason", "")],
        "state": signal["state"],
        "levels": levels,
        "timeframes": timeframe_reads,
    }
    if signal["state"] not in ("CALL_ENTRY_QUALIFIED", "PUT_ENTRY_QUALIFIED"):
        return context

    try:
        expirations = get_expirations(SPY_EXPANSION_TICKER)
        expiration = spy_expansion_choose_expiration(expirations, today_str)
        if expiration is None:
            context["qualified"] = False
            context["reason"] = "no tradeable 0-1 DTE expiration currently listed"
            context["failures"] = [context["reason"]]
            return context
        raw_chain = get_chain(SPY_EXPANSION_TICKER, expiration)
        for option in raw_chain:
            if option.get("symbol"):
                quote_map[option["symbol"]] = option
        found = scan_spy_expansion_candidates(raw_chain, signal, expiration, spot_price)
        add_candidates(f"SPY_EXPANSION_LEVEL {signal['side']}s", found)
    except Exception as exc:
        print(f"SPY Expansion-Level scan step failed: {exc}", file=sys.stderr)
    return context


def scan_candidates(
    spot_price: float,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    expirations = get_expirations(TICKER)
    try:
        intraday_5m = get_intraday_history(TICKER, interval="5min")
    except (TradierError, requests.RequestException):
        intraday_5m = []
    try:
        intraday_1m = get_intraday_history(TICKER, interval="1min")
    except (TradierError, requests.RequestException):
        intraday_1m = []

    enabled = trade_types_enabled()

    stats: dict[str, Any] = {
        "expirations": [],
        "raw_contracts": 0,
        "band_contracts": 0,
        "calls": 0,
        "puts": 0,
        "qualified_candidates": 0,
        "candidate_counts": {},
        "spy_0dte_market_context": {},
    }
    candidates: list[dict[str, Any]] = []
    quote_map: dict[str, dict[str, Any]] = {}

    def add_candidates(label: str, found: list[dict[str, Any]]) -> None:
        candidates.extend(found)
        stats["candidate_counts"][label] = stats["candidate_counts"].get(label, 0) + len(found)

    # SPY 0DTE is the only trade family this system runs, now split into two
    # independently-tracked live strategies that differ only in the intraday
    # bar interval their opening-range signal reads: SPY_0DTE_5M (the
    # original) and SPY_0DTE_1M. Same delta band, same risk cap, same
    # stop/target/floor/EOD exit rules for both - bar interval is the one
    # variable actually being compared, per explicit owner direction not to
    # invent artificial differences that would muddy the comparison.
    if TICKER == SPY_0DTE_TICKER:
        today_str = now_ct().date().isoformat()
        if today_str in expirations:
            # Both retired 2026-08-17 - see SPY_0DTE_PLAY_TYPES. The loop
            # is kept (rather than deleted) so restoring a variant means
            # re-adding one line here, and so the surrounding expiration /
            # chain plumbing stays exercised.
            variants: tuple[tuple[str, int, list, bool], ...] = ()
            for play_type, bar_minutes, intraday_history, variant_enabled in variants:
                if not variant_enabled:
                    stats["spy_0dte_market_context"][play_type] = _unavailable_context(
                        f"{play_type} disabled in trade_types_enabled"
                    )
                    continue
                stats["spy_0dte_market_context"][play_type] = _run_spy_0dte_variant(
                    play_type=play_type,
                    bar_minutes=bar_minutes,
                    intraday_history=intraday_history,
                    today_str=today_str,
                    spot_price=spot_price,
                    candidates=candidates,
                    quote_map=quote_map,
                    add_candidates=add_candidates,
                )
        else:
            unavailable = _unavailable_context("no same-day expiration listed today")
            stats["spy_0dte_market_context"] = {"SPY_0DTE_5M": unavailable, "SPY_0DTE_1M": unavailable}

        # SPY Ratchet-floor variants: 10 more independently-tracked
        # strategies, sharing the SAME self-contained Python opening-range
        # breakout signal SPY_0DTE_1M uses (spy_0dte_opening_range_signal
        # on 1-minute bars) - they're the same entry as 1M, only their
        # exit shape (spy_ratchet_exit_signal) differs. See
        # SPY_RATCHET_VARIANTS/_run_spy_ratchet_variants.
        if today_str in expirations:
            stats["spy_ratchet_market_context"] = _run_spy_ratchet_variants(
                today_str=today_str,
                spot_price=spot_price,
                intraday_1m=intraday_1m,
                candidates=candidates,
                quote_map=quote_map,
                add_candidates=add_candidates,
                enabled=enabled,
            )
        else:
            ratchet_unavailable = _unavailable_context("no same-day expiration listed today")
            stats["spy_ratchet_market_context"] = {
                variant["play_type"]: ratchet_unavailable for variant in SPY_RATCHET_VARIANTS
            }

    # SPY Key-Levels/ORB/VWAP - a second, fully independent SPY strategy.
    # Runs its own data fetch and signal read regardless of what SPY_0DTE
    # did above; nothing here reads spy_0dte_market_context or vice versa.
    if TICKER == SPY_KEY_LEVELS_TICKER:
        today_str = now_ct().date().isoformat()
        if enabled.get("spy_key_levels"):
            stats["spy_key_levels_context"] = _run_spy_key_levels_variant(
                spot_price=spot_price,
                today_str=today_str,
                candidates=candidates,
                quote_map=quote_map,
                add_candidates=add_candidates,
            )
        else:
            stats["spy_key_levels_context"] = _unavailable_context(
                "spy_key_levels disabled in trade_types_enabled"
            )

        # The 14 strategies promoted from the locked top 15. Independent of
        # anything above: own feature build, own signal read, own chain
        # fetch, own per-strategy config gates.
        stats["new_strategy_context"] = _run_new_strategy_variants(
            today_str=today_str,
            spot_price=spot_price,
            candidates=candidates,
            quote_map=quote_map,
            add_candidates=add_candidates,
            enabled=enabled,
        )

    # SPY 0-1 DTE Expansion-Level - a third, fully independent SPY strategy.
    # Runs its own data fetch and signal read regardless of what SPY_0DTE or
    # SPY_KEY_LEVELS did above.
    if TICKER == SPY_EXPANSION_TICKER:
        today_str = now_ct().date().isoformat()
        # SPY_EXPANSION_LEVEL retired 2026-08-17: -0.0044 ATR/trade
        # (t=-0.34) over 818 trades, positive in only 2 of 4 eras. The gate
        # is left in place so the config flag remains the single switch.
        if False and enabled.get("spy_expansion_level"):
            stats["spy_expansion_context"] = _run_spy_expansion_variant(
                spot_price=spot_price,
                today_str=today_str,
                candidates=candidates,
                quote_map=quote_map,
                add_candidates=add_candidates,
            )
        else:
            stats["spy_expansion_context"] = _unavailable_context(
                "spy_expansion_level disabled in trade_types_enabled"
            )

    stats["qualified_candidates"] = len(candidates)
    return candidates, quote_map, stats


def _scan_candidates_lock_released(
    spot_price: float, position_lock: Any
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, Any]]:
    """Runs scan_candidates() with position_lock released, if one was
    passed in - scan_candidates() only reads market data and returns
    in-memory candidates, it never calls read_log/write_log or otherwise
    touches shared row state, so it's safe to run without holding the
    lock. The caller is responsible for write_log(rows) right before
    calling this (flushing anything not yet persisted) and read_log()
    again right after it returns (picking up whatever a concurrent holder -
    the real-time stream exit path - wrote during the released window);
    skipping either one turns this into a lost-update race instead of a
    safe optimization. No-op passthrough when position_lock is None, so
    every caller that doesn't pass a lock is unaffected."""
    if position_lock is None:
        return scan_candidates(spot_price)
    position_lock.release()
    try:
        return scan_candidates(spot_price)
    finally:
        position_lock.acquire()


def report_error(discord: DiscordTracker | None, message: str) -> None:
    safe_message = message
    for secret in (TRADIER_TOKEN, DISCORD_BOT_TOKEN, DISCORD_WEBHOOK_URL):
        if secret:
            safe_message = safe_message.replace(secret, "[REDACTED]")
    print(safe_message, file=sys.stderr)
    if discord and discord.ready:
        safe_discord_call("error alert", lambda: discord.send_channel("errors", content=f"🚨 **{TICKER} scanner error**\n```{safe_message[:1500]}```"))


def main(*, publish_shared: bool = True, position_lock: Any = None) -> int:
    """position_lock, when passed, is released around scan_candidates() (via
    _scan_candidates_lock_released) - the ~10+ sequential chain-fetch,
    no-CSV-touching part of a scan cycle that empirically dominates its
    ~25s runtime - so the separate-thread real-time stream exit path
    (which needs the same lock) isn't blocked for the whole cycle, only
    the repricing/Discord-posting parts that actually touch shared row
    state. Optional and backward compatible - every other caller (tests, a
    bare spy_scanner.main()) behaves exactly as before."""
    timestamp = now_ct()
    rows = read_log()
    write_log(rows)  # immediately migrate old CSV headers/IDs safely

    discord: DiscordTracker | None = None
    try:
        discord = initialize_discord()
    except DiscordError as exc:
        report_error(None, f"TradeBot setup failed: {exc}")
        return 1

    report_state = read_report_state()
    migrated_cards = 0
    if publish_shared:
        if DISCORD_MIGRATE_LEGACY_MESSAGES:
            try:
                migrated_cards = migrate_recent_bot_messages_to_cards(discord, report_state)
            except DiscordError as exc:
                print(f"Discord card migration failed: {exc}", file=sys.stderr)
        if migrated_cards:
            print(f"Discord card migration: converted {migrated_cards} recent message(s).")
        safe_discord_call(
            "channel audit",
            lambda: publish_channel_audit(discord, report_state, timestamp),
        )
        safe_discord_call(
            "server pages",
            lambda: ensure_static_server_pages(discord, report_state),
        )
        safe_discord_call(
            "performance pages",
            lambda: refresh_all_summary_dashboards(discord, report_state, rows),
        )

    closed_results_backfilled = 0
    if publish_shared:
        try:
            closed_results_backfilled = sync_closed_result_channels(rows, discord, report_state)
        except DiscordError as exc:
            print(f"Discord closed-result backfill failed: {exc}", file=sys.stderr)
    if closed_results_backfilled:
        print(f"Discord result backfill: posted {closed_results_backfilled} closed result(s).")

    journal_counts = (
        sync_all_trade_journals(rows, discord)
        if publish_shared
        else {"created": 0, "refreshed": 0, "closed_reviews": 0}
    )
    if any(journal_counts.values()):
        write_log(rows)
        safe_discord_call(
            "backfill status",
            lambda: discord.upsert_channel_message(
                "status",
                report_state,
                "trade-journal-backfill",
                (
                    "## Trade Journal Synchronization\n"
                    f"Created **{journal_counts['created']}** · refreshed **{journal_counts['refreshed']}** · "
                    f"closed reviews verified **{journal_counts['closed_reviews']}**.\n"
                    "Each paper trade has one canonical lifecycle thread; missing historical evidence is not invented."
                ),
                search_token="Trade Journal Synchronization",
            ),
        )
        print(f"Discord journal sync: {journal_counts}.")

    is_open, timestamp = market_is_open_now()
    if not is_open:
        closed_summary = (
            f"Market closed · maintenance sync complete · "
            f"{len(open_rows(rows))} open trade(s)"
        )
        if publish_shared:
            safe_discord_call(
                "closed status",
                lambda: update_scanner_status(
                    discord,
                    report_state,
                    market_open=False,
                    summary=closed_summary,
                    rows=rows,
                    timestamp=timestamp,
                ),
            )
            safe_discord_call(
                "performance pages",
                lambda: refresh_all_summary_dashboards(discord, report_state, rows),
            )
            safe_discord_call(
                "report sync",
                lambda: sync_reports(
                    discord,
                    report_state,
                    rows,
                    timestamp,
                    market_open=False,
                ),
            )
            safe_discord_call(
                "closed scanner feed",
                lambda: discord.upsert_channel_message(
                    "scanner_feed",
                    report_state,
                    f"scanner-closed:{timestamp.date().isoformat()}",
                    format_closed_scanner_feed(rows, timestamp),
                    search_token="Market closed. No option-chain scan was performed.",
                ),
            )
            safe_discord_call(
                "workflow log",
                lambda: post_workflow_log(
                    discord,
                    timestamp=timestamp,
                    result=f"OK · market closed · {len(open_rows(rows))} open",
                ),
            )
            render_dashboard(None, rows, f"Market closed at {portable_strftime(timestamp, '%-I:%M %p %Z')}; maintenance sync only.")
        write_log(rows)
        write_report_state(report_state)
        print(f"Market closed ({timestamp.isoformat()}); maintenance sync complete.")
        return 0

    try:
        spot = get_quote(TICKER)
        if not spot or as_float(spot.get("last")) is None:
            raise TradierError(f"{TICKER} spot quote was unavailable")
        spot_price = float(spot["last"])
        history = get_daily_history(TICKER, days=120)
        market_condition = classify_market_condition(history)["label"]
        if history:
            render_market_chart(history, spot_price)
            safe_discord_call(
                f"{TICKER} market map",
                lambda: discord.upsert_channel_message(
                    "charts",
                    report_state,
                    f"{TICKER.lower()}-market-map",
                    market_map_text(history, spot_price),
                    search_token=f"{TICKER} Market Map",
                ),
            )
            chart_date_key = f"chart_snapshot_date:{TICKER}"
            if report_state.get(chart_date_key) != timestamp.date().isoformat():
                upload = discord.send_channel_file(
                    "charts",
                    CHART_SCREENSHOT_PATH,
                    content=(
                        f"📊 **DAILY {TICKER} CHART · {timestamp.date().isoformat()}**\n"
                        f"Spot ${spot_price:.2f} · indicators, support, and resistance are marked."
                    ),
                )
                if upload:
                    report_state[chart_date_key] = timestamp.date().isoformat()

        # Reprice every existing open play in one or more batched quote calls.
        currently_open = open_rows(rows) if publish_shared else []
        open_quote_map = get_quotes(symbols_for_rows(currently_open), include_greeks=True)
        refreshed_market_fields = refresh_open_entry_market_data(currently_open, open_quote_map)
        if refreshed_market_fields:
            print(f"Refreshed {refreshed_market_fields} missing IV/OI field(s) on open trades.")
        closed_count = 0
        material_updates = 0
        hold_count = 0
        for row in list(currently_open):
            evaluation = evaluate_open_row(row, open_quote_map, timestamp, underlying_spot_price=spot_price)
            if evaluation.get("pl_pct") is None:
                hold_count += 1
                safe_discord_call(
                    "position board quote warning",
                    lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
                )
                continue
            signal = evaluation.get("signal")
            if signal in CLOSING_SIGNALS:
                close_row(row, evaluation, timestamp)
                safe_discord_call("close routing", lambda r=row, e=evaluation: post_close(r, e, discord, report_state))
                closed_count += 1
            else:
                hold_count += 1
                before = row.get("last_discord_update_at")
                safe_discord_call("journal position update", lambda r=row, e=evaluation: post_material_update(r, e, discord, timestamp))
                safe_discord_call(
                    "position board sync",
                    lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
                )
                if row.get("last_discord_update_at") != before:
                    material_updates += 1

        # Scan for new candidates and choose the highest-quality unique set.
        # scan_candidates() only reads market data and returns in-memory
        # candidates - it never touches rows/the CSV - so the position lock
        # (when held) is released for just this call, the slowest part of a
        # scan cycle, so the real-time stream exit path isn't blocked for
        # the whole cycle. See main()'s docstring and
        # _scan_candidates_lock_released()'s for why the flush before and
        # re-read after are both required, not optional.
        if position_lock is not None:
            write_log(rows)
        candidates, candidate_quote_map, scan_stats = _scan_candidates_lock_released(
            spot_price, position_lock
        )
        if position_lock is not None:
            rows = read_log()
        eligible = [
            candidate for candidate in candidates
            if not recently_tracked(rows, candidate, timestamp)
            and not has_open_position(rows, candidate.get("play_type", ""))
        ]
        # Time-of-day exclusion: the opening minutes and the midday lull
        # both distort entries for reasons that have nothing to do with
        # the actual thesis - this only blocks new entries, never touches
        # exits or position management already in flight.
        if eligible and entry_window_blocked(timestamp):
            eligible = []
        # Earnings blackout: long options bought close to an earnings date
        # can lose value from IV crush alone, independent of whether the
        # stock even moves the predicted direction. days_until_earnings
        # fails open (returns None) on any lookup problem, so a broken or
        # reshaped response from this beta endpoint can never block every
        # trade - only a genuinely confirmed nearby earnings date does.
        if eligible:
            earnings_gap = days_until_earnings(TICKER)
            if earnings_gap is not None and earnings_gap <= EARNINGS_BLACKOUT_DAYS:
                eligible = []
        eligible.sort(key=lambda candidate: candidate.get("score", 0), reverse=True)
        eligible = dedupe_by_play_type(eligible)
        selected = apply_ticker_exposure_cap(eligible, rows, TICKER)

        new_rows: list[dict[str, str]] = []
        for candidate in selected:
            row = candidate_to_row(candidate, rows, timestamp, market_condition=market_condition)
            rows.append(row)
            new_rows.append(row)
            _mark_tradingview_event_if_opened(candidate)
            save_chain_snapshot(row, candidates, timestamp)
            safe_discord_call("new trade post", lambda r=row: post_new_trade(r, discord, report_state))

        # Give newly opened rows their initial zero-P&L values and preserve all state.
        all_quotes = {**open_quote_map, **candidate_quote_map}
        for row in new_rows:
            evaluation = evaluate_open_row(row, all_quotes, timestamp, underlying_spot_price=spot_price)
            if evaluation.get("pl_pct") is None:
                row["current_pl_pct"] = "0"
                row["current_pl_dollars"] = "0"
                evaluation = stored_open_evaluation(row)
            hold_count += 1
            safe_discord_call(
                "new position board sync",
                lambda r=row, e=evaluation: sync_open_trade_cards(r, discord, report_state, e),
            )

        write_log(rows)
        summary = (
            f"Spot ${spot_price:.2f} · {scan_stats.get('raw_contracts', 0)} contracts scanned · "
            f"{scan_stats.get('qualified_candidates', 0)} passed filters · {len(new_rows)} opened · "
            f"{closed_count} closed · {hold_count} HOLD · {len(open_rows(rows))} open total."
        )
        render_dashboard(spot, rows, summary)
        if publish_shared:
            safe_discord_call(
                "open status",
                lambda: update_scanner_status(
                    discord,
                    report_state,
                    market_open=True,
                    summary=summary,
                    rows=rows,
                    timestamp=timestamp,
                ),
            )
            safe_discord_call(
                "performance pages",
                lambda: refresh_all_summary_dashboards(discord, report_state, rows),
            )
            safe_discord_call(
                "report sync",
                lambda: sync_reports(
                    discord,
                    report_state,
                    rows,
                    timestamp,
                    market_open=True,
                ),
            )
        run_number = os.environ.get("GITHUB_RUN_NUMBER", timestamp.strftime("%Y%m%d%H%M"))
        safe_discord_call(
            "qualified scan feed",
            lambda: discord.upsert_channel_message(
                "qualified",
                report_state,
                f"qualified-scan:{TICKER}:{run_number}",
                format_qualified_scan(candidates, eligible, selected, timestamp),
                search_token=f"Qualified {TICKER} Option Setups",
            ),
        )
        safe_discord_call(
            "scanner feed",
            lambda: discord.upsert_channel_message(
                "scanner_feed",
                report_state,
                f"scanner-run:{TICKER}:{run_number}",
                format_scanner_feed(
                    scan_stats,
                    spot_price=spot_price,
                    eligible_count=len(eligible),
                    selected_count=len(new_rows),
                    closed_count=closed_count,
                    hold_count=hold_count,
                    open_count=len(open_rows(rows)),
                    timestamp=timestamp,
                ),
                search_token=f"{TICKER} Options Scanner",
            ),
        )
        if publish_shared:
            safe_discord_call(
                "workflow log",
                lambda: post_workflow_log(
                    discord,
                    timestamp=timestamp,
                    result=f"OK · {summary}",
                ),
            )

        if not discord.ready and (new_rows or closed_count):
            notify_webhook([summary], title=f"{TICKER} options scan")

        write_report_state(report_state)
        print(summary)
        return 0
    except (TradierError, DiscordError, requests.RequestException, ValueError, KeyError) as exc:
        error_text = f"{type(exc).__name__}: {exc}"
        report_error(discord, error_text)
        safe_discord_call(
            "workflow error log",
            lambda: post_workflow_log(
                discord,
                timestamp=now_ct(),
                result=f"ERROR · {error_text[:120]}",
            ),
        )
        write_log(rows)
        write_report_state(report_state)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


ENTRY_SCAN_STATE_PATH = STATE_DIR / "entry-scan-state.json"


def read_entry_scan_state() -> dict[str, Any]:
    """Which signal bar each strategy last acted on.

    Needed because the scan now looks back a few bars instead of only the
    newest one. Without it: a signal fires at 10:07, the scan opens at
    10:08, the trade stops out at 10:09, and the 10:10 scan sees that same
    10:07 signal still inside its lookback and re-enters a setup it has
    already traded.
    """
    if not ENTRY_SCAN_STATE_PATH.exists():
        return {"last_signal_bar": {}}
    try:
        loaded = json.loads(ENTRY_SCAN_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {"last_signal_bar": {}}
    if not isinstance(loaded, dict) or not isinstance(
        loaded.get("last_signal_bar"), dict
    ):
        return {"last_signal_bar": {}}
    return loaded


def write_entry_scan_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ENTRY_SCAN_STATE_PATH.write_text(
        json.dumps(state, indent=2, sort_keys=True), encoding="utf-8"
    )

def scan_new_strategy_entries(position_lock: Any = None) -> dict[str, Any]:
    """Entry-only scan for the promoted strategies, safe to run frequently.

    Exists because the full scan runs every 15 minutes while these
    strategies read their signal off the NEWEST CLOSED BAR - so a setup
    appearing at 10:07 is already gone when the 10:15 scan looks. Measured
    over 250 sessions, a 15-minute cadence sees only 7.6% of signals, and
    ORB Immediate never fires at all because its trigger bar never lands on
    a 15-minute boundary.

    Two rules make a fast cadence safe:

    1. **A strategy holding a position is skipped entirely.** Owner: "we only
       need them to scan until they pick up a play then we focus on its held
       positions until they are closed." Occupied strategies cost nothing per
       cycle.
    2. **POSITION_FILE_LOCK is never held during network I/O.** main() holds
       it for its whole run, which is fine every 15 minutes and would starve
       the exit path every 2. Here the lock is taken only to read the log and
       again to append a row - never across a chain fetch. Exits keep
       priority, which is the point.
    """
    import spy_live_new_strategies as lns
    from contextlib import nullcontext

    lock = position_lock or nullcontext()
    enabled = trade_types_enabled()
    active = [p for p in lns.NEW_STRATEGY_PLAY_TYPES if enabled.get(lns.config_flag(p))]
    key_levels_enabled = bool(enabled.get("spy_key_levels"))
    if not active and not key_levels_enabled:
        return {"scanned": 0, "opened": 0, "skipped": 0, "reason": "none enabled"}

    with lock:
        rows = read_log()
    active = [p for p in active if not has_open_position(rows, p)]
    key_levels_held = has_open_position(rows, SPY_KEY_LEVELS_PLAY_TYPE)
    if not active and (key_levels_held or not key_levels_enabled):
        return {"scanned": 0, "opened": 0, "holding": True,
                "reason": "every enabled strategy is already holding"}

    # --- no lock held from here until the append ---
    spot_quote = get_quote(TICKER)
    spot_price = as_float((spot_quote or {}).get("last"))
    if spot_price is None:
        return {"scanned": 0, "opened": 0, "reason": "no spot quote"}

    # Tradier's timesales intermittently returns an empty series for a
    # perfectly valid window - measured 2 empty responses out of 3 calls in
    # a row, then a full 390-bar session on the next. An empty read here
    # means zero feature rows, which means the cycle silently scans nothing,
    # so it is retried rather than treated as "no bars yet".
    intraday: list[dict[str, Any]] = []
    for _attempt in range(3):
        intraday = get_intraday_history(TICKER, interval="1min") or []
        if intraday:
            break
    daily = get_daily_history(TICKER)
    feature_rows = lns.live_feature_rows(intraday, daily or [])
    if not feature_rows:
        feature_rows = []

    scan_state = read_entry_scan_state()
    last_bar = scan_state.setdefault("last_signal_bar", {})
    fired = {}
    for signal in lns.recent_signals(feature_rows, enabled):
        play_type = signal["play_type"]
        if play_type not in active:
            continue
        # Already traded this exact signal bar - see read_entry_scan_state.
        if last_bar.get(play_type) == signal["bar_time"]:
            continue
        fired[play_type] = signal
    today_str = now_ct().date().isoformat()
    opened: list[str] = []
    tracker = initialize_discord()
    report_state = read_report_state()
    timestamp = now_ct()

    # No early return here even when nothing fired: SPY_KEY_LEVELS is
    # evaluated further down and must still get its pass. Returning at this
    # point is what left it on the 15-minute cadence.
    chain: list[dict[str, Any]] = []
    expiration: str | None = None
    if fired:
        expirations = get_expirations(TICKER) or []
        expiration = today_str if today_str in expirations else (
            expirations[0] if expirations else None)
        if expiration is None:
            fired = {}
        else:
            allowed = set(filter_strikes(get_strikes(TICKER, expiration), spot_price))
            chain = [o for o in get_chain(TICKER, expiration)
                     if float(o.get("strike", -1)) in allowed]

    for play_type, signal in fired.items():
        candidates = lns.scan_new_strategy_candidates(
            chain, signal, expiration, spot_price)
        if not candidates:
            continue
        with lock:
            rows = read_log()
            if has_open_position(rows, play_type):
                continue          # opened by another path since the first read
            eligible = [c for c in candidates if not recently_tracked(rows, c, timestamp)]
            selected = apply_ticker_exposure_cap(eligible, rows, TICKER)
            if not selected:
                continue
            row = candidate_to_row(selected[0], rows, timestamp,
                                   market_condition=signal.get("regime") or "LIVE SIGNAL")
            rows.append(row)
            write_log(rows)
            last_bar[play_type] = signal["bar_time"]
            write_entry_scan_state(scan_state)
        safe_discord_call(
            f"{play_type} entry post",
            lambda r=row: post_new_trade(r, tracker, report_state),
        )
        opened.append(play_type)

    # SPY_KEY_LEVELS is the 14th strategy and does not share the signal
    # plumbing above - its entry is a live price-vs-level read rather than a
    # bar event, so it lives in _run_spy_key_levels_variant with its own
    # fetch. It was therefore still only scanned by the 15-minute full scan
    # while the other 13 moved to 1 minute. Same two rules apply: skipped
    # entirely while it holds a position, and the lock is taken only to
    # append, never across its fetch.
    if key_levels_enabled and not key_levels_held:
        collected: list[dict[str, Any]] = []

        def _collect(_label: str, found: list[dict[str, Any]]) -> None:
            collected.extend(found or [])

        try:
            _run_spy_key_levels_variant(
                spot_price=spot_price, today_str=today_str,
                candidates=[], quote_map={}, add_candidates=_collect,
            )
        except Exception as exc:
            print(f"key-levels fast scan failed: {exc}", file=sys.stderr)
            collected = []

        if collected:
            with lock:
                rows = read_log()
                if not has_open_position(rows, SPY_KEY_LEVELS_PLAY_TYPE):
                    eligible = [c for c in collected
                                if not recently_tracked(rows, c, timestamp)]
                    selected = apply_ticker_exposure_cap(eligible, rows, TICKER)
                    if selected:
                        row = candidate_to_row(selected[0], rows, timestamp,
                                               market_condition="LIVE SIGNAL")
                        rows.append(row)
                        write_log(rows)
                        opened.append(SPY_KEY_LEVELS_PLAY_TYPE)
                    else:
                        row = None
                else:
                    row = None
            if row is not None:
                safe_discord_call(
                    "SPY_KEY_LEVELS entry post",
                    lambda r=row: post_new_trade(r, tracker, report_state),
                )

    if opened:
        write_report_state(report_state)
    return {"scanned": len(active) + (1 if key_levels_enabled else 0),
            "opened": len(opened), "play_types": opened}

