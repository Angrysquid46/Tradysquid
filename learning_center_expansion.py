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


# ---------------------------------------------------------------------------
# Library emission
# ---------------------------------------------------------------------------
#
# The bot answers /ask and /explain by searching
# learning_center_content.library_sections(), which parses
# learning_center/COMPREHENSIVE_TRADING_LIBRARY.md into one LibrarySection per
# `##` heading. So content only becomes answerable once it is IN that file -
# defining channels alone would create empty tabs the bot could not cite.

LIBRARY_MARKER = "<!-- EXPANSION:modules-28-128 -->"


def render_library_markdown(path: Path | None = None, start_number: int = 31) -> str:
    """Markdown for the 24 consolidated channels, in library format.

    Each source sub-topic becomes its own `##` section, which is the unit the
    bot indexes and cites - so a question about, say, volume z-scores lands on
    that specific section rather than a whole channel."""
    channels = build_channels(path)
    lines = [LIBRARY_MARKER, ""]
    for offset, channel in enumerate(channels):
        number = start_number + offset
        lines.append(f"<!-- CHANNEL:{number:02d}-{channel.slug} -->")
        lines.append(f"# {number:02d} · {channel.title}")
        lines.append("")
        lines.append(channel.summary)
        lines.append("")
        source_list = ", ".join(str(m) for m in channel.modules)
        lines.append(
            f"Consolidated from source modules {source_list}. Those modules "
            f"covered overlapping ground; the material is kept in full here "
            f"with the repetition removed."
        )
        lines.append("")
        for topic in channel.topics:
            lines.append(f"## {topic.title}")
            body = topic.body or (
                f"Covered in source module {topic.module}. See the surrounding "
                f"sections in this channel for the full treatment."
            )
            lines.append(body)
            lines.append("")
        # CHANNEL_PATTERN requires a matching END marker. Without it the whole
        # block is invisible to the parser, so library_sections() reports the
        # channel missing even though its text sits right there in the file -
        # 88KB of content indexed as nothing.
        lines.append(f"<!-- END:{number:02d}-{channel.slug} -->")
        lines.append("")
    return "\n".join(lines) + "\n"


def channel_names(start_number: int = 31, path: Path | None = None) -> list[str]:
    """Discord channel names, numbered to continue the existing curriculum."""
    return [
        f"{start_number + offset:02d}-{channel.slug}"
        for offset, channel in enumerate(build_channels(path))
    ]


def install_into_library(library_path: Path, source: Path | None = None,
                         start_number: int = 31) -> dict[str, Any]:
    """Append (or replace) the expansion block in the library file.

    Idempotent: re-running replaces the previous block rather than appending a
    second copy, which would double every section and make the bot cite
    duplicates."""
    existing = library_path.read_text(encoding="utf-8") if library_path.exists() else ""
    block = render_library_markdown(source, start_number=start_number)
    if LIBRARY_MARKER in existing:
        head = existing.split(LIBRARY_MARKER)[0].rstrip() + "\n\n"
        updated = head + block
        action = "replaced"
    else:
        updated = existing.rstrip() + "\n\n" + block
        action = "appended"
    library_path.write_text(updated, encoding="utf-8")
    return {"action": action, "channels": len(build_channels(source)),
            "chars": len(block)}

# ---------------------------------------------------------------------------
# Where each theme's content actually goes
# ---------------------------------------------------------------------------
#
# 31 LEARNING CENTER channels already exist and 24 new ones would make 55 -
# past Discord's 50-per-category cap, which the owner explicitly said not to
# exceed. But most of the new material is not new SUBJECT matter: 19 of the
# 24 themes cover ground an existing channel already owns.
#
# So the new sections are appended to the existing channel for that subject,
# and only genuinely new subjects get their own channel. Owner: "include the
# first 28 as well so we can have a super huge learning center but not exceed
# limits on channels." That gives one dense channel per subject rather than
# two thin ones competing - and it is the same deduplication applied to the
# curriculum that was applied to the source modules.
#
# theme slug -> existing channel to extend, or None to create a new one.
THEME_TARGETS: dict[str, str | None] = {
    "market-microstructure": "05-market-mechanics-orders",
    "volume-and-flow": "08-volume-breadth-internals",
    "candlestick-and-chart-anatomy": "06-charts-price-action",
    "trend-strength-and-regimes": "07-technical-analysis",
    "the-greeks": "15-option-pricing-greeks",
    "volatility-surface": "16-volatility",
    "dealer-gamma-and-hedging": None,        # no existing channel covers GEX
    "fair-value-and-mean-reversion": None,   # VWAP/anchor mean reversion
    "the-market-clock": None,                # intraday session regimes
    "risk-and-backtesting": "24-backtesting-statistics",
    "algorithmic-glossary": None,            # HFT / bot mechanics
    "moneyness-and-leverage": "14-option-chain-liquidity",
    "expiration-dynamics": "21-expiration-assignment",
    "macro-regimes": "09-macro-sectors-catalysts",
    "option-contracts-basics": "13-options-basics",
    "directional-strategies": "17-directional-options",
    "neutral-and-multileg": "19-spreads-multi-leg",
    "hedging-and-synthetics": "18-income-and-hedging",
    "fundamentals-and-valuation": "04-valuation-and-quality",
    "indices-and-etfs": "01-stock-market-foundations",
    "gaps-and-oscillators": "07-technical-analysis",
    "commodities-and-fixed-income": None,    # rates/commodities term structure
    "psychology-and-journaling": "23-psychology-journaling",
    "accounts-tax-and-funding": "25-brokers-accounts-taxes",
}


def new_channel_themes() -> list[ExpansionChannel]:
    """Only the themes that need a channel of their own."""
    return [c for c in build_channels() if THEME_TARGETS.get(c.slug) is None]


def appended_themes() -> list[tuple[str, ExpansionChannel]]:
    """(existing channel, theme) pairs whose sections extend that channel."""
    return [(THEME_TARGETS[c.slug], c) for c in build_channels()
            if THEME_TARGETS.get(c.slug)]


def channel_budget_check(existing_channel_count: int) -> dict[str, Any]:
    """Proof the result stays under the per-category cap."""
    new = len(new_channel_themes())
    return {
        "existing": existing_channel_count,
        "new_channels": new,
        "total": existing_channel_count + new,
        "cap": MAX_CHANNELS_PER_CATEGORY,
        "within_cap": existing_channel_count + new <= MAX_CHANNELS_PER_CATEGORY,
        "themes_appended_to_existing": len(appended_themes()),
    }


def _sections_markdown(channel: ExpansionChannel) -> str:
    """The `##` sections for one theme, with provenance."""
    lines = [
        f"## {channel.title} — expanded reference",
        f"{channel.summary} Consolidated from source modules "
        f"{', '.join(str(m) for m in channel.modules)}; those modules covered "
        f"overlapping ground, so the material is kept in full with the "
        f"repetition removed.",
        "",
    ]
    for topic in channel.topics:
        lines.append(f"## {topic.title}")
        lines.append(topic.body or (
            f"Covered in source module {topic.module}. See the surrounding "
            f"sections for the full treatment."
        ))
        lines.append("")
    return "\n".join(lines)


BEGIN_TEMPLATE = "<!-- EXPANDED:{slug} -->"
END_TEMPLATE = "<!-- /EXPANDED:{slug} -->"


def install_expansion(library_path: Path, start_number: int = 32) -> dict[str, Any]:
    """Fold the expansion into the library.

    Appended themes are inserted INSIDE the target channel's existing block,
    just before its `<!-- END:channel -->` marker, so they become sections of
    that channel rather than a competing channel. New themes get their own
    block. Idempotent - a previous expansion block is replaced, not stacked,
    since duplicating sections would have the bot cite the same text twice.
    """
    text = library_path.read_text(encoding="utf-8")
    appended = 0

    for target, channel in appended_themes():
        begin = BEGIN_TEMPLATE.format(slug=channel.slug)
        end = END_TEMPLATE.format(slug=channel.slug)
        block = f"{begin}\n\n{_sections_markdown(channel)}\n{end}\n"
        if begin in text:
            head, rest = text.split(begin, 1)
            text = head + block + rest.split(end, 1)[1].lstrip("\n")
        else:
            marker = f"<!-- END:{target} -->"
            if marker not in text:
                continue
            text = text.replace(marker, block + "\n" + marker, 1)
        appended += 1

    new_blocks = []
    for offset, channel in enumerate(new_channel_themes()):
        number = start_number + offset
        slug = f"{number:02d}-{channel.slug}"
        new_blocks.append(
            f"<!-- CHANNEL:{slug} -->\n# {number:02d} · {channel.title}\n\n"
            f"{_sections_markdown(channel)}\n<!-- END:{slug} -->\n"
        )
    joined = "\n".join(new_blocks)
    if LIBRARY_MARKER in text:
        text = text.split(LIBRARY_MARKER)[0].rstrip() + "\n\n"
    text = text.rstrip() + f"\n\n{LIBRARY_MARKER}\n\n" + joined
    library_path.write_text(text, encoding="utf-8")
    return {"appended_to_existing": appended, "new_channels": len(new_blocks),
            "chars": len(text)}


def new_channel_names(start_number: int = 32) -> list[str]:
    return [f"{start_number + offset:02d}-{channel.slug}"
            for offset, channel in enumerate(new_channel_themes())]
