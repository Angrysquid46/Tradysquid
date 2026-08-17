"""Phase 8 - Learning Center expansion, modules 28-128 consolidated.

The source material (`learning update.txt`) defines 101 new modules, 28
through 128, carrying 393 sub-topics between them. Two problems had to be
solved before any of it could go into Discord.

**1. Channel limits.** Discord allows 50 channels per category. One channel
per module would need 101 in LEARNING CENTER alone, on top of the 27
existing ones - 128 total, well past the cap.

**2. The source repeats itself.** The 101 modules are roughly 45 distinct
topics stated 2-4 times. Some are literal duplicates: 36, 48 and 124 are all
"the institutional market clock"; 85 and 127 are both "brokerage mechanics
and margin"; 82, 101 and 125 all cover trading psychology. Others overlap
heavily - order-book microstructure appears as 28, 41, 46, 58, 72 and 117.

So this is deduplicated by TOPIC rather than truncated by count. Every one
of the 393 sub-topics is kept and routed to a themed channel; what is
dropped is the repetition, not the material. A reader gets one dense channel
per subject instead of six thin channels saying the same thing.

Owner direction: "include the first 28 as well so we can have a super huge
learning center but not exceed limits on channels."
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SOURCE = Path(r"C:\Users\strea\OneDrive\Desktop\spy strats\learning update.txt")
CATEGORY = "LEARNING CENTER"

# Discord's hard limit is 50 channels per category. Staying meaningfully
# under it leaves room for the existing curriculum and for later additions
# without another restructure.
MAX_CHANNELS_PER_CATEGORY = 50
CHANNEL_BUDGET = 24


@dataclass
class Topic:
    """One sub-topic lifted from the source, with its module of origin."""
    title: str
    module: int
    body: str = ""


@dataclass
class ExpansionChannel:
    slug: str
    title: str
    summary: str
    modules: tuple[int, ...]
    topics: list[Topic] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Theme map: which source modules belong to which channel.
#
# Curated deliberately rather than derived from slug similarity - the source
# names the same subject several different ways ("order-book
# microstructure", "the-limit-order-book", "understanding-bid-ask-spreads"),
# so string matching would split subjects that belong together and merge ones
# that do not.
# ---------------------------------------------------------------------------

THEMES: tuple[tuple[str, str, str, tuple[int, ...]], ...] = (
    ("market-microstructure", "Market Microstructure & Execution",
     "How the double-sided auction actually works, and what it costs to cross it: "
     "the limit order book, bid/ask spreads, slippage, routing, dark pools and "
     "internalisation.",
     (28, 41, 46, 58, 71, 72, 88, 96, 102, 107, 117)),

    ("volume-and-flow", "Volume, Flow & Tape Reading",
     "Reading participation rather than price: dollar volume, volume z-scores, "
     "volume volatility, breadth, and the tape signatures that separate a real "
     "breakout from a low-volume fake.",
     (29, 77, 78, 123)),

    ("candlestick-and-chart-anatomy", "Candlestick Math & Chart Anatomy",
     "The arithmetic under the bars - body size, upper and lower shadows, "
     "rejection wicks - plus classical patterns and how price rejection actually "
     "prints.",
     (30, 47, 73, 121)),

    ("trend-strength-and-regimes", "Trend Strength, Velocity & Chop Filters",
     "Distinguishing a trend from noise: velocity measures, efficiency ratios, "
     "ADX-style strength, and the filters that switch a strategy off in chop.",
     (31, 122)),

    ("the-greeks", "The Greeks & 0DTE Acceleration",
     "Delta, gamma, theta, vega and rho as working tools, with the way each one "
     "behaves differently on a same-day expiry where gamma dominates and theta "
     "compounds by the minute.",
     (32, 55, 119)),

    ("volatility-surface", "Implied Volatility, Skew & Term Structure",
     "Why the same underlying carries different volatilities at different "
     "strikes and dates, how skew and term structure move, and what a "
     "volatility risk premium is.",
     (33, 42, 56, 57)),

    ("dealer-gamma-and-hedging", "Dealer Gamma, GEX & Market-Maker Hedging",
     "The mechanical flow created when market makers hedge their books: gamma "
     "exposure landscapes, re-hedging pressure, inventory management, and why "
     "price pins near large open interest.",
     (34, 44, 45, 112)),

    ("fair-value-and-mean-reversion", "Fair-Value Anchors & Mean Reversion",
     "The reference prices institutions actually trade around - VWAP, prior-day "
     "levels, settlement anchors - and the conditions under which price reverts "
     "to them rather than trending away.",
     (35, 49)),

    ("the-market-clock", "The Institutional Market Clock",
     "The trading day as a sequence of distinct regimes: the opening auction, "
     "the mid-morning trend window, the lunch lull, the afternoon repositioning, "
     "and the closing imbalance.",
     (36, 48, 124)),

    ("risk-and-backtesting", "Risk Architecture, Backtesting & Stress Testing",
     "Expectancy, profit factor, drawdown, walk-forward validation, backtester "
     "architecture, and the stress tests that separate a real edge from a curve "
     "fit.",
     (37, 52, 84, 98, 115)),

    ("algorithmic-glossary", "Algorithmic Trading, HFT & Bot Logic",
     "The vocabulary and mechanics of automated trading: execution algorithms, "
     "latency, HFT microstructure, and how a bot's logic is specified and "
     "audited.",
     (38, 89, 111)),

    ("moneyness-and-leverage", "Moneyness, Contract Selection & Leverage",
     "ITM, ATM and OTM as regimes rather than labels, how moneyness drives "
     "leverage and probability, and how contract choice changes the trade you "
     "are actually taking.",
     (39, 51, 118)),

    ("expiration-dynamics", "Expiration Dynamics, Assignment & Exotics",
     "Pin risk, assignment and exercise mechanics, settlement, and the exotic "
     "behaviour that shows up as an expiry approaches.",
     (40, 54, 65, 103)),

    ("macro-regimes", "Macro Regimes, Central Banks & Intermarket",
     "Rates, inflation, central-bank policy and the cross-asset relationships "
     "that set the regime a strategy has to survive.",
     (43, 50, 79, 90, 104, 113)),

    ("option-contracts-basics", "Option Contracts: Definitions & Long vs Short",
     "What a contract actually is, the difference between buying and selling "
     "premium, and the obligations each side carries.",
     (53, 66)),

    ("directional-strategies", "Directional & Long-Premium Strategies",
     "Long calls and puts, debit structures, and the conditions under which "
     "paying premium is the right expression of a view.",
     (59, 60)),

    ("neutral-and-multileg", "Market-Neutral, Range-Bound & Multi-Leg",
     "Iron condors, butterflies, calendars and volatility structures - trades "
     "that profit from time or from volatility rather than direction.",
     (61, 62)),

    ("hedging-and-synthetics", "Hedging, Synthetics & Arbitrage",
     "Portfolio protection, synthetic positions, put-call parity, and the "
     "arbitrage relationships that keep option prices honest.",
     (63, 64, 95, 105, 106)),

    ("fundamentals-and-valuation", "Corporate Finance, Valuation & Statements",
     "Fundamentals for context rather than for day trading: statements, "
     "multiples, ratios, and credit analysis.",
     (67, 68, 69, 92)),

    ("indices-and-etfs", "Indices, ETF Structure & Creation Units",
     "How SPY actually works - index construction, ETF creation and redemption, "
     "tracking, and why an ETF can trade away from its basket.",
     (70,)),

    ("gaps-and-oscillators", "Gaps, Oscillators & Volatility Bands",
     "Opening gaps and their statistics, momentum oscillators, mean-reversion "
     "signals, and Bollinger-style statistical bands.",
     (74, 75, 76, 97)),

    ("commodities-and-fixed-income", "Fixed Income, Commodities & Term Structure",
     "Bonds, the yield curve, commodity term structures and contango - the "
     "signals that lead equity regimes.",
     (80, 81, 108)),

    ("psychology-and-journaling", "Psychology, Behavioural Bias & Journaling",
     "The failure modes that are the trader rather than the strategy, plus the "
     "journal and mistake log that make them visible.",
     (82, 91, 101, 116, 120, 125, 126)),

    ("accounts-tax-and-funding", "Accounts, Margin, Tax & Prop Funding",
     "Brokerage mechanics, margin and PDT rules, wash sales and tax treatment, "
     "legal structures, and how prop-firm funding works.",
     (83, 85, 86, 87, 93, 94, 99, 100, 109, 110, 114, 127, 128)),
)


def _clean(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text.strip(" *:-")


def parse_source(path: Path | None = None) -> dict[int, dict[str, Any]]:
    """Pull every module's sub-topics and explanatory text out of the source.

    Content comes from the source rather than being written from scratch, so
    the Learning Center teaches what the owner actually supplied."""
    target = path or SOURCE
    if not target.exists():
        return {}
    raw = target.read_text(encoding="utf-8", errors="replace")
    parts = re.split(r"^## # (\d+)-([a-z0-9\-]+)", raw, flags=re.M)

    modules: dict[int, dict[str, Any]] = {}
    for index in range(1, len(parts) - 1, 3):
        number, slug, body = int(parts[index]), parts[index + 1], parts[index + 2]
        topics: list[Topic] = []
        # Each sub-topic is a "* ## <emoji> Title" line; everything until the
        # next such line is its explanation.
        chunks = re.split(r"^\* ## \S*\s*(.+)$", body, flags=re.M)
        for offset in range(1, len(chunks) - 1, 2):
            title = _clean(chunks[offset])
            detail = _clean(chunks[offset + 1])
            if title:
                topics.append(Topic(title=title, module=number, body=detail))
        modules[number] = {"slug": slug, "topics": topics}
    return modules


def build_channels(path: Path | None = None) -> list[ExpansionChannel]:
    """Themed channels with every source sub-topic routed into one of them."""
    modules = parse_source(path)
    channels: list[ExpansionChannel] = []
    for slug, title, summary, module_numbers in THEMES:
        channel = ExpansionChannel(slug=slug, title=title, summary=summary,
                                   modules=module_numbers)
        seen: set[str] = set()
        for number in module_numbers:
            for topic in modules.get(number, {}).get("topics", []):
                key = topic.title.casefold()
                if key in seen:
                    continue      # same subject repeated across source modules
                seen.add(key)
                channel.topics.append(topic)
        channels.append(channel)
    return channels


def coverage(path: Path | None = None) -> dict[str, Any]:
    """Proof that consolidation dropped repetition and not material."""
    modules = parse_source(path)
    mapped = {number for _slug, _title, _summary, numbers in THEMES for number in numbers}
    all_numbers = set(modules)
    total_topics = sum(len(m["topics"]) for m in modules.values())
    channels = build_channels(path)
    kept = sum(len(c.topics) for c in channels)
    return {
        "source_modules": len(all_numbers),
        "modules_mapped": len(mapped & all_numbers),
        "modules_unmapped": sorted(all_numbers - mapped),
        "source_topics": total_topics,
        "topics_after_dedupe": kept,
        "duplicate_topics_removed": total_topics - kept,
        "channels": len(channels),
        "within_budget": len(channels) <= CHANNEL_BUDGET,
    }
