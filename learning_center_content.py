"""Library-grounded stock and options education for TradeBot.

The answer engine indexes the same Markdown lessons synchronized into Discord.
Every answer cites one or more Learning Center channels and section headings.
It does not provide personalized recommendations or invent missing facts.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from learning_center_catalog import LESSONS, LESSON_BY_CHANNEL, ORDERED_CHANNELS

ROOT = Path(__file__).resolve().parent
LIBRARY_PATH = ROOT / "learning_center" / "COMPREHENSIVE_TRADING_LIBRARY.md"
CHANNEL_MAP_PATH = ROOT / "state" / "learning-channel-map.json"
CHANNEL_PATTERN = re.compile(
    r"<!-- CHANNEL:(?P<channel>[a-z0-9-]+) -->\s*"
    r"(?P<body>.*?)\s*"
    r"<!-- END:(?P=channel) -->",
    re.DOTALL,
)
SECTION_PATTERN = re.compile(r"(?m)^##\s+(?P<title>.+?)\s*$")
WORD_PATTERN = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)?")
SENTENCE_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9*`])")

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by",
    "can", "could", "do", "does", "for", "from", "get", "how", "i", "if",
    "in", "is", "it", "me", "my", "of", "on", "or", "should", "so", "that",
    "the", "their", "this", "to", "what", "when", "where", "which", "why",
    "will", "with", "would", "you", "your",
}

# Query expansion improves everyday wording without pretending to be an LLM.
SYNONYM_GROUPS: tuple[tuple[str, ...], ...] = (
    ("stock", "stocks", "share", "shares", "equity", "equities"),
    ("etf", "fund", "exchange traded fund"),
    ("fundamental", "fundamentals", "business quality", "company analysis"),
    ("income statement", "profit and loss", "p and l", "earnings statement"),
    ("balance sheet", "assets liabilities equity"),
    ("cash flow", "cashflow", "free cash flow", "fcf"),
    ("valuation", "fair value", "multiple", "p e", "pe ratio", "dcf"),
    ("bid ask", "bid and ask", "spread width", "market spread"),
    ("stop loss", "stoploss", "stop order", "risk stop"),
    ("chart", "candlestick", "candle", "price action"),
    ("support", "demand zone", "floor"),
    ("resistance", "supply zone", "ceiling"),
    ("moving average", "sma", "ema"),
    ("volume", "relative volume", "rvol", "participation"),
    ("breadth", "advance decline", "market internals"),
    ("interest rate", "interest rates", "rates", "fed", "federal reserve"),
    ("inflation", "cpi", "pce", "producer prices"),
    ("short selling", "short stock", "shorting", "borrow shares"),
    ("position sizing", "size", "risk per trade", "trade size"),
    ("option", "options", "contract", "derivative"),
    ("call", "calls", "call option", "bullish option"),
    ("put", "puts", "put option", "bearish option"),
    ("expiration", "expiry", "dte", "days to expiration"),
    ("in the money", "itm", "moneyness"),
    ("at the money", "atm", "moneyness"),
    ("out of the money", "otm", "moneyness"),
    ("open interest", "oi", "outstanding contracts"),
    ("implied volatility", "iv", "volatility pricing"),
    ("iv crush", "volatility crush", "post earnings volatility"),
    ("delta", "directional greek", "share equivalent"),
    ("gamma", "delta acceleration", "gamma risk"),
    ("theta", "time decay", "decay"),
    ("vega", "volatility sensitivity"),
    ("rho", "rate sensitivity"),
    ("covered call", "buy write", "overwrite"),
    ("cash secured put", "csp", "short put"),
    ("protective put", "insurance put", "downside hedge"),
    ("vertical spread", "debit spread", "credit spread", "bull put", "bear call", "bull call", "bear put"),
    ("calendar spread", "time spread", "calendar"),
    ("diagonal spread", "diagonal", "pmcc", "poor mans covered call"),
    ("iron condor", "condor"),
    ("assignment", "assigned", "option assignment"),
    ("exercise", "exercised", "option exercise"),
    ("pin risk", "expiration near strike"),
    ("earnings", "earnings report", "quarterly results", "guidance"),
    ("psychology", "fomo", "revenge trading", "emotions", "discipline"),
    ("journal", "journaling", "trade review", "post trade review"),
    ("expectancy", "expected value", "average trade"),
    ("backtest", "backtesting", "historical test", "strategy test"),
    ("overfitting", "curve fitting", "data snooping"),
    ("broker", "brokerage", "trading account"),
    ("tax", "taxes", "wash sale", "cost basis"),
    ("research", "sec filing", "10 k", "10 q", "8 k", "edgar"),
    ("scam", "fraud", "fake guru", "signal room", "guaranteed returns"),
)


@dataclass(frozen=True)
class LibrarySection:
    channel: str
    lesson_title: str
    heading: str
    text: str
    normalized: str
    tokens: frozenset[str]
    keywords: frozenset[str]


def normalize(value: str) -> str:
    return " ".join(WORD_PATTERN.findall(str(value or "").casefold()))


def tokens(value: str) -> set[str]:
    return {
        token
        for token in WORD_PATTERN.findall(str(value or "").casefold())
        if len(token) > 1 and token not in STOPWORDS
    }


def _expand_query(value: str) -> tuple[str, set[str], set[str]]:
    normalized = normalize(value)
    query_tokens = tokens(normalized)
    phrases = {normalized} if normalized else set()
    for group in SYNONYM_GROUPS:
        normalized_group = tuple(normalize(item) for item in group)
        if any(
            phrase == normalized
            or phrase in normalized
            or tokens(phrase).intersection(query_tokens)
            for phrase in normalized_group
        ):
            phrases.update(normalized_group)
            for phrase in normalized_group:
                query_tokens.update(tokens(phrase))
    return normalized, query_tokens, phrases


def _strip_markdown(value: str) -> str:
    value = re.sub(r"<!--.*?-->", " ", value, flags=re.DOTALL)
    value = re.sub(r"^#{1,6}\s*", "", value, flags=re.MULTILINE)
    value = value.replace("**", "").replace("__", "").replace("`", "")
    value = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", value)
    return re.sub(r"\s+", " ", value).strip()


def _parse_sections(channel: str, body: str) -> list[LibrarySection]:
    spec = LESSON_BY_CHANNEL[channel]
    matches = list(SECTION_PATTERN.finditer(body))
    sections: list[LibrarySection] = []
    if not matches:
        matches = []
    intro_end = matches[0].start() if matches else len(body)
    intro = body[:intro_end].strip()
    if intro:
        sections.append(_build_section(channel, spec.title, "Overview", intro))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        if section_text:
            sections.append(
                _build_section(channel, spec.title, match.group("title").strip(), section_text)
            )
    return sections


def _build_section(
    channel: str,
    lesson_title: str,
    heading: str,
    text: str,
) -> LibrarySection:
    spec = LESSON_BY_CHANNEL[channel]
    searchable = " ".join(
        [lesson_title, heading, text, " ".join(spec.keywords)]
    )
    return LibrarySection(
        channel=channel,
        lesson_title=lesson_title,
        heading=heading,
        text=text.strip(),
        normalized=normalize(searchable),
        tokens=frozenset(tokens(searchable)),
        keywords=frozenset(tokens(" ".join(spec.keywords))),
    )


@lru_cache(maxsize=1)
def library_sections() -> tuple[LibrarySection, ...]:
    text = LIBRARY_PATH.read_text(encoding="utf-8")
    lessons = {
        match.group("channel"): match.group("body").strip()
        for match in CHANNEL_PATTERN.finditer(text)
    }
    missing = [channel for channel in ORDERED_CHANNELS if channel not in lessons]
    if missing:
        raise RuntimeError("Learning library is missing: " + ", ".join(missing))
    sections: list[LibrarySection] = []
    for channel in ORDERED_CHANNELS:
        sections.extend(_parse_sections(channel, lessons[channel]))
    return tuple(sections)


def _score_section(
    section: LibrarySection,
    normalized_query: str,
    query_tokens: set[str],
    query_phrases: set[str],
) -> float:
    heading_norm = normalize(section.heading)
    title_norm = normalize(section.lesson_title)
    score = 0.0
    if normalized_query and normalized_query == heading_norm:
        score += 1000
    if normalized_query and normalized_query == title_norm:
        score += 900
    if normalized_query and normalized_query in heading_norm:
        score += 450
    if normalized_query and normalized_query in section.normalized:
        score += 260

    heading_tokens = tokens(section.heading)
    title_tokens = tokens(section.lesson_title)
    score += len(query_tokens.intersection(heading_tokens)) * 90
    score += len(query_tokens.intersection(title_tokens)) * 55
    score += len(query_tokens.intersection(section.keywords)) * 45
    overlap = query_tokens.intersection(section.tokens)
    score += len(overlap) * 12
    if query_tokens:
        score += 80 * (len(overlap) / len(query_tokens))

    for phrase in query_phrases:
        if len(phrase) < 3:
            continue
        if phrase == heading_norm:
            score += 400
        elif phrase in heading_norm:
            score += 180
        elif phrase in section.normalized:
            score += 45
    return score


def search_library(query: str, limit: int = 4) -> list[tuple[float, LibrarySection]]:
    normalized_query, query_tokens, query_phrases = _expand_query(query)
    if not normalized_query:
        return []
    ranked = [
        (
            _score_section(section, normalized_query, query_tokens, query_phrases),
            section,
        )
        for section in library_sections()
    ]
    ranked = [item for item in ranked if item[0] >= 45]
    ranked.sort(key=lambda item: (-item[0], ORDERED_CHANNELS.index(item[1].channel), item[1].heading))

    selected: list[tuple[float, LibrarySection]] = []
    seen: set[tuple[str, str]] = set()
    for item in ranked:
        identity = (item[1].channel, item[1].heading)
        if identity in seen:
            continue
        selected.append(item)
        seen.add(identity)
        if len(selected) >= limit:
            break
    return selected


def _channel_ids() -> dict[str, str]:
    try:
        payload = json.loads(CHANNEL_MAP_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return {}
    channels = payload.get("channels") if isinstance(payload, dict) else {}
    return channels if isinstance(channels, dict) else {}


def channel_reference(channel: str) -> str:
    channel_id = str(_channel_ids().get(channel) or "").strip()
    return f"<#{channel_id}>" if channel_id else f"**#{channel}**"


def _relevant_sentences(section: LibrarySection, query: str, limit: int = 1450) -> str:
    plain = _strip_markdown(section.text)
    sentences = [item.strip() for item in SENTENCE_PATTERN.split(plain) if item.strip()]
    if not sentences:
        return plain[:limit]
    _, query_tokens, query_phrases = _expand_query(query)
    scored: list[tuple[float, int, str]] = []
    for index, sentence in enumerate(sentences):
        sentence_norm = normalize(sentence)
        sentence_tokens = tokens(sentence)
        score = len(query_tokens.intersection(sentence_tokens)) * 8
        score += sum(12 for phrase in query_phrases if phrase and phrase in sentence_norm)
        if index == 0:
            score += 3
        scored.append((score, index, sentence))
    best = sorted(scored, key=lambda item: (-item[0], item[1]))[:6]
    chosen_indices = sorted(item[1] for item in best if item[0] > 0)
    if not chosen_indices:
        chosen_indices = list(range(min(4, len(sentences))))
    selected = " ".join(sentences[index] for index in chosen_indices)
    if len(selected) <= limit:
        return selected
    clipped = selected[:limit].rsplit(" ", 1)[0].rstrip(" ,;:")
    return clipped + "…"


def _reference_line(section: LibrarySection) -> str:
    return f"{channel_reference(section.channel)} → **{section.heading}**"


def category_index() -> str:
    groups = (
        ("Stocks and business", LESSONS[0:4]),
        ("Mechanics and analysis", LESSONS[4:12]),
        ("Options", LESSONS[12:19]),
        ("Execution and improvement", LESSONS[19:27]),
    )
    lines = ["# Complete Trading Learning Center"]
    for heading, items in groups:
        lines.append(f"\n**{heading}**")
        for item in items:
            lines.append(f"{channel_reference(item.channel)} · {item.title}")
    lines.append(
        "\nUse `/ask question:` for ordinary-language questions or `/explain topic:` "
        "for one concept. Answers cite the exact library sections used."
    )
    return "\n".join(lines)[:3900]


def _answer_from_matches(question: str, matches: list[tuple[float, LibrarySection]]) -> str:
    primary = matches[0][1]
    lines = [
        f"# {primary.heading}",
        _relevant_sentences(primary, question),
        "",
        "## Learning Center reference",
        _reference_line(primary),
    ]
    related: list[str] = []
    for _, section in matches[1:]:
        reference = _reference_line(section)
        if reference not in related and section.channel != primary.channel:
            related.append(reference)
        if len(related) >= 2:
            break
    if related:
        lines.extend(["", "## Related reading", *[f"• {item}" for item in related]])
    lines.extend(
        [
            "",
            "_Educational information only. Live quotes, current broker rules, and "
            "personal tax or legal circumstances require separate verification._",
        ]
    )
    return "\n".join(lines)[:3900]


def explain(topic_query: str) -> str:
    matches = search_library(topic_query, limit=4)
    if not matches:
        return category_index()
    return _answer_from_matches(topic_query, matches)


def answer(question: str) -> str:
    cleaned = str(question or "").strip()
    matches = search_library(cleaned, limit=5)
    if not matches:
        return (
            f"# No confident library match\nI could not match **{cleaned or 'that question'}** "
            "to the curated trading library with enough confidence. I will not invent "
            "a financial answer. Try the main term with `/explain`, or use "
            f"{channel_reference('learning-index')} to browse all 27 subjects."
        )[:3900]
    return _answer_from_matches(cleaned, matches)


def validate_library_search() -> dict[str, Any]:
    sections = library_sections()
    probes = {
        "What does gamma do near expiration?": "15-option-pricing-greeks",
        "How do I read a balance sheet?": "03-financial-statements",
        "Why can an option lose after earnings even when direction is right?": "16-volatility",
        "What is a stop limit order?": "05-market-mechanics-orders",
        "How do covered calls lose money?": "18-income-and-hedging",
        "What is pin risk?": "21-expiration-assignment",
        "How should I test a strategy without overfitting?": "24-backtesting-statistics",
        "How do I verify a news headline?": "26-research-data-tools",
    }
    failures: list[str] = []
    for query, expected_channel in probes.items():
        matches = search_library(query, limit=1)
        actual = matches[0][1].channel if matches else "none"
        if actual != expected_channel:
            failures.append(f"{query!r}: expected {expected_channel}, got {actual}")
    if failures:
        raise RuntimeError("Learning search validation failed: " + "; ".join(failures))
    return {"sections": len(sections), "probes": len(probes)}


if __name__ == "__main__":
    result = validate_library_search()
    print(
        f"Validated {result['sections']} searchable lesson sections and "
        f"{result['probes']} representative questions."
    )
