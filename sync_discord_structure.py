"""Idempotently synchronize the shared Tradysquids Discord information layout."""

from __future__ import annotations

import sys
from dataclasses import dataclass

import discord_transport
from run_with_env import load_env

BOT_CHANNEL_ALLOW = (
    1024
    | 2048
    | 16384
    | 32768
    | 65536
    | (1 << 34)
    | (1 << 38)
)
ADMINISTRATOR_PERMISSION = 1 << 3
BAN_MEMBERS_PERMISSION = 1 << 2
BOT_ROLE_REQUIRED_PERMISSIONS = {
    "Kick Members": 1 << 1,
    "Manage Channels": 1 << 4,
    "Manage Server": 1 << 5,
    "View Audit Log": 1 << 7,
    "View Channels": 1 << 10,
    "Send Messages": 1 << 11,
    "Manage Messages": 1 << 13,
    "Embed Links": 1 << 14,
    "Attach Files": 1 << 15,
    "Read Message History": 1 << 16,
    "Change Nickname": 1 << 26,
    "Manage Nicknames": 1 << 27,
    "Manage Roles": 1 << 28,
    "Manage Webhooks": 1 << 29,
    "Manage Expressions": 1 << 30,
    "Use Application Commands": 1 << 31,
    "Manage Events": 1 << 33,
    "Manage Threads and Posts": 1 << 34,
    "Send Messages in Threads": 1 << 38,
    "Timeout Members": 1 << 40,
}


@dataclass(frozen=True)
class ChannelSpec:
    category: str
    name: str
    topic: str
    channel_type: int = 0



# Old per-variant category names, kept only so the sync can find and
# delete them (see DELETE_CATEGORIES/DELETE_CHANNELS below).

# strategies (1-Minute, 5-Minute, Key-Levels, Expansion-Level) - owner:
# and just have a similar dashboard for the other trader types so the
# homepage can be clean and we can still see all the results... tabs can
# stay meaningful and not scattered craziness." Each strategy still gets
# its own independently-tracked card (see
# performance_reconciliation.REPORT_ROUTES) - only the real channel every
# strategy's logical key resolves to changed.
STRATEGIES_CATEGORY_NAME = "STRATEGIES"
_OLD_STRATEGY_CATEGORY_NAMES = [
    "1-MINUTE STRATEGY", "5-MINUTE STRATEGY", "KEY-LEVELS STRATEGY", "EXPANSION-LEVEL STRATEGY",
]

CATEGORY_ORDER = [
    "START HERE",
    "COMMUNITY",
    "MARKET INTELLIGENCE",
    "LEARNING CENTER",
    "SYSTEM",
    "RIVALRY",
    "OWNER CONTROL",
]

# Phase 3 purge (Master Spec Section 2: "trader-specific Discord state/
# routes/cards/channels"). LIVE TRADING DESK, PERFORMANCE, STRATEGY CONTROL,
# and STRATEGIES all held only per-strategy or aggregate-trade-output
# channels (new-positions, wins, losses, trade-journal, backtest-results,
# strategy-control/settings/versions, daily/weekly/monthly recaps) - nothing
# in them is generic infrastructure. Added to DELETE_CATEGORIES below so a
# future, owner-triggered sync run cleans them up on the live server; this
# pass does not run that sync itself.

CHANNELS = [
    ChannelSpec("START HERE", "welcome", "What Tradysquids is, paper-trading status, and navigation."),
    ChannelSpec("START HERE", "rules-and-risk", "Rules, options risk, educational-only disclaimer, privacy, and conduct."),
    ChannelSpec("START HERE", "how-to-use-tradebot", "TradeBot commands, examples, schedules, and data limitations."),
    ChannelSpec("START HERE", "how-trades-are-found", "Transparent scanner discovery, qualification, play-selection, and rejection rules."),
    ChannelSpec("COMMUNITY", "general-chat", "The main member conversation channel."),
    ChannelSpec("MARKET INTELLIGENCE", "premarket", "Premarket universe, gaps, calendars, and scheduled events."),
    ChannelSpec("MARKET INTELLIGENCE", "breaking-alerts", "Deduplicated TradingView and provider events."),
    ChannelSpec("MARKET INTELLIGENCE", "charts-and-levels", "Requested and scheduled charts, support, and resistance."),
    ChannelSpec("MARKET INTELLIGENCE", "news-and-events", "Cached company and market news with timestamps."),
    ChannelSpec("MARKET INTELLIGENCE", "market-regime", "Broad-market context, trend, and volatility conditions."),
    ChannelSpec("MARKET INTELLIGENCE", "universe-watch", "SPY off-hours screen status and on-demand snapshot."),
    ChannelSpec("MARKET INTELLIGENCE", "spy-technicals", "SPY technical history from the standalone market-memory store: SMA/EMA/VWAP, MACD, RSI, ADX, Bollinger and ATR across intraday, short, medium and long horizons, plus what each tracked pattern is actually worth against the base rate."),
    ChannelSpec("LEARNING CENTER", "learning-index", "Complete organized curriculum and recommended learning path."),
    ChannelSpec("LEARNING CENTER", "07-technical-analysis", "Momentum, trend, volume, volatility indicators, confluence, and invalidation."),
    ChannelSpec("LEARNING CENTER", "ask-tradebot", "Use /ask and /explain for curated educational answers."),
    ChannelSpec("LEARNING CENTER", "examples-and-reviews", "Paper-trade walkthroughs and post-trade reviews."),
    ChannelSpec("SYSTEM", "scanner-status", "Current scanner run state: cycle phase, last completed pass, and next scheduled run."),
    ChannelSpec("SYSTEM", "api-errors", "Provider and Discord API errors, rate limits, and failed requests."),
    ChannelSpec("SYSTEM", "system-health", "Local service health, freshness, queue depth, and restarts."),
    ChannelSpec("SYSTEM", "update-status", "Deploy checks, current commit, and auto-update outcomes."),
    ChannelSpec("SYSTEM", "provider-status", "Tradier, TradingView, Discord, and read-only MCP status."),
    ChannelSpec("OWNER CONTROL", "scanner-controls", "Owner-only universe, filter, and schedule controls."),
    ChannelSpec("OWNER CONTROL", "workflow-log", "Release and deployment history."),
    ChannelSpec("OWNER CONTROL", "upgrade-review", "Member suggestions pending owner approval or decline."),
    ChannelSpec("OWNER CONTROL", "security-log", "Rejected requests and configuration warnings without secrets."),
    # Reconciled 2026-08-19: these are live channels the bot already writes
    # to that had drifted out of this spec entirely. Declared with their
    # CURRENT topics so the sync is a no-op - the point is that a future
    # audit can trust this list, not to change anything now. moderator-only
    # is deliberately NOT declared: it sits outside any category in Discord,
    # so declaring it would move it.
    ChannelSpec("START HERE", "bot-commands", "Complete TradeBot slash-command reference and ticker-context instructions."),
    ChannelSpec("START HERE", "risk-management", "Options risk disclosures and pre-trade safety checklist."),
    ChannelSpec("LEARNING CENTER", "learning-start", "Begin here: learning path, definitions, safety, and how to ask TradeBot."),
    ChannelSpec("SYSTEM", "system-activity", "Always-on interval receipts, off-hours SPY research, event sweeps, and data freshness."),
    ChannelSpec("SYSTEM", "automation-diagnostics", "Missed jobs, overdue intervals, stale runs, automatic repair attempts, retry limits, and unresolved failures."),
    ChannelSpec("OWNER CONTROL", "applied-upgrades", "Verified installed upgrades, affected channels, implementations, and live runtime proof."),
    ChannelSpec("OWNER CONTROL", "upgrade-requests", "Owner-submitted upgrade batches mirrored from any Discord channel."),
    # Phase 9 (Master Spec Section 7): official head-to-head results, lead
    # changes, busts, milestones, and bounded bot-to-bot trash talk -
    # separate from operational trade channels. No persona/response logic
    # exists yet (Phase 11+); this is the channel that work will post into.
    ChannelSpec("RIVALRY", "blacktide-vs-claude", "Official head-to-head competition results, lead changes, busts, milestones, and bounded bot-to-bot rivalry."),
]





# Old per-variant channels (10 categories x 2 channels), retired in favor
# of the shared pair above.

DELETE_CHANNELS = {
    # Retired 2026-08-17 - owner: "we have performance tab for all this".
    # Every strategy now has its own channel, and period recaps live in
    # PERFORMANCE, so this shared pair duplicated both. The cross-strategy
    # leaderboard moved to #monthly-dashboard rather than being lost.
    "strategies-dashboard", "strategies-results",
    # entry measured at essentially zero (+0.0004 ATR/trade, t=+0.39), and
    # of them lost $275k against the SPY_0DTE shape's $156k. Only the
    # locked top-15 strategies survive.
    # Retired 2026-08-19 - owner: "delete held positions as well since
    # that's no longer active". Live cards moved to one held channel per
    # strategy so each gets its own Discord rate-limit bucket; this shared
    # channel had nothing left routing to it. No manual trade has ever been
    # opened (0 SPY_MANUAL rows in the log), so nothing fell back to it
    # either.
    "held-positions",
    "qualified-trades", "scratches", "expired", "exit-alerts",
    "f-dashboard", "f-options-setups", "f-charts", "f-news-events",
    "f-research-performance", "vale-dashboard", "vale-options-setups",
    "vale-charts", "vale-news-events", "vale-research-performance",
    "regular-calls", "regular-puts", "swing-calls", "swing-puts",
    "bull-put-spreads", "bear-call-spreads",
    # Retired in favor of per-strategy 1m-performance/1m-results and
    # 5m-performance/5m-results, now that SPY 0DTE is split into two
    # independently-tracked live strategies instead of one combined read.
    "performance-dashboard", "strategy-results", "strategy-breakdown",
    # instead of 11 different channels."
    # Retired in favor of the single shared strategies-dashboard/
    # instead all the other trades tradebot makes."
    "1m-performance", "1m-results", "5m-performance", "5m-results",
    "key-levels-performance", "key-levels-results",
    "expansion-performance", "expansion-results",
    # Phase 3 purge: per-strategy and aggregate-trade-output channels that
    # lived under the now-deleted LIVE TRADING DESK/PERFORMANCE/STRATEGY
    # CONTROL categories.
    "scanner-feed", "new-positions", "wins", "losses", "trade-journal",
    "backtest-results", "ticker-results", "learning-results",
    "strategy-control", "strategy-settings", "strategy-versions",
    "trade-overrides", "strategy-change-log", "strategy-recommendations",
    "strategy-rules", "daily-recap", "weekly-report", "monthly-dashboard",
}

DELETE_CATEGORIES = {
    "ARCHIVE - LEGACY", "TICKER • F", "TICKER • VALE",
    "LIVE TRADING DESK", "PERFORMANCE", "STRATEGY CONTROL",
    *_OLD_STRATEGY_CATEGORY_NAMES,
    STRATEGIES_CATEGORY_NAME,
}

CHANNEL_STARTERS = {
    "scanner-feed": "Runs every 15 minutes during regular market hours.",
    "new-positions": "Updates only when a paper setup passes every active filter.",
    "wins": "Updates immediately when a tracked paper position closes profitably.",
    "losses": "Updates immediately when a tracked paper position closes without a profit.",
    "premarket": "Updated on weekday premarket research runs.",
    "breaking-alerts": "Event-driven TradingView and provider alerts appear here.",
    "charts-and-levels": "Updated by scheduled research and `/chart` or `/levels` requests.",
    "news-and-events": "Updated by scheduled news checks and `/events` requests.",
    "market-regime": "Updated with broad-market and scanner context.",
    "universe-watch": "Updated by the SPY off-hours screen and on-demand scans.",
    "spy-technicals": "Refreshed once per trading day, shortly after the 3:35pm CT market-memory collection run. Charts show completed sessions - never a live price.",
    "strategies-dashboard": "Updated as each live strategy's paper trades open and close, plus a leaderboard ranking them.",
    "strategies-results": "Updated from every one of those strategies' recorded paper-trade outcomes, each tagged with its own strategy.",
    "ticker-results": "Updated from recorded outcomes grouped by underlying, combined across every live strategy.",
    "learning-results": "Updated by the local learning review.",
    "ask-tradebot": "Use `/ask` or `/explain`; general conversation belongs in #general-chat.",
    "examples-and-reviews": "Paper-trade examples and completed reviews appear here.",
    "scanner-status": "Updated as the scanner cycles through the active universe.",
    "api-errors": "Populated only when a provider or Discord request actually fails.",
    "system-health": "Updated by the local supervisor and engine.",
    "update-status": "Updated on every automatic deploy check.",
    "provider-status": "Shows the current data-provider and webhook status.",
    "strategy-control": "Owner-only; reflects both live SPY 0DTE strategy toggles (1-minute and 5-minute).",
    "strategy-settings": "Mirrors the filters each strategy is currently using.",
    "strategy-versions": "Updated when a strategy's configuration hash changes.",
    "trade-overrides": "Owner-only; a manual override always overrides automatic management.",
    "strategy-change-log": "One entry per strategy-logic change, in plain language.",
    "strategy-recommendations": "Never auto-applied - owner approval required.",
    "workflow-log": "Used for releases, deployments, and rollback reports.",
    "upgrade-review": "Manual owner review only.",
    "security-log": "Receives rejected requests and configuration warnings.",
}



GUIDES = {
    "welcome": """# Tradysquids
Tradysquids is a local-first, paper-trading research system for learning how
options setups are found, tracked, and reviewed. Start with #rules-and-risk,
then use #how-to-use-tradebot and #learning-index. No brokerage orders are placed.""",
    "rules-and-risk": """# Rules, Risk, and Conduct
1. Educational information only—not professional financial advice.
2. Options can lose 100% of premium. Some short-option positions can lose more
than the opening credit or initial deposit.
3. Spreads still carry assignment, exercise, expiration, pin, liquidity,
slippage, and maximum-loss risk.
4. Never promise returns, pressure another member, impersonate a professional,
share private information, spam, harass, or manipulate markets.
5. Verify every quote and contract independently. You alone decide and place
your trades. Paper results and historical performance do not guarantee profit.""",
    "how-to-use-tradebot": """# How to Use TradeBot
Type `/`, choose a command, complete its fields, and send it.
• `/quote`, `/trend`, `/levels`, `/chart` — current market context.
• `/chain`, `/option`, `/setup`, `/risk` — options research and risk examples.
• `/events`, `/calendar` — timestamped research links.
• `/performance`, `/why`, `/status`, `/dataage`, `/lastscan` — tracking.
• `/ask`, `/explain` — educational answers.
• `/filters`, `/ticker-list`, `/ticker-status` — configuration status.
• `/scan-now scope:` — owner-only manual scan and reporting.
The hidden supervisor starts services, checks GitHub for approved releases,
restarts failures, synchronizes Discord, and reports deployments. The system is
paper-trading only and cannot place brokerage orders.""",
    "how-trades-are-found": """# How TradeBot Finds Paper Trades
Nothing is selected randomly. SPY 0DTE is the only strategy family this system
trades, split into two independently-tracked live strategies that run at the
same time and never share a position - #1-minute-strategy and
#5-minute-strategy. They differ in exactly one thing: how often the bot checks
SPY's price to read the opening range and the breakout. Everything else below
is identical for both.

**1. Establish the opening range**
The bot watches SPY's first 30 minutes of trading and records the high/low of
that range from its own bar interval (1-minute or 5-minute). Nothing opens
before the range is established.

**2. Wait for a real breakout**
The first bar to close outside the opening range fires the signal - above for
bullish, below for bearish. A signal fires once per session, at the first
breach, not on every bar that stays outside the range.

**3. Choose an eligible contract**
Same-day (0DTE) expiration only. Absolute delta must be 0.40–0.60 and the
contract must cost $5.00 or less per share ($500 or less per contract). Both
strategies use the same delta band and the same $500-per-trade risk cap - each
one independently, so both can hold a position on the same underlying move at
once.

**4. Manage the position**
Target +50% / stop -50%. Once a trade peaks past +30% profit, the stop raises
ONCE to -15% and holds there - it does not keep trailing behind every tick.
Every position force-closes at end of day; 0DTE never holds overnight.

Quotes, assignment, exercise, slippage, and total-loss risk still require
individual review. Educational only—not financial advice.""",
    "learning-index": """# Complete Learning Center
Use the numbered channels in order, or jump directly to the topic you need.

**Foundations:** #01-market-basics → #02-options-basics → #03-option-chain
**Pricing:** #04-pricing-and-greeks → #05-volatility
**Analysis:** #06-charts → #07-technical-analysis
**Structures:** #08-strategies → #09-spreads
**Risk and execution:** #10-risk-management → #11-trade-management
**Lifecycle:** #12-expiration-assignment → #13-events-and-catalysts
**Improvement:** #14-psychology-journaling → #15-backtesting-stats
**Real-world rules:** #16-taxes-and-rules → #17-scams-and-myths

Use #examples-and-reviews for walkthroughs and `/ask question:` or
`/explain topic:` in #ask-tradebot for definitions. Master maximum loss,
liquidity, and expiration behavior before worrying about clever strategies.""",
    "01-market-basics": """# Market and Stock Basics
Learn what you are trading before adding leverage.

• Stocks represent ownership; ETFs hold baskets; indexes are measurements and
may have cash-settled options rather than shares.
• Know bid, ask, last, midpoint, volume, market capitalization, float, sector,
dividends, splits, and earnings dates.
• Regular, premarket, and after-hours sessions have different liquidity.
• Market, limit, stop, and stop-limit orders solve different problems.
• Gaps, halts, news, and low float can produce poor fills or violent moves.
• Correlated tickers can create one large hidden position.
• Price is not value, and a cheap stock is not automatically safer.

Before options, explain the underlying trend, catalyst, liquidity, support,
resistance, expected holding period, and what proves the idea wrong.""",
    "02-options-basics": """# Options Contract Basics
A call gives its buyer a right to buy; a put gives its buyer a right to sell.
The seller accepts the corresponding obligation if assigned.

Know: underlying, call/put, strike, expiration, DTE, premium, contract
multiplier, moneyness, intrinsic value, extrinsic value, and breakeven at
expiration. One standard equity contract normally controls 100 shares, so a
$0.45 quote generally represents $45 before fees.

Long options can lose the full premium. Short options may create assignment,
margin, and losses beyond the opening credit. ITM, ATM, and OTM describe the
relationship between price and strike, not whether a trade is profitable.
Selling to close differs from exercising; buying to close differs from accepting
assignment. Learn rights, obligations, and maximum loss before any strategy.""",
    "03-option-chain": """# Reading an Option Chain
Read every column instead of shopping by the cheapest premium.

• Expiration and DTE set the time horizon.
• Strike and moneyness shape intrinsic value and sensitivity.
• Bid/ask width estimates friction; midpoint is not a guaranteed fill.
• Volume is today's activity; open interest is existing open contracts.
• Delta, gamma, theta, vega, and IV are estimates, not promises.
• Last trade may be stale and should not replace a current bid/ask.
• Low liquidity increases slippage and makes exits harder.
• Multi-leg orders should be evaluated as one net debit or credit.
• Confirm symbol, side, quantity, expiration, and every strike.

A contract can be directionally correct and still lose from time decay, IV
decline, an expensive entry, weak liquidity, or an undersized move.""",
    "04-pricing-and-greeks": """# Pricing and the Greeks
Option premium combines intrinsic and extrinsic value. Extrinsic value is
influenced by time, implied volatility, rates, dividends, and supply/demand.

• **Delta:** estimated sensitivity to a $1 underlying move.
• **Gamma:** estimated change in delta as the underlying moves.
• **Theta:** estimated effect of one day passing, all else equal.
• **Vega:** estimated sensitivity to a one-point IV change.
• **Rho:** estimated sensitivity to interest rates.
• **Charm/vanna:** advanced cross-effects involving time and volatility.

Greeks move together and change continuously. Near-expiration ATM options can
have extreme gamma and rapid theta. Delta is not a guaranteed probability.
Use scenarios: underlying up/down, IV up/down, and time passing.""",
    "05-volatility": """# Volatility and IV
Historical volatility describes realized movement. Implied volatility is the
movement priced into options.

Learn IV level, IV percentile/rank, expected move, skew, smile, term structure,
event volatility, and volatility crush. High IV can make long premium expensive,
but high does not mean it must fall. Low IV can stay low or expand suddenly.

Earnings often inflate near-term IV and can cause a post-event collapse.
Direction alone may not overcome repricing. Compare expirations and strikes,
not just one IV number. Understand whether a strategy is long or short vega and
whether it benefits from movement, calm, or time. Large premium often prices a
real risk rather than free money.""",
    "06-charts": """# Charts, Candles, and Timeframes
A chart compresses transactions into a visual summary; it does not predict the
future.

Know candle open/high/low/close, bodies, wicks, gaps, volume, trend, range,
breakout, failed breakout, pullback, consolidation, and market structure.
Higher timeframes provide context; lower timeframes show execution noise.
Support and resistance are zones, not magic single prices.

Use consistent sessions and adjusted data. Mark prior highs/lows, gaps, VWAP,
moving averages, trendlines, and volume areas only when they change a decision.
State the thesis, entry area, target area, stop/invalidation, and expected
holding period before selecting the option.""",
    "07-technical-analysis": """# Technical Analysis
Indicators describe price, volume, trend, momentum, or volatility. They are
derived from past data and should support a thesis, not manufacture one.

• Trend: SMA/EMA, slope, higher highs/lows, market structure.
• Momentum: RSI, MACD, rate of change, stochastic.
• Volatility: ATR, Bollinger Bands, range expansion/contraction.
• Participation: volume, relative volume, VWAP.
• Levels: prior highs/lows, gaps, pivots, supply/demand zones.

Learn divergence, confluence, lag, false signals, parameter sensitivity, and
regime dependence. Overbought does not automatically mean sell; oversold does
not automatically mean buy. Five indicators built from the same price series
are not five independent confirmations.""",
    "08-strategies": """# Core Options Strategies
Start with the market view, risk limit, and time horizon, then select a structure.

• Long call / long put: defined premium risk and directional exposure.
• Covered call: stock plus short call; capped upside with full stock downside.
• Protective put: stock plus long put; downside protection with premium cost.
• Collar: covered call plus protective put.
• Cash-secured put: obligation to buy shares at the strike if assigned.
• Synthetic and stock-replacement structures: advanced leverage.
• Straddle/strangle: volatility positions, not simply 'price will move.'

For every strategy know max profit, max loss, breakeven, directional bias,
Greek exposure, assignment risk, capital requirement, ideal conditions, and
what happens if price does nothing.""",
    "09-spreads": """# Spreads and Multi-Leg Positions
Spreads combine options to reshape risk, cost, and Greek exposure.

• Debit vertical: pay a debit for defined directional exposure.
• Credit vertical: receive credit with defined but real maximum loss.
• Calendar/diagonal: different expirations; sensitive to IV and timing.
• Iron condor/butterfly: range-focused structures with narrow profit zones.
• Ratio/backspread: uneven quantities; may contain uncovered risk.

Calculate net debit/credit, width, maximum profit/loss, expiration breakevens,
and buying-power effect. Use one multi-leg limit order when possible. Legging
creates execution and naked-position risk. Defined risk can still lose the full
modeled maximum or behave unexpectedly near expiration.""",
    "10-risk-management": """# Risk Management and Position Sizing
Survival comes before optimization.

Set maximum account risk, trade risk, daily loss, weekly drawdown, open-risk,
sector exposure, and correlated exposure. Position size from the planned loss,
not from unused buying power. Distinguish premium paid, stop-based loss, and
true maximum loss.

Track portfolio delta, theta, vega, and event concentration. Assume slippage and
gaps can exceed a stop. Do not average down without a written rule. Avoid risking
bill, emergency, or borrowed money. A high win rate can still lose if losses are
larger than wins. Ask not only 'Can this win?' but 'What happens when it doesn't?'""",
    "11-trade-management": """# Trade Planning and Management
Write the plan before entry:

1. Thesis and evidence.
2. Exact contract or spread.
3. Entry method and acceptable fill.
4. Maximum loss and size.
5. Target, stop, invalidation, and time stop.
6. Event and overnight policy.
7. Adjustment or rolling rules.
8. Exit order and review fields.

Understand scaling, trailing stops, partial exits, rolling, closing early, and
letting a position expire. Rolling closes one trade and opens another; it does
not erase a loss. Stops on options can fill poorly. Manage the underlying thesis
and the option's liquidity and Greeks together.""",
    "12-expiration-assignment": """# Expiration, Exercise, and Assignment
Expiration is an operational risk event, not just a date on the chain.

Equity-option sellers can be assigned before expiration. ITM contracts may be
automatically exercised under broker/OCC procedures, but deadlines and risk
controls vary. Exercise can create or remove 100 shares per standard contract.
Spreads can become unhedged if only one leg is exercised or assigned.

Learn early assignment, ex-dividend risk, pin risk, after-hours movement,
exercise cutoffs, cash vs physical settlement, American vs European exercise,
and broker liquidation. Never hold a spread into expiration without knowing the
share and cash obligations of every leg.""",
    "13-events-and-catalysts": """# Events and Catalysts
Track earnings, guidance, investor days, product news, analyst actions,
dividends, splits, mergers, regulatory decisions, economic releases, Fed
decisions, inflation, jobs data, and broad-market expiration dates. Confirm
whether the event occurs before open, during market, or after close.

An expected move is not a direction forecast. Good news can fall if expectations
were higher; bad news can rally if feared outcomes were avoided. Event trades
face gaps, IV crush, wide spreads, halts, and poor stop execution. Decide before
entry whether the position intentionally holds through the event.""",
    "14-psychology-journaling": """# Psychology and Journaling
Common traps: FOMO, revenge trading, loss aversion, anchoring, recency bias,
confirmation bias, overconfidence, boredom trades, moving stops, and increasing
size after losses. Use checklists, predefined limits, scheduled breaks, and a
cooldown after rule violations.

Journal setup, regime, contract, Greeks, liquidity, entry, exit, reason,
screenshots, emotions, mistakes, and whether rules were followed. Separate a
good process that lost from a bad process that won. Review weekly and monthly.
Do not rewrite the thesis after seeing the outcome. The journal exists to expose
patterns, not produce flattering autobiography.""",
    "15-backtesting-stats": """# Backtesting, Statistics, and Learning
Measure more than win rate.

Track expectancy, average win/loss, profit factor, maximum drawdown, consecutive
losses, exposure, holding time, MAE/MFE, slippage, fees, and results by regime,
ticker, strategy, DTE, delta, and event context. Use enough trades for a useful
sample and keep out-of-sample data.

Avoid look-ahead bias, survivorship bias, overfitting, data snooping, unrealistic
fills, and changing several rules at once. Paper fills may be better than live
fills. A backtest is evidence about historical rules, not proof of future profit.
Champion/challenger tests need fixed definitions and human review.""",
    "16-taxes-and-rules": """# Accounts, Taxes, and Trading Rules
Broker approval levels, cash/margin treatment, settlement, buying power,
exercise procedures, and day-trading rules vary by firm and can change.

Keep confirmations, statements, fees, assignments, exercises, expirations, and
cost-basis records. Options tax treatment can vary by underlying, holding period,
exercise, assignment, straddles, wash-sale rules, and special contract status.
Do not guess from a social-media post.

Check current broker rules, FINRA/SEC notices, the OCC Options Disclosure
Document, and current IRS Publication 550. Use a qualified tax professional for
your situation. Tradysquids is not tax software or legal advice.""",
    "17-scams-and-myths": """# Scams, Myths, and Red Flags
Red flags include guaranteed returns, secret indicators, impossible win rates,
pressure to act immediately, unverifiable screenshots, deleted losses, paid
signal rooms with no audited history, impersonation, account-access requests,
and requests to send crypto or gift cards.

Myths:
• High win rate automatically means profit.
• Cheap options are low risk.
• Delta is exact probability.
• Selling premium is always safer.
• Defined risk means small risk.
• More indicators mean more confirmation.
• A roll removes the original loss.
• Paper success guarantees live success.

Protect tokens and passwords, verify identities, and never give anyone remote
control of a brokerage account.""",
    "scanner-controls": """# Owner Scanner Controls
`/filters` shows active limits. `/filter-set` changes a guarded local value.
This system trades SPY exclusively - there is no ticker roster to manage.
`/scan-now scope:Everything` immediately runs provider events, market
intelligence, the SPY options scan, position tracking, and health reporting.
The runtime is read-only toward brokerages and cannot place trades.""",
}


def normalized(value: str) -> str:
    return str(value or "").strip().casefold()


def main() -> int:
    load_env()
    apply = "--apply" in sys.argv
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise SystemExit("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required")
    existing = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    if "--inventory" in sys.argv:
        category_names = {
            str(item["id"]): item["name"]
            for item in existing
            if item.get("type") == 4
        }
        for item in sorted(
            existing,
            key=lambda row: (int(row.get("position") or 0), row.get("name") or ""),
        ):
            parent = category_names.get(str(item.get("parent_id") or ""), "(root)")
            print(f"{item.get('type')}\t{parent}\t{item.get('name')}\t{item.get('id')}")
        return 0
    warnings: list[str] = []
    bot_user = tracker._request("GET", "/users/@me")
    roles = tracker._request("GET", f"/guilds/{tracker.guild_id}/roles")
    bot_role = next(
        (
            role
            for role in roles
            if str((role.get("tags") or {}).get("bot_id") or "")
            == str(bot_user.get("id") or "")
        ),
        None,
    )
    bot_role_id = str((bot_role or {}).get("id") or "")
    bot_permissions = int((bot_role or {}).get("permissions") or 0)
    if not apply and bot_permissions & ADMINISTRATOR_PERMISSION:
        warnings.append("TradeBot has Administrator; remove it because Administrator includes bans.")
    if not apply and bot_permissions & BAN_MEMBERS_PERMISSION:
        warnings.append("TradeBot has Ban Members; remove that permission.")
    missing_bot_permissions = [
        name
        for name, permission in BOT_ROLE_REQUIRED_PERMISSIONS.items()
        if not bot_permissions & permission
    ]
    if not apply and missing_bot_permissions:
        warnings.append(
            "TradeBot is missing required non-ban permissions: "
            + ", ".join(missing_bot_permissions)
            + "."
        )
    by_name = {normalized(item.get("name")): item for item in existing}
    categories: dict[str, dict] = {}

    for position, name in enumerate(CATEGORY_ORDER):
        item = next(
            (
                row for row in existing
                if row.get("type") == 4 and normalized(row.get("name")) == normalized(name)
            ),
            None,
        )
        if item is None:
            print(f"{'CREATE' if apply else 'WOULD CREATE'} category {name}")
            if apply:
                item = tracker._request(
                    "POST",
                    f"/guilds/{tracker.guild_id}/channels",
                    {"name": name, "type": 4, "position": position},
                )
        if item:
            categories[name] = item
            if apply and bot_role_id:
                try:
                    tracker._request(
                        "PUT",
                        f"/channels/{item['id']}/permissions/{bot_role_id}",
                        {"type": 0, "allow": str(BOT_CHANNEL_ALLOW), "deny": "0"},
                    )
                except discord_transport.DiscordError as exc:
                    warnings.append(f"TradeBot access to {name}: {exc}")

    for spec in CHANNELS:
        category = categories.get(spec.category)
        item = by_name.get(normalized(spec.name))
        if item is None:
            print(f"{'CREATE' if apply else 'WOULD CREATE'} #{spec.name}")
            if apply:
                item = tracker._request(
                    "POST",
                    f"/guilds/{tracker.guild_id}/channels",
                    {
                        "name": spec.name,
                        "type": spec.channel_type,
                        "parent_id": category["id"],
                        "topic": spec.topic,
                    },
                )
                by_name[normalized(spec.name)] = item
            continue
        changes = {}
        if apply and bot_role_id:
            try:
                tracker._request(
                    "PUT",
                    f"/channels/{item['id']}/permissions/{bot_role_id}",
                    {"type": 0, "allow": str(BOT_CHANNEL_ALLOW), "deny": "0"},
                )
            except discord_transport.DiscordError as exc:
                warnings.append(f"TradeBot access to #{spec.name}: {exc}")
        if category and str(item.get("parent_id") or "") != str(category["id"]):
            changes["parent_id"] = category["id"]
        if spec.channel_type == 0 and str(item.get("topic") or "") != spec.topic:
            changes["topic"] = spec.topic
        if changes:
            print(f"{'UPDATE' if apply else 'WOULD UPDATE'} #{spec.name}")
            if apply:
                try:
                    tracker._request("PATCH", f"/channels/{item['id']}", changes)
                except discord_transport.DiscordError as exc:
                    warnings.append(f"#{spec.name}: {exc}")

    # Deletions report what ACTUALLY happened, not what was attempted.
    #
    # This previously printed "DELETE #x" before trying, and pushed failures
    # into `warnings` where they were easy to miss - so the script reported
    # deleting three objects it had not touched. It also looked the channel up
    # in `by_name`, which only holds channels matched to a ChannelSpec, so any
    # channel being retired (and therefore no longer specced) was silently
    # skipped.
    #
    # Now it searches every existing channel, and on --apply it re-queries the
    # guild afterwards to confirm the object is really gone before claiming it.
    all_by_name = {
        normalized(item.get("name")): item
        for item in existing
        if item.get("type") != 4
    }
    deleted_ids: list[tuple[str, str]] = []
    for name in sorted(DELETE_CHANNELS):
        item = all_by_name.get(normalized(name))
        if not item:
            continue
        if not apply:
            print(f"WOULD DELETE #{name}")
            continue
        try:
            tracker._request("DELETE", f"/channels/{item['id']}")
            deleted_ids.append((name, str(item["id"])))
        except discord_transport.DiscordError as exc:
            print(f"DELETE FAILED #{name}: {exc}")
            warnings.append(f"delete #{name}: {exc}")

    if apply and deleted_ids:
        try:
            remaining = {
                str(item["id"])
                for item in tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
            }
        except discord_transport.DiscordError as exc:
            remaining = set()
            warnings.append(f"could not verify deletions: {exc}")
        for name, channel_id in deleted_ids:
            if channel_id in remaining:
                print(f"DELETE UNCONFIRMED #{name} - still present after delete")
                warnings.append(f"#{name} still present after delete")
            else:
                print(f"DELETE #{name}")

    for category_name in sorted(DELETE_CATEGORIES):
        category = next(
            (
                item
                for item in existing
                if item.get("type") == 4
                and normalized(item.get("name")) == normalized(category_name)
            ),
            None,
        )
        if category:
            print(f"{'DELETE' if apply else 'WOULD DELETE'} category {category_name}")
            if apply:
                try:
                    tracker._request("DELETE", f"/channels/{category['id']}")
                except discord_transport.DiscordError as exc:
                    warnings.append(f"delete category {category_name}: {exc}")

    if apply:
        for channel_name, content in GUIDES.items():
            channel = by_name.get(normalized(channel_name))
            if not channel:
                continue
            try:
                marker = content.splitlines()[0].lstrip("# ").strip()
                _, removed = tracker.upsert_singleton_message(
                    str(channel["id"]), content, marker
                )
                if removed:
                    print(f"REMOVED {removed} duplicate guide card(s) from #{channel_name}")
            except discord_transport.DiscordError as exc:
                warnings.append(f"guide #{channel_name}: {exc}")

        for channel_name, schedule in CHANNEL_STARTERS.items():
            channel = by_name.get(normalized(channel_name))
            if not channel or channel.get("type") != 0:
                continue
            try:
                recent = tracker._request(
                    "GET", f"/channels/{channel['id']}/messages?limit=1"
                )
                if recent:
                    continue
                topic = str(channel.get("topic") or "").strip()
                content = (
                    f"# {channel_name.replace('-', ' ').title()}\n"
                    f"{topic}\n\n**Update behavior:** {schedule}\n"
                    "No information is shown until a real event or scheduled update occurs."
                )
                tracker._request(
                    "POST",
                    f"/channels/{channel['id']}/messages",
                    {"content": content[:2000], "allowed_mentions": {"parse": []}},
                )
            except discord_transport.DiscordError as exc:
                warnings.append(f"starter #{channel_name}: {exc}")

    print("Discord structure synchronized." if apply else "Dry run complete; no Discord changes made.")
    for warning in warnings:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
