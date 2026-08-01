"""Canonical ordered catalog for the Tradysquids Learning Center.

This is the single source of truth for channel names, numerical order, lesson
labels, search terms, and migrations from older Learning Center layouts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LessonSpec:
    number: int
    channel: str
    title: str
    topic: str
    keywords: tuple[str, ...]


LESSONS: tuple[LessonSpec, ...] = (
    LessonSpec(1, "01-stock-market-foundations", "Stock and Market Foundations", "Stocks, ETFs, indexes, exchanges, sessions, quotations, ownership, returns, liquidity, and how markets function.", ("stock", "stocks", "etf", "index", "exchange", "market basics", "shares", "ownership")),
    LessonSpec(2, "02-company-fundamentals", "Company Fundamentals and Business Quality", "Business models, competitive advantages, industries, management, customers, suppliers, cyclicality, governance, and qualitative research.", ("fundamental analysis", "business model", "moat", "management", "industry", "company quality", "governance")),
    LessonSpec(3, "03-financial-statements", "Financial Statements and Accounting", "Income statements, balance sheets, cash-flow statements, margins, working capital, debt, dilution, accounting quality, and common red flags.", ("income statement", "balance sheet", "cash flow", "revenue", "earnings", "debt", "free cash flow", "accounting")),
    LessonSpec(4, "04-valuation-and-quality", "Valuation, Growth, and Quality", "Valuation multiples, discounted-cash-flow concepts, growth quality, profitability, capital allocation, expectations, and scenario analysis.", ("valuation", "pe ratio", "p e", "price sales", "ev ebitda", "dcf", "growth", "quality", "fair value")),
    LessonSpec(5, "05-market-mechanics-orders", "Market Mechanics and Order Execution", "Bid and ask, order books, spreads, market and limit orders, stops, auctions, halts, routing, fills, slippage, and execution review.", ("bid", "ask", "order", "limit order", "market order", "stop order", "slippage", "fill", "liquidity")),
    LessonSpec(6, "06-charts-price-action", "Charts, Candles, and Price Action", "Chart construction, candles, timeframes, gaps, trends, ranges, breakouts, pullbacks, support, resistance, and market structure.", ("chart", "candlestick", "price action", "support", "resistance", "breakout", "pullback", "trend", "range")),
    LessonSpec(7, "07-technical-analysis", "Technical Analysis and Indicators", "Moving averages, VWAP, RSI, MACD, ATR, Bollinger Bands, momentum, volatility, confluence, divergence, and indicator failure modes.", ("technical analysis", "indicator", "rsi", "macd", "atr", "bollinger", "moving average", "vwap", "ema", "sma")),
    LessonSpec(8, "08-volume-breadth-internals", "Volume, Breadth, and Market Internals", "Volume analysis, relative volume, volume profile, advance/decline data, breadth, market internals, positioning, and confirmation.", ("volume", "relative volume", "volume profile", "breadth", "advance decline", "market internals", "tick", "trin")),
    LessonSpec(9, "09-macro-sectors-catalysts", "Macroeconomics, Sectors, and Catalysts", "Rates, inflation, employment, currencies, commodities, economic cycles, sector rotation, earnings, news, and catalyst calendars.", ("macro", "inflation", "interest rates", "fed", "cpi", "jobs", "sector", "catalyst", "earnings", "economic cycle")),
    LessonSpec(10, "10-stock-trading-strategies", "Stock Trading Styles and Strategies", "Investing, swing trading, day trading, trend following, momentum, breakouts, mean reversion, event trading, pairs, and strategy selection.", ("stock strategy", "day trade", "swing trade", "investing", "momentum", "mean reversion", "trend following", "breakout strategy")),
    LessonSpec(11, "11-short-selling-margin", "Short Selling, Leverage, and Margin", "Borrowing shares, locates, short squeezes, buy-ins, margin, leverage, inverse products, financing costs, and asymmetric short risk.", ("short selling", "short stock", "margin", "leverage", "borrow fee", "short squeeze", "locate", "buy in")),
    LessonSpec(12, "12-portfolio-risk", "Portfolio Construction and Risk Management", "Position sizing, diversification, correlation, concentration, drawdowns, risk limits, portfolio exposure, hedging, and capital survival.", ("portfolio", "risk management", "position sizing", "correlation", "diversification", "drawdown", "risk per trade", "hedge")),
    LessonSpec(13, "13-options-basics", "Options Foundations", "Calls, puts, contract rights and obligations, strikes, expiration, moneyness, premium, breakeven, exercise styles, and contract deliverables.", ("options basics", "call option", "put option", "strike", "expiration", "dte", "premium", "itm", "atm", "otm")),
    LessonSpec(14, "14-option-chain-liquidity", "Option Chains, Symbols, and Liquidity", "Reading option chains, OCC symbols, expirations, strikes, bid/ask, last price, volume, open interest, contract selection, and fill quality.", ("option chain", "open interest", "option volume", "option liquidity", "occ symbol", "contract selection", "bid ask spread")),
    LessonSpec(15, "15-option-pricing-greeks", "Option Pricing and the Greeks", "Intrinsic and extrinsic value, pricing inputs, delta, gamma, theta, vega, rho, higher-order Greeks, scenario analysis, and Greek interactions.", ("greeks", "delta", "gamma", "theta", "vega", "rho", "intrinsic", "extrinsic", "option pricing", "charm", "vanna")),
    LessonSpec(16, "16-volatility", "Volatility, IV, Skew, and Expected Move", "Historical and implied volatility, IV rank and percentile, realized volatility, skew, term structure, expected move, event premium, and volatility crush.", ("volatility", "iv", "implied volatility", "historical volatility", "iv rank", "iv percentile", "skew", "term structure", "expected move", "iv crush")),
    LessonSpec(17, "17-directional-options", "Directional Options Strategies", "Long calls and puts, debit spreads, stock replacement, synthetic positions, delta selection, DTE selection, and directional trade design.", ("long call", "long put", "debit spread", "directional option", "stock replacement", "synthetic long", "synthetic short")),
    LessonSpec(18, "18-income-and-hedging", "Income, Yield, and Hedging Strategies", "Covered calls, cash-secured puts, protective puts, collars, the wheel, overwriting, hedging, and the risks hidden behind premium income.", ("covered call", "cash secured put", "wheel", "protective put", "collar", "income strategy", "hedging")),
    LessonSpec(19, "19-spreads-multi-leg", "Spreads and Multi-Leg Strategies", "Credit and debit verticals, calendars, diagonals, straddles, strangles, butterflies, condors, ratios, backspreads, legging, and multi-leg risk.", ("spread", "credit spread", "calendar", "diagonal", "iron condor", "butterfly", "straddle", "strangle", "ratio spread", "backspread")),
    LessonSpec(20, "20-trade-planning-execution", "Trade Planning, Execution, and Management", "Thesis construction, entries, exits, stops, targets, time stops, scaling, rolling, adjustments, overnight risk, execution, and post-trade review.", ("trade plan", "entry", "exit", "stop loss", "target", "rolling", "adjustment", "trade management", "execution")),
    LessonSpec(21, "21-expiration-assignment", "Expiration, Exercise, Assignment, and Settlement", "Exercise, assignment, automatic exercise, early assignment, dividends, pin risk, settlement, expiration procedures, and spread expiration failures.", ("expiration", "exercise", "assignment", "assigned", "pin risk", "settlement", "auto exercise", "early assignment", "dividend risk")),
    LessonSpec(22, "22-events-corporate-actions", "Events, Earnings, and Corporate Actions", "Earnings, guidance, dividends, splits, mergers, spin-offs, tender offers, bankruptcies, halts, adjusted options, and event planning.", ("earnings", "corporate action", "dividend", "split", "merger", "spinoff", "tender offer", "bankruptcy", "halt", "adjusted option")),
    LessonSpec(23, "23-psychology-journaling", "Trading Psychology and Journaling", "FOMO, revenge trading, cognitive biases, discipline, routines, emotional regulation, journaling, process scoring, and review practices.", ("psychology", "fomo", "revenge trading", "discipline", "journal", "bias", "emotions", "overtrading")),
    LessonSpec(24, "24-backtesting-statistics", "Backtesting, Statistics, and System Development", "Expectancy, win rate, payoff ratio, profit factor, drawdown, MAE/MFE, sample size, bias, overfitting, validation, and strategy research.", ("backtest", "expectancy", "win rate", "profit factor", "drawdown", "mae", "mfe", "sample size", "overfitting", "out of sample")),
    LessonSpec(25, "25-brokers-accounts-taxes", "Brokers, Accounts, Taxes, and Rules", "Cash and margin accounts, settlement, buying power, options approval, day-trading restrictions, records, taxes, cost basis, and rule verification.", ("broker", "cash account", "margin account", "settlement", "buying power", "options approval", "pdt", "tax", "wash sale", "cost basis")),
    LessonSpec(26, "26-research-data-tools", "Research, Data, Tools, and News Verification", "SEC filings, earnings materials, data quality, screeners, scanners, charting, news verification, calendars, APIs, timestamps, and source evaluation.", ("research", "sec filing", "10 k", "10 q", "8 k", "screener", "scanner", "news", "data quality", "api", "earnings call")),
    LessonSpec(27, "27-scams-security-myths", "Scams, Security, and Trading Myths", "Fraud red flags, fake gurus, signal rooms, impersonation, account security, credential protection, misleading statistics, and common market myths.", ("scam", "guru", "signal room", "fraud", "security", "phishing", "guaranteed returns", "myth", "fake trader")),
)

LESSON_BY_CHANNEL = {item.channel: item for item in LESSONS}
ORDERED_CHANNELS = tuple(item.channel for item in LESSONS)
AUXILIARY_CHANNELS = ("learning-index", "ask-tradebot", "examples-and-reviews")
LEARNING_CHANNEL_ORDER = ("learning-index", *ORDERED_CHANNELS, "ask-tradebot", "examples-and-reviews")

# Old layouts are migrated to the closest new canonical subject. The migration
# preserves useful channel history when the destination does not already exist.
LEGACY_CHANNEL_ALIASES: dict[str, str] = {
    "01-market-basics": "01-stock-market-foundations",
    "01-stock-basics": "01-stock-market-foundations",
    "stock-basics": "01-stock-market-foundations",
    "stocks-basics": "01-stock-market-foundations",
    "market-basics": "01-stock-market-foundations",
    "02-options-basics": "13-options-basics",
    "options-basics": "13-options-basics",
    "option-basics": "13-options-basics",
    "03-option-chain": "14-option-chain-liquidity",
    "option-chain": "14-option-chain-liquidity",
    "04-pricing-and-greeks": "15-option-pricing-greeks",
    "pricing-and-greeks": "15-option-pricing-greeks",
    "05-volatility": "16-volatility",
    "06-charts": "06-charts-price-action",
    "07-technical-analysis": "07-technical-analysis",
    "08-strategies": "17-directional-options",
    "09-spreads": "19-spreads-multi-leg",
    "10-risk-management": "12-portfolio-risk",
    "11-trade-management": "20-trade-planning-execution",
    "12-expiration-assignment": "21-expiration-assignment",
    "13-events-and-catalysts": "22-events-corporate-actions",
    "14-psychology-journaling": "23-psychology-journaling",
    "15-backtesting-stats": "24-backtesting-statistics",
    "16-taxes-and-rules": "25-brokers-accounts-taxes",
    "17-scams-and-myths": "27-scams-security-myths",
}


def lesson_reference(channel: str) -> str:
    item = LESSON_BY_CHANNEL[channel]
    return f"#{item.channel}"
