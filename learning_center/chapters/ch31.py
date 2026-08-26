"""Chapter 31: Index Spreading."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 31

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Inter-Index Spreading",
        topics=("index spread", "relative value"),
        keywords=("index spread", "relative value trade"),
        related_concepts=("LC-30-01", "LC-07-01"),
        sections=(
            Section(
                "The Idea",
                "Rather than taking a directional view on one index, an "
                "**inter-index spread** takes a relative-value view "
                "between two related indexes (for example a broad market "
                "index versus a sector-specific one) - buying options "
                "favoring one and selling options favoring the other, so "
                "the position profits from one outperforming the other "
                "regardless of which direction the broad market moves.",
            ),
            Section(
                "Why This Is Harder Than a Single-Underlying Spread",
                "Unlike the vertical and calendar spreads in earlier "
                "chapters, both legs of an inter-index spread reference "
                "*different* underlyings, so the position's value depends "
                "on the relationship between two separate price series, "
                "each with its own liquidity, bid/ask spread, and "
                "volatility - materially harder to price, execute, and "
                "manage than a same-underlying spread, and worth "
                "attempting only with a genuine, well-researched view on "
                "the relationship itself.",
            ),
        ),
    ),
]
