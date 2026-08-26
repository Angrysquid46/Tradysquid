"""Chapter 38: Distribution of Stock Prices."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 38

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Why Option Pricing Assumes a Price Distribution",
        topics=("probability distribution", "lognormal assumption"),
        keywords=("price distribution", "lognormal"),
        related_concepts=("LC-36-01",),
        sections=(
            Section(
                "The Basic Idea",
                "Option pricing models translate a view on how likely "
                "different future prices are into a fair premium - they "
                "need some assumption about the *shape* of possible future "
                "outcomes, not just a single predicted price. A commonly "
                "used starting assumption models percentage returns as "
                "roughly bell-shaped (normally distributed) around an "
                "expected path, which implies prices themselves follow a "
                "related, right-skewed ('lognormal') shape - prices cannot "
                "go below zero, but can rise without a symmetric upper "
                "limit.",
            ),
            Section(
                "Where the Assumption Breaks Down",
                "Real markets show more large, sudden moves ('fat tails') "
                "than a clean bell-curve assumption predicts - crashes and "
                "sharp spikes happen more often than that simplified model "
                "implies. This is exactly why implied volatility varies by "
                "strike (Chapter 39's volatility skew) rather than being "
                "one flat number across every strike: the market is "
                "pricing in that the simple assumption is imperfect.",
            ),
        ),
    ),
]
