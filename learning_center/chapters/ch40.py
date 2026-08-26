"""Chapter 40: Advanced Concepts."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 40

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Gamma and Convexity",
        topics=("gamma", "convexity", "delta sensitivity"),
        keywords=("gamma", "convexity"),
        related_concepts=("LC-01-04",),
        sections=(
            Section(
                "What Gamma Adds Beyond Delta",
                "Delta (a first-order sensitivity to the underlying's "
                "move) changes as the underlying moves - **gamma** "
                "measures how fast delta itself changes. High gamma means "
                "a position's directional exposure can shift quickly as "
                "the underlying moves, which matters most for options "
                "near the money and near expiration, where small moves "
                "can swing an option from behaving like a near-worthless "
                "OTM contract to a near-fully-directional ITM one within a "
                "short time.",
            ),
            Section(
                "Why This Matters for 0DTE",
                "Same-day-expiration options (Chapter 1, Lesson LC-01-02) "
                "carry unusually high gamma near the strike, because there "
                "is no time left to smooth out how fast delta changes - "
                "small underlying moves can produce large, fast swings in "
                "an at-the-money 0DTE option's value, more so than an "
                "otherwise-identical option with weeks remaining.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Dealer Positioning and Gamma Exposure",
        topics=("dealer gamma", "hedging flows"),
        keywords=("dealer gamma", "market maker hedging"),
        related_concepts=("LC-40-01",),
        sections=(
            Section(
                "A Higher-Level View",
                "Market makers who sell options typically hedge their own "
                "resulting exposure by trading the underlying - in "
                "aggregate, their collective hedging activity can amplify "
                "or dampen the underlying's own moves, depending on "
                "whether dealers are net long or net short gamma at "
                "prevailing price levels. This is an advanced, higher-"
                "level market-structure topic built entirely on the "
                "gamma concept from Lesson LC-40-01, not a separate new "
                "Greek.",
            ),
        ),
    ),
]
