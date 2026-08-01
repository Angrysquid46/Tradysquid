"""Curated options-trading education used by TradeBot.

Answers are intentionally educational, concise enough for Discord, and never
personalized recommendations. Current broker, tax, and regulatory rules must be
verified with primary sources and qualified professionals.
"""

from __future__ import annotations

import re
from typing import Any


def topic(title: str, aliases: list[str], answer: str, category: str) -> dict[str, Any]:
    return {
        "title": title,
        "aliases": aliases,
        "answer": answer,
        "category": category,
    }


TOPICS = {
    "stocks-etfs-indexes": topic(
        "Stocks, ETFs, and Indexes",
        ["stock", "stocks", "etf", "etfs", "index", "indexes", "indices", "underlying"],
        "A stock represents ownership in one company. An ETF trades like a stock but holds a basket or follows a strategy. An index is a calculated market measurement and may have cash-settled options rather than deliverable shares. Always confirm the underlying, settlement method, multiplier, trading hours, dividends, and event calendar before using options on it.",
        "Market basics",
    ),
    "quotes-orders": topic(
        "Quotes and Order Types",
        ["bid", "ask", "mid", "midpoint", "market order", "limit order", "stop order", "stop limit", "quote"],
        "The bid is the best displayed buying price; the ask is the best displayed selling price. The midpoint is only a reference. Market orders prioritize execution, limit orders control the worst acceptable price, stop orders become market orders after triggering, and stop-limit orders can fail to fill. Options often require patient limit orders because spreads and displayed sizes can change quickly.",
        "Market basics",
    ),
    "calls": topic(
        "Call Options",
        ["call", "calls", "call option", "buy call", "long call", "short call"],
        "A call buyer has the right, but not the obligation, to buy the underlying at the strike under the contract terms. A long call generally benefits from a sufficiently large and timely rise. The buyer can lose the full premium. A call seller accepts assignment risk and may face substantial or unlimited loss when uncovered.",
        "Options basics",
    ),
    "puts": topic(
        "Put Options",
        ["put", "puts", "put option", "buy put", "long put", "short put"],
        "A put buyer has the right, but not the obligation, to sell the underlying at the strike under the contract terms. A long put generally benefits from a sufficiently large and timely decline. The buyer can lose the full premium. A put seller can be assigned and obligated to buy shares at the strike.",
        "Options basics",
    ),
    "contract-terms": topic(
        "Option Contract Terms",
        ["strike", "strike price", "premium", "expiration", "dte", "multiplier", "contract size", "option symbol"],
        "The strike is the contract price, expiration is the final contract date, DTE means days to expiration, and premium is quoted per share. One standard equity option usually represents 100 shares, so a $0.45 premium normally means $45 per contract before fees. Confirm the complete OCC symbol, side, quantity, expiration, strike, and opening or closing action before sending an order.",
        "Options basics",
    ),
    "moneyness": topic(
        "Moneyness",
        ["itm", "atm", "otm", "in the money", "at the money", "out of the money", "moneyness"],
        "ITM means the option has intrinsic value, ATM means the strike is near the underlying price, and OTM means it has no intrinsic value. Moneyness does not tell you whether the trade is profitable. Profit depends on the premium paid or received, current value, costs, and the complete position.",
        "Options basics",
    ),
    "intrinsic-extrinsic": topic(
        "Intrinsic and Extrinsic Value",
        ["intrinsic", "extrinsic", "time value", "option value"],
        "Intrinsic value is immediate exercise value. Extrinsic value is premium beyond intrinsic value and reflects time, implied volatility, rates, dividends, and supply and demand. Extrinsic value generally decays toward zero by expiration, but it does not decline in a smooth or guaranteed path.",
        "Pricing and Greeks",
    ),
    "breakeven": topic(
        "Breakeven",
        ["breakeven", "break even", "break-even"],
        "Expiration breakeven is strike plus premium for a long call and strike minus premium for a long put. Spread breakevens depend on the net debit or credit and structure. Before expiration, an option can be profitable or unprofitable away from expiration breakeven because time and implied volatility still have value.",
        "Options basics",
    ),
    "option-chain": topic(
        "Reading an Option Chain",
        ["option chain", "chain", "read chain", "contract selection"],
        "Read expiration, strike, bid, ask, last-trade time, volume, open interest, implied volatility, and Greeks. The last price may be stale and the midpoint is not guaranteed. Select a contract that matches the expected holding period, move, risk limit, liquidity, event exposure, and desired Greek profile rather than choosing the cheapest premium.",
        "Option chain",
    ),
    "liquidity": topic(
        "Options Liquidity",
        ["liquidity", "bid ask spread", "spread width", "slippage", "open interest", "volume"],
        "Liquidity affects entry and exit quality. Narrower bid/ask spreads, useful displayed size, volume, and open interest can help, but none guarantees a fill. Wide spreads increase slippage and make stops unreliable. Volume is today's activity; open interest is outstanding contracts. Use executable bid and ask prices, not a stale last trade.",
        "Option chain",
    ),
    "delta": topic(
        "Delta",
        ["delta"],
        "Delta estimates how much option premium may change for a $1 underlying move, all else equal. It also describes directional exposure. Delta changes as price, time, and volatility change. It is sometimes used as a rough probability proxy, but it is not an exact probability or guarantee.",
        "Pricing and Greeks",
    ),
    "gamma": topic(
        "Gamma",
        ["gamma"],
        "Gamma estimates how much delta changes when the underlying moves by $1. Gamma is usually strongest near the money and close to expiration. High gamma can make gains and losses accelerate quickly, which is why short-dated options can behave far more violently than their starting delta suggests.",
        "Pricing and Greeks",
    ),
    "theta": topic(
        "Theta",
        ["theta", "time decay", "decay"],
        "Theta estimates the effect of one day passing, all else equal. Time decay is not perfectly linear and often becomes more urgent near expiration, especially around the money. A correct directional idea can still lose when the move is too small or too slow.",
        "Pricing and Greeks",
    ),
    "vega": topic(
        "Vega",
        ["vega"],
        "Vega estimates how much premium may change for a one-percentage-point change in implied volatility. Long options are generally long vega and short options are generally short vega. Direction can be correct while a long option loses after implied volatility falls.",
        "Pricing and Greeks",
    ),
    "rho": topic(
        "Rho",
        ["rho", "interest rates greek"],
        "Rho estimates sensitivity to interest-rate changes. It is often less important than delta, gamma, theta, and vega for short-dated equity options, but it can matter more for long-dated contracts, rate-sensitive products, and changing interest-rate environments.",
        "Pricing and Greeks",
    ),
    "implied-volatility": topic(
        "Implied Volatility",
        ["iv", "implied volatility", "volatility"],
        "Implied volatility is the movement priced into options, not a direction forecast. Higher IV generally increases option premiums. Compare IV across strikes and expirations and consider event risk, skew, and term structure. High IV can remain high; low IV can expand suddenly.",
        "Volatility",
    ),
    "iv-rank-percentile": topic(
        "IV Rank and Percentile",
        ["iv rank", "iv percentile", "volatility percentile"],
        "IV rank compares current IV with its high and low over a chosen period. IV percentile estimates how often IV was below its current value. Both depend on the lookback and data method. They describe relative history, not whether IV must rise or fall.",
        "Volatility",
    ),
    "skew-term-structure": topic(
        "Skew and Term Structure",
        ["skew", "volatility skew", "smile", "term structure", "iv curve"],
        "Skew describes different IV across strikes. Term structure describes different IV across expirations. Downside puts often carry different IV from upside calls, and event expirations can be priced differently from later months. One IV number cannot describe the whole surface.",
        "Volatility",
    ),
    "iv-crush-expected-move": topic(
        "IV Crush and Expected Move",
        ["iv crush", "volatility crush", "expected move", "earnings move"],
        "Event premiums can include an expected move. After the event, uncertainty may collapse and IV can fall sharply. A long option may lose even when direction is correct if the realized move is smaller than priced. Expected move estimates magnitude, not direction or certainty.",
        "Volatility",
    ),
    "candles-timeframes": topic(
        "Candles and Timeframes",
        ["candles", "candlestick", "wick", "timeframe", "chart timeframe", "ohlc"],
        "A candle shows open, high, low, and close for one period. Bodies and wicks summarize trading, not future certainty. Higher timeframes provide broader context; lower timeframes show more execution detail and noise. Use a timeframe that matches the planned holding period and confirm whether extended-hours data is included.",
        "Charts",
    ),
    "trend-structure": topic(
        "Trend and Market Structure",
        ["trend", "higher highs", "lower lows", "market structure", "breakout", "pullback", "range"],
        "Trend can be described by slope, moving averages, and sequences of higher highs and lows or lower highs and lows. Ranges, breakouts, failed breakouts, pullbacks, and consolidation require different tactics. A lower-timeframe reversal can be only a pullback inside a higher-timeframe trend.",
        "Charts",
    ),
    "support-resistance": topic(
        "Support and Resistance",
        ["support", "resistance", "levels", "supply", "demand"],
        "Support and resistance are zones where behavior previously changed. They are context, not guaranteed barriers. Prior highs and lows, gaps, volume areas, VWAP, and moving averages may help define them. A useful level includes an invalidation rule, not merely a line drawn after price turned.",
        "Charts",
    ),
    "moving-averages-vwap": topic(
        "Moving Averages and VWAP",
        ["sma", "ema", "moving average", "vwap"],
        "SMA gives equal weight to prices in its window; EMA weights recent prices more heavily. VWAP measures volume-weighted average price for the selected session or anchor. These tools describe trend and positioning but lag price and can fail in ranges or fast regime changes.",
        "Technical analysis",
    ),
    "rsi-macd": topic(
        "RSI and MACD",
        ["rsi", "macd", "momentum indicator", "overbought", "oversold"],
        "RSI summarizes recent momentum on a 0-100 scale. Overbought can mean strong momentum, not an automatic short; oversold can mean strong selling, not an automatic long. MACD compares moving-average relationships and is also lagging. Use momentum with trend, levels, volume, and invalidation.",
        "Technical analysis",
    ),
    "atr-bollinger": topic(
        "ATR and Bollinger Bands",
        ["atr", "average true range", "bollinger", "bollinger bands", "volatility indicator"],
        "ATR estimates recent movement size and has no directional prediction. Bollinger Bands place volatility-based bands around a moving average. Expanding bands can accompany movement; contracting bands can precede expansion but do not predict direction. These tools can inform stops and targets only when matched to the setup and timeframe.",
        "Technical analysis",
    ),
    "long-options": topic(
        "Long Calls and Puts",
        ["long option", "long call strategy", "long put strategy", "buying options"],
        "Long calls and puts offer defined premium risk but require direction, movement size, timing, liquidity, and volatility to cooperate. Maximum loss is generally the premium paid. Before entry define the underlying thesis, DTE, delta, IV, maximum loss, target, stop, time stop, and event policy.",
        "Strategies",
    ),
    "covered-call-csp": topic(
        "Covered Calls and Cash-Secured Puts",
        ["covered call", "cash secured put", "csp", "wheel"],
        "A covered call combines long shares with a short call, capping upside while retaining substantial stock downside. A cash-secured put accepts an obligation to buy shares at the strike if assigned. Premium does not eliminate stock risk. The wheel is a sequence of these obligations, not a guaranteed-income machine.",
        "Strategies",
    ),
    "protective-put-collar": topic(
        "Protective Puts and Collars",
        ["protective put", "collar", "hedge", "insurance put"],
        "A protective put adds downside protection to long shares at the cost of premium. A collar adds a short call to help finance the put, usually capping upside. Evaluate the net cost, protection level, expiration mismatch, tax consequences, and assignment risk.",
        "Strategies",
    ),
    "straddle-strangle": topic(
        "Straddles and Strangles",
        ["straddle", "strangle", "long volatility", "short volatility"],
        "Long straddles and strangles need movement large enough to overcome premium and decay; they are not simply bets that price moves. Short versions collect premium but can face substantial or unlimited risk. Compare the priced expected move, IV, event timing, and exit plan.",
        "Strategies",
    ),
    "vertical-spreads": topic(
        "Vertical Debit and Credit Spreads",
        ["vertical", "debit spread", "credit spread", "bull call", "bear put", "bull put", "bear call"],
        "A vertical combines options of the same type and expiration at different strikes. Debit spreads pay for defined directional exposure; credit spreads receive premium with defined but real maximum loss. Calculate width, net debit or credit, maximum profit, maximum loss, breakeven, and assignment risk before entry.",
        "Spreads",
    ),
    "calendar-diagonal": topic(
        "Calendars and Diagonals",
        ["calendar spread", "diagonal spread", "time spread", "poor mans covered call", "pmcc"],
        "Calendars use the same strike across different expirations; diagonals also vary strike. They depend on timing, price location, and IV differences between expirations. The front short option can be assigned, and the long option may not offset the position as expected. Model both expiration paths.",
        "Spreads",
    ),
    "condor-butterfly": topic(
        "Iron Condors and Butterflies",
        ["iron condor", "iron butterfly", "butterfly", "broken wing butterfly"],
        "Condors and butterflies shape range-focused risk with multiple legs. They can have narrow profit zones, poor fills, and fast gamma near expiration. Defined risk can still equal the full spread loss. Evaluate each wing, net credit or debit, breakpoints, commissions, and expiration management.",
        "Spreads",
    ),
    "position-sizing": topic(
        "Position Sizing",
        ["position size", "sizing", "risk per trade", "max loss", "account risk"],
        "Choose size from the planned and maximum loss, not from unused buying power. Set trade, daily, weekly, portfolio, and drawdown limits. Include slippage, fees, gaps, correlation, and assignment obligations. Low premium does not automatically mean low risk, and a stop does not guarantee the planned exit price.",
        "Risk management",
    ),
    "portfolio-risk": topic(
        "Portfolio and Correlation Risk",
        ["portfolio risk", "correlation", "portfolio greeks", "concentration", "sector exposure"],
        "Several small positions can combine into one large directional, volatility, theta, sector, or event bet. Track total delta, theta, vega, maximum loss, ticker and sector concentration, expiration concentration, and correlated underlyings. Diversification by ticker name is not diversification when every position depends on the same market move.",
        "Risk management",
    ),
    "trade-plan": topic(
        "Trade Planning",
        ["trade plan", "entry plan", "exit plan", "target", "stop", "invalidation", "time stop"],
        "Before entry write the thesis, evidence, exact contract, acceptable fill, maximum loss, size, target, stop, invalidation, time stop, event policy, overnight policy, adjustment rules, and exit method. A plan written after the trade moves is a story, not a plan.",
        "Trade management",
    ),
    "rolling": topic(
        "Rolling Options",
        ["roll", "rolling", "roll out", "roll up", "roll down"],
        "Rolling closes one position and opens another. It can change strike, expiration, credit, risk, and thesis, but it does not erase the original realized gain or loss. Evaluate the new position independently, including its maximum loss, buying power, assignment risk, and reason for existing.",
        "Trade management",
    ),
    "exercise-assignment": topic(
        "Exercise and Assignment",
        ["exercise", "assignment", "assigned", "auto exercise", "early assignment"],
        "Exercise is the buyer using the contract right; assignment is the seller being required to fulfill it. Equity options can be assigned before expiration. Exercise or assignment can create or remove 100 shares per standard contract. Broker deadlines, automatic-exercise procedures, and risk controls vary and must be verified.",
        "Expiration and assignment",
    ),
    "pin-dividend-risk": topic(
        "Pin and Dividend Assignment Risk",
        ["pin risk", "dividend risk", "ex dividend", "ex-dividend", "expiration risk"],
        "Pin risk occurs when the underlying finishes near a strike and exercise outcomes are uncertain, including after-hours movement. Short calls can face early assignment around ex-dividend dates when remaining extrinsic value is small. Multi-leg spreads can become unhedged if legs are handled differently.",
        "Expiration and assignment",
    ),
    "earnings-events": topic(
        "Earnings and Catalysts",
        ["earnings", "catalyst", "fed", "cpi", "jobs report", "economic event", "news event"],
        "Earnings, guidance, economic releases, regulatory decisions, dividends, and corporate actions can cause gaps and volatility repricing. Confirm event timing and decide before entry whether the trade intentionally holds through it. Good news can fall when expectations were higher; expected move is not a direction forecast.",
        "Events and catalysts",
    ),
    "psychology": topic(
        "Trading Psychology",
        ["psychology", "fomo", "revenge trading", "loss aversion", "overtrading", "discipline", "bias"],
        "Common traps include FOMO, revenge trading, anchoring, loss aversion, recency bias, confirmation bias, boredom trades, moving stops, and increasing size after losses. Use checklists, fixed limits, breaks, and cooldowns after rule violations. A winning rule violation is still a process failure.",
        "Psychology and journaling",
    ),
    "journal": topic(
        "Trading Journal",
        ["journal", "journaling", "trade review", "post trade review"],
        "Record setup, regime, contract, Greeks, IV, liquidity, entry, exit, reason, screenshot, emotion, mistake, and whether rules were followed. Separate good-process losses from bad-process wins. Review patterns by strategy, ticker, DTE, delta, regime, event context, and execution quality.",
        "Psychology and journaling",
    ),
    "expectancy-stats": topic(
        "Expectancy and Performance Statistics",
        ["expectancy", "win rate", "profit factor", "average win", "average loss", "drawdown", "performance stats"],
        "Win rate alone is incomplete. Expectancy combines win probability, average win, and average loss. Also track profit factor, maximum drawdown, consecutive losses, exposure, holding time, fees, slippage, MAE, and MFE. A high-win-rate strategy can lose when occasional losses are much larger than wins.",
        "Backtesting and statistics",
    ),
    "backtesting": topic(
        "Backtesting and Overfitting",
        ["backtest", "backtesting", "overfitting", "look ahead bias", "survivorship bias", "out of sample"],
        "A useful backtest uses realistic fills, costs, timing, and rules that were knowable at the time. Avoid look-ahead bias, survivorship bias, data snooping, cherry-picked periods, and repeated parameter tuning. Use validation and out-of-sample data. Historical performance is evidence under assumptions, not proof of future profit.",
        "Backtesting and statistics",
    ),
    "paper-trading": topic(
        "Paper Trading",
        ["paper trade", "paper trading", "simulation", "simulated fills"],
        "Paper trading tests process without cash risk, but simulated fills can be better than live fills and do not reproduce emotion, assignment, margin, or liquidity perfectly. Record conservative executable prices, follow the same rules as live trading, and require a meaningful sample before drawing conclusions.",
        "Backtesting and statistics",
    ),
    "accounts-taxes-rules": topic(
        "Accounts, Taxes, and Trading Rules",
        ["tax", "taxes", "wash sale", "pdt", "pattern day trader", "settlement", "margin", "cash account", "broker approval"],
        "Broker approval, margin, settlement, exercise procedures, buying power, and active-trading restrictions vary and can change. Tax treatment can depend on the underlying, holding period, exercise, assignment, straddles, wash-sale rules, and special contract status. Verify current broker, FINRA, SEC, OCC, and IRS information and use a qualified professional for personal advice.",
        "Rules and taxes",
    ),
    "scams-myths": topic(
        "Scams and Trading Myths",
        ["scam", "guru", "signal room", "guaranteed returns", "myth", "fake trader"],
        "Red flags include guaranteed returns, secret indicators, unverifiable screenshots, deleted losses, pressure to act, credential requests, impersonation, and payment by crypto or gift card. Myths include: high win rate guarantees profit, cheap options are safe, delta is exact probability, selling premium is always safer, and paper success guarantees live success.",
        "Scams and myths",
    ),
}


def normalize(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).split())


def match_topic(query: str) -> dict[str, Any] | None:
    normalized = normalize(query)
    if not normalized:
        return None
    best: tuple[int, dict[str, Any]] | None = None
    query_tokens = set(normalized.split())
    for item in TOPICS.values():
        phrases = [item["title"], *item["aliases"]]
        score = 0
        for phrase in phrases:
            candidate = normalize(phrase)
            if normalized == candidate:
                score = max(score, 1000 + len(candidate))
            elif candidate and candidate in normalized:
                score = max(score, 500 + len(candidate))
            else:
                overlap = len(query_tokens.intersection(candidate.split()))
                score = max(score, overlap * 20)
        if score and (best is None or score > best[0]):
            best = (score, item)
    return best[1] if best else None


def category_index() -> str:
    categories: dict[str, list[str]] = {}
    for item in TOPICS.values():
        categories.setdefault(item["category"], []).append(item["title"])
    lines = ["📚 **Learning Center topics**"]
    for category, titles in categories.items():
        preview = ", ".join(titles[:5])
        if len(titles) > 5:
            preview += f", +{len(titles) - 5} more"
        lines.append(f"**{category}:** {preview}")
    lines.append("Ask `/ask question:` in ordinary language or use `/explain topic:`.")
    return "\n".join(lines)[:1900]


def explain(topic_query: str) -> str:
    item = match_topic(topic_query)
    if not item:
        return category_index()
    return (
        f"📚 **{item['title']}**\n{item['answer']}\n\n"
        f"Category: **{item['category']}** · Educational information only."
    )[:1950]


def answer(question: str) -> str:
    item = match_topic(question)
    if not item:
        return (
            f"**Question:** {question.strip()}\n\n"
            "I do not have a confident curated match for that wording yet. "
            "Use `/explain topic:` with a specific term or check #learning-index. "
            "I will not invent a financial answer."
        )[:1950]
    return (
        f"**Question:** {question.strip()}\n\n"
        f"**{item['title']}:** {item['answer']}\n\n"
        f"Category: **{item['category']}** · Educational information only."
    )[:1950]
