"""Rerank Learning Center search results for precise educational questions.

The base index remains broad. This layer adds deterministic subject routing for
terms whose neighboring topics can otherwise overpower the correct lesson, such
as gamma near expiration, stop-limit orders, IV crush, and pin risk.
"""

from __future__ import annotations

from typing import Any

import learning_center_content as learning


MIN_CONFIDENT_SCORE = 165.0
BASE_SEARCH = learning.search_library
BASE_ANSWER_FROM_MATCHES = learning._answer_from_matches

# required words/phrases, preferred channel, optional preferred heading phrase
ROUTES: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("gamma",), "15-option-pricing-greeks", "gamma"),
    (("delta",), "15-option-pricing-greeks", "delta"),
    (("theta",), "15-option-pricing-greeks", "theta"),
    (("vega",), "15-option-pricing-greeks", "vega"),
    (("rho",), "15-option-pricing-greeks", "rho"),
    (("pin risk",), "21-expiration-assignment", "pin risk"),
    (("stop limit",), "05-market-mechanics-orders", "order types"),
    (("stop-limit",), "05-market-mechanics-orders", "order types"),
    (("iv crush",), "16-volatility", "iv crush"),
    (("volatility crush",), "16-volatility", "iv crush"),
    (("earnings", "option", "lose"), "16-volatility", "iv crush"),
    (("earnings", "direction", "right"), "16-volatility", "iv crush"),
    (("balance sheet",), "03-financial-statements", "balance sheet"),
    (("income statement",), "03-financial-statements", "income statement"),
    (("cash flow",), "03-financial-statements", "cash-flow"),
    (("covered call",), "18-income-and-hedging", "covered calls"),
    (("assignment",), "21-expiration-assignment", "assignment"),
    (("exercise",), "21-expiration-assignment", "exercise"),
    (("overfitting",), "24-backtesting-statistics", "biases"),
    (("news headline",), "26-research-data-tools", "news verification"),
)


def _route_bonus(query: str, channel: str, heading: str) -> float:
    normalized = learning.normalize(query)
    heading_normalized = learning.normalize(heading)
    bonus = 0.0
    for required, preferred_channel, preferred_heading in ROUTES:
        if not all(learning.normalize(term) in normalized for term in required):
            continue
        if channel == preferred_channel:
            bonus += 1200.0
            if learning.normalize(preferred_heading) in heading_normalized:
                bonus += 500.0
    return bonus


def search_library(
    query: str,
    limit: int = 4,
) -> list[tuple[float, learning.LibrarySection]]:
    candidates = BASE_SEARCH(query, limit=80)
    reranked = [
        (float(score) + _route_bonus(query, section.channel, section.heading), section)
        for score, section in candidates
    ]
    reranked.sort(
        key=lambda item: (
            -item[0],
            learning.ORDERED_CHANNELS.index(item[1].channel),
            item[1].heading,
        )
    )
    return reranked[: max(1, limit)]


def confident_matches(
    query: str,
    limit: int = 5,
) -> list[tuple[float, learning.LibrarySection]]:
    matches = search_library(query, limit=limit)
    if not matches or matches[0][0] < MIN_CONFIDENT_SCORE:
        return []
    return matches


def answer_from_matches(
    question: str,
    matches: list[tuple[float, learning.LibrarySection]],
) -> str:
    return BASE_ANSWER_FROM_MATCHES(question, matches)


def answer(question: str) -> str:
    cleaned = str(question or "").strip()
    matches = confident_matches(cleaned, limit=5)
    if not matches:
        return (
            f"# No confident library match\nI could not match **{cleaned or 'that question'}** "
            "to the curated trading library with enough confidence. I will not invent "
            "a financial answer."
        )[:3900]
    return answer_from_matches(cleaned, matches)


def explain(topic: str) -> str:
    matches = confident_matches(topic, limit=4)
    return answer_from_matches(topic, matches) if matches else learning.category_index()


def install() -> None:
    """Make library citations and application references use routed search too."""
    learning.search_library = search_library
    learning.answer = answer
    learning.explain = explain
    learning.confident_matches = confident_matches
    learning.answer_from_matches = answer_from_matches


def validate_search() -> dict[str, Any]:
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
        matches = confident_matches(query, limit=1)
        actual = matches[0][1].channel if matches else "none"
        if actual != expected_channel:
            failures.append(f"{query!r}: expected {expected_channel}, got {actual}")
    if confident_matches("What is the lunar sandwich coefficient?", limit=1):
        failures.append("Unsupported nonsense query was treated as a confident match")
    if failures:
        raise RuntimeError("Routed learning search validation failed: " + "; ".join(failures))
    return {"sections": len(learning.library_sections()), "probes": len(probes) + 1}


if __name__ == "__main__":
    result = validate_search()
    print(
        f"Validated {result['sections']} searchable sections and "
        f"{result['probes']} routed confidence probes."
    )
