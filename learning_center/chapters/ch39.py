"""Chapter 39: Volatility Trading Techniques."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 39

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Volatility Skew and Smile",
        topics=("volatility skew", "volatility smile"),
        keywords=("volatility skew", "volatility smile"),
        related_concepts=("LC-38-01", "LC-36-01"),
        sections=(
            Section(
                "What Skew Is",
                "**Volatility skew** describes implied volatility "
                "differing by strike for the same underlying and "
                "expiration - commonly, OTM puts trade at higher implied "
                "volatility than OTM calls on equity indexes, reflecting "
                "the market pricing in more perceived crash risk (sudden "
                "large declines) than sudden large rallies. A **volatility "
                "smile** is the related pattern where both OTM calls and "
                "OTM puts trade at higher implied volatility than "
                "at-the-money options.",
            ),
            Section(
                "Why Traders Watch It",
                "Skew directly affects which strikes are relatively "
                "cheap or expensive within the same expiration - a "
                "spread's two legs (Chapters 7, 8, 22) are not shielded "
                "from skew just because they share an expiration, since "
                "each leg's strike can sit at a different point on the "
                "skew curve.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Volatility Term Structure",
        topics=("term structure", "contango", "backwardation"),
        keywords=("volatility term structure", "contango", "backwardation"),
        related_concepts=("LC-09-01", "LC-39-01"),
        sections=(
            Section(
                "Definition",
                "**Term structure** describes how implied volatility "
                "differs across *expirations* for the same strike/"
                "moneyness, separate from skew's across-*strikes* "
                "comparison. Near-term implied volatility rising above "
                "longer-term implied volatility (often around a known "
                "near-term event) or the reverse are both observable "
                "patterns, and directly affect calendar spreads (Chapter "
                "9), whose entire thesis depends on the relationship "
                "between near- and far-term option behavior.",
            ),
        ),
    ),
]
