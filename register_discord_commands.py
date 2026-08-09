"""Register private guild-scoped slash commands for TradeBot."""

from __future__ import annotations

import os
import sys

import requests

APPLICATION_ID = os.environ.get("DISCORD_APPLICATION_ID", "").strip()
BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()

OWNER_ONLY_COMMANDS = {
    "filter-set",
    "trader-toggle",
    "regular-set",
    "swing-set",
    "spread-set",
    "reset-trading-data",
    "clear-chat-history",
    "ticker-pause",
    "ticker-resume",
    "ticker-remove",
    "scan-now",
}

TICKER_ARGUMENT = {
    "name": "ticker",
    "description": "Active-universe ticker; defaults to the highest-ranked symbol",
    "type": 3,
    "required": False,
    "min_length": 1,
    "max_length": 10,
}

COMMANDS = [
    {
        "name": "filters",
        "type": 1,
        "description": "Show active paper-scanner risk and liquidity filters",
    },
    {
        "name": "scan-now",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: run local discovery, scanning, or reporting immediately",
        "options": [{
            "name": "scope",
            "description": "Choose the manual local job to run",
            "type": 3,
            "required": True,
            "choices": [
                {"name": "Everything", "value": "all"},
                {"name": "Universe discovery", "value": "discovery"},
                {"name": "Options scanner", "value": "options"},
                {"name": "Market intelligence", "value": "intelligence"},
                {"name": "Open positions", "value": "positions"},
                {"name": "System health", "value": "health"}
            ]
        }]
    },
    {
        "name": "filter-set",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: change a shared exit/risk setting (applies across single-leg trades)",
        "options": [
            {
                "name": "filter",
                "description": "Guarded filter to change",
                "type": 3,
                "required": True,
                "choices": [
                    {"name": "Maximum contract ask", "value": "max_contract_ask"},
                    {"name": "Maximum position risk", "value": "max_position_risk_dollars"},
                    {"name": "Long profit target", "value": "single_leg_profit_target_pct"},
                    {"name": "Long stop", "value": "single_leg_stop_pct"},
                    {"name": "Breakeven lock trigger %", "value": "single_leg_breakeven_trigger_pct"},
                    {"name": "Trailing stop giveback %", "value": "single_leg_trail_giveback_pct"},
                    {"name": "Delta erosion ratio", "value": "single_leg_delta_erosion_ratio"},
                    {"name": "IV crush ratio", "value": "single_leg_iv_crush_ratio"}
                ]
            },
            {
                "name": "value",
                "description": "New decimal value; percentages use 0.20 for 20%",
                "type": 10,
                "required": True,
                "min_value": 0.01,
                "max_value": 100
            }
        ]
    },
    {
        "name": "regular-set",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: change a regular calls/puts entry signal setting",
        "options": [
            {
                "name": "filter",
                "description": "Regular-trader setting to change",
                "type": 3,
                "required": True,
                "choices": [
                    {"name": "Intraday change threshold %", "value": "regular_intraday_change_threshold_pct"},
                    {"name": "VWAP distance threshold %", "value": "regular_vwap_distance_threshold_pct"},
                    {"name": "Momentum gap threshold %", "value": "regular_momentum_gap_threshold_pct"},
                    {"name": "RSI bullish level", "value": "regular_rsi_bullish"},
                    {"name": "RSI bearish level", "value": "regular_rsi_bearish"},
                    {"name": "15-min slope threshold %", "value": "regular_slope_threshold_pct"},
                    {"name": "Daily trend threshold %", "value": "regular_daily_trend_threshold_pct"},
                    {"name": "Qualifying score threshold", "value": "regular_score_threshold"}
                ]
            },
            {
                "name": "value",
                "description": "New decimal value",
                "type": 10,
                "required": True,
                "min_value": -10,
                "max_value": 100
            }
        ]
    },
    {
        "name": "swing-set",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: change a swing calls/puts entry signal setting",
        "options": [
            {
                "name": "filter",
                "description": "Swing-trader setting to change",
                "type": 3,
                "required": True,
                "choices": [
                    {"name": "20-day distance threshold %", "value": "swing_sma20_distance_threshold_pct"},
                    {"name": "Trend threshold %", "value": "swing_trend_threshold_pct"},
                    {"name": "RSI bullish level", "value": "swing_rsi_bullish"},
                    {"name": "RSI bearish level", "value": "swing_rsi_bearish"},
                    {"name": "Minimum volume ratio", "value": "swing_volume_ratio_min"},
                    {"name": "Close-vs-high bullish %", "value": "swing_close_vs_high_bullish_pct"},
                    {"name": "Close-vs-high bearish %", "value": "swing_close_vs_high_bearish_pct"},
                    {"name": "Qualifying score threshold", "value": "swing_score_threshold"}
                ]
            },
            {
                "name": "value",
                "description": "New decimal value",
                "type": 10,
                "required": True,
                "min_value": -10,
                "max_value": 100
            }
        ]
    },
    {
        "name": "spread-set",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: change a credit-spread entry, exit, or IV-history setting",
        "options": [
            {
                "name": "filter",
                "description": "Spread-trader setting to change",
                "type": 3,
                "required": True,
                "choices": [
                    {"name": "Spread profit target", "value": "spread_profit_target_pct"},
                    {"name": "Spread stop multiple", "value": "spread_stop_multiple"},
                    {"name": "Min IV/RV ratio", "value": "iv_rv_min_ratio"},
                    {"name": "Max trend strength", "value": "spread_max_trend_strength"},
                    {"name": "20-day extreme buffer %", "value": "spread_extreme_buffer_pct"},
                    {"name": "Delta danger ratio", "value": "spread_delta_danger_ratio"},
                    {"name": "IV expansion ratio", "value": "spread_iv_expansion_ratio"},
                    {"name": "IV history min samples", "value": "iv_history_min_samples"},
                    {"name": "Pooled IV min samples", "value": "pooled_iv_min_samples"},
                    {"name": "Pooled IV lookback days", "value": "pooled_iv_lookback_days"}
                ]
            },
            {
                "name": "value",
                "description": "New decimal value; percentages use 0.20 for 20%",
                "type": 10,
                "required": True,
                "min_value": 0.001,
                "max_value": 400
            }
        ]
    },
    {
        "name": "trader-toggle",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: turn one of the six traders on or off locally",
        "options": [
            {
                "name": "trader",
                "description": "Which trader to enable or disable",
                "type": 3,
                "required": True,
                "choices": [
                    {"name": "Regular calls", "value": "regular_calls"},
                    {"name": "Regular puts", "value": "regular_puts"},
                    {"name": "Swing calls", "value": "swing_calls"},
                    {"name": "Swing puts", "value": "swing_puts"},
                    {"name": "Bull put spreads", "value": "bull_put_spreads"},
                    {"name": "Bear call spreads", "value": "bear_call_spreads"}
                ]
            },
            {
                "name": "enabled",
                "description": "Turn this trader on or off",
                "type": 5,
                "required": True
            }
        ]
    },
    {
        "name": "reset-trading-data",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: wipe all paper trades and journal history to start clean",
        "options": [
            {
                "name": "confirm",
                "description": "Type RESET exactly to confirm - this cannot be undone from Discord alone",
                "type": 3,
                "required": True,
                "min_length": 5,
                "max_length": 5
            },
            {
                "name": "archive",
                "description": "Legacy option, now ignored - a backup is always saved before clearing",
                "type": 5,
                "required": True
            }
        ]
    },
    {
        "name": "clear-chat-history",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: delete all bot command-reply clutter from #general-chat, keeping pinned messages",
        "options": [
            {
                "name": "confirm",
                "description": "Type CLEAR exactly to confirm - this cannot be undone from Discord alone",
                "type": 3,
                "required": True,
                "min_length": 5,
                "max_length": 5
            }
        ]
    },
    {
        "name": "ticker-add",
        "type": 1,
        "description": "Add a verified optionable ticker to the shared scan universe",
        "options": [{
            "name": "ticker",
            "description": "Stock symbol, such as VALE",
            "type": 3,
            "required": True,
            "min_length": 1,
            "max_length": 10,
        }],
    },
    {
        "name": "ticker-pause",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: exclude a ticker from new scans",
        "options": [
            {
                "name": "ticker",
                "description": "Integrated ticker symbol",
                "type": 3,
                "required": True,
                "min_length": 1,
                "max_length": 10,
            },
            {
                "name": "duration",
                "description": "Resume next market day or remain paused",
                "type": 3,
                "required": False,
                "choices": [
                    {"name": "Today only", "value": "today"},
                    {"name": "Until resumed", "value": "indefinite"},
                ],
            },
        ],
    },
    {
        "name": "ticker-resume",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: restore a ticker to the shared scan universe",
        "options": [{
            "name": "ticker",
            "description": "Integrated ticker symbol",
            "type": 3,
            "required": True,
            "min_length": 1,
            "max_length": 10,
        }],
    },
    {
        "name": "ticker-remove",
        "type": 1,
        "default_member_permissions": "0",
        "description": "Owner: remove a ticker from new scans but preserve history",
        "options": [{
            "name": "ticker",
            "description": "Integrated ticker symbol",
            "type": 3,
            "required": True,
            "min_length": 1,
            "max_length": 10,
        }],
    },
    {
        "name": "ticker-list",
        "type": 1,
        "description": "List the current dynamic scanner universe and exclusions",
    },
    {
        "name": "ticker-status",
        "type": 1,
        "description": "Show whether a ticker is active in the shared universe",
        "options": [{
            "name": "ticker",
            "description": "Integrated ticker symbol",
            "type": 3,
            "required": True,
            "min_length": 1,
            "max_length": 10,
        }],
    },
    {
        "name": "help",
        "type": 1,
        "description": "Show every dynamic Tradysquids command and how to use it",
    },
    {
        "name": "quote",
        "type": 1,
        "description": "Show a ticker quote, volume, spread, and timestamp",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "trend",
        "type": 1,
        "description": "Show a ticker technical dashboard",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "chart",
        "type": 1,
        "description": "Generate a current ticker price chart",
        "options": [dict(TICKER_ARGUMENT), {
            "name": "days",
            "description": "Number of trading days",
            "type": 4,
            "required": False,
            "choices": [
                {"name": "30 days", "value": 30},
                {"name": "60 days", "value": 60},
                {"name": "90 days", "value": 90},
                {"name": "120 days", "value": 120},
            ],
        }],
    },
    {
        "name": "levels",
        "type": 1,
        "description": "Show ticker trend, RSI, support, and resistance",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "events",
        "type": 1,
        "description": "Show ticker events, news, and filing links",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "why",
        "type": 1,
        "description": "Explain a tracked trade for the selected ticker",
        "options": [{
            "name": "trade_id",
            "description": "Example: F-20260729-005",
            "type": 3,
            "required": True,
            "min_length": 10,
            "max_length": 40,
        }, dict(TICKER_ARGUMENT)],
    },
    {
        "name": "chain",
        "type": 1,
        "description": "Rank liquid option contracts for an integrated ticker",
        "options": [dict(TICKER_ARGUMENT), {
            "name": "side",
            "description": "Calls or puts",
            "type": 3,
            "required": False,
            "choices": [
                {"name": "Calls", "value": "call"},
                {"name": "Puts", "value": "put"},
            ],
        }],
    },
    {
        "name": "setup",
        "type": 1,
        "description": "Check a ticker direction and research shortlist",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "watchlist",
        "type": 1,
        "description": "Show ticker levels and monitored conditions",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "option",
        "type": 1,
        "description": "Inspect an option contract for the selected ticker",
        "options": [{
            "name": "symbol",
            "description": "Tradier OCC option symbol",
            "type": 3,
            "required": True,
            "min_length": 8,
            "max_length": 32,
        }, dict(TICKER_ARGUMENT)],
    },
    {
        "name": "risk",
        "type": 1,
        "description": "Calculate long-option premium risk and management levels",
        "options": [
            {
                "name": "premium",
                "description": "Option price per share, such as 0.42",
                "type": 10,
                "required": True,
                "min_value": 0.01,
                "max_value": 100,
            },
            {
                "name": "contracts",
                "description": "Number of contracts",
                "type": 4,
                "required": False,
                "min_value": 1,
                "max_value": 100,
            },
            {
                "name": "side",
                "description": "Call or put",
                "type": 3,
                "required": False,
                "choices": [
                    {"name": "Call", "value": "call"},
                    {"name": "Put", "value": "put"},
                ],
            },
            dict(TICKER_ARGUMENT),
        ],
    },
    {
        "name": "performance",
        "type": 1,
        "description": "Summarize recorded performance for one ticker",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "status",
        "type": 1,
        "description": "Check current ticker and system status",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "schedule",
        "type": 1,
        "description": "Show the current ticker monitoring schedule",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "dataage",
        "type": 1,
        "description": "Show cached information age for one ticker",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "lastscan",
        "type": 1,
        "description": "Show recent monitoring results for the current ticker",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "filings",
        "type": 1,
        "description": "Show ticker filing links and recent news",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "calendar",
        "type": 1,
        "description": "Show ticker event, news, and filing links",
        "options": [dict(TICKER_ARGUMENT)],
    },
    {
        "name": "explain",
        "type": 1,
        "description": "Explain an options or technical-analysis term",
        "options": [{
            "name": "topic",
            "description": "Delta, theta, IV, spread, open interest, DTE, RSI, or ATR",
            "type": 3,
            "required": True,
            "choices": [
                {"name": "Delta", "value": "delta"},
                {"name": "Theta", "value": "theta"},
                {"name": "Implied volatility", "value": "iv"},
                {"name": "Bid/ask spread", "value": "spread"},
                {"name": "Open interest", "value": "open-interest"},
                {"name": "Days to expiration", "value": "dte"},
                {"name": "RSI", "value": "rsi"},
                {"name": "ATR", "value": "atr"},
            ],
        }],
    },
    {
        "name": "ask",
        "type": 1,
        "description": "Ask TradeBot a beginner trading or options question",
        "options": [{
            "name": "question",
            "description": "Example: What is a call option?",
            "type": 3,
            "required": True,
            "min_length": 3,
            "max_length": 300,
        }],
    },
]


def main() -> int:
    missing = [
        name for name, value in (
            ("DISCORD_APPLICATION_ID", APPLICATION_ID),
            ("DISCORD_BOT_TOKEN", BOT_TOKEN),
            ("DISCORD_GUILD_ID", GUILD_ID),
        )
        if not value
    ]
    if missing:
        print("Missing environment values: " + ", ".join(missing), file=sys.stderr)
        return 1
    url = (
        f"https://discord.com/api/v10/applications/{APPLICATION_ID}"
        f"/guilds/{GUILD_ID}/commands"
    )
    headers = {
        "Authorization": f"Bot {BOT_TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (Tradysquids TradeBot, 1.0)",
    }
    # Discord's bulk-overwrite endpoint registers the complete guild command
    # set in one request. This avoids a burst of POST requests and removes
    # commands that no longer exist in COMMANDS.
    response = requests.put(url, headers=headers, json=COMMANDS, timeout=30)
    if not response.ok:
        print(
            f"Failed to register command set: "
            f"HTTP {response.status_code} {response.text[:500]}",
            file=sys.stderr,
        )
        return 1
    registered = response.json()
    if not isinstance(registered, list):
        print("Discord returned an unexpected command response.", file=sys.stderr)
        return 1
    names = {str(command.get("name") or "") for command in registered}
    expected = {str(command["name"]) for command in COMMANDS}
    if names != expected:
        print(
            "Discord command verification mismatch: "
            f"expected {sorted(expected)}, received {sorted(names)}",
            file=sys.stderr,
        )
        return 1
    print(f"Registered and verified {len(registered)} guild commands.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
