"""Chapter 30: Stock Index Hedging."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 30

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Hedging a Portfolio with Index Options",
        topics=("portfolio hedging", "beta", "index puts"),
        keywords=("portfolio hedge", "index put hedge", "beta"),
        related_concepts=("LC-17-01", "LC-29-01"),
        sections=(
            Section(
                "Why Hedge the Index Instead of Each Position",
                "A trader holding many individual stock positions can "
                "buy protective puts (Chapter 17) on a broad index instead "
                "of on every position individually - cheaper and simpler "
                "than hedging each holding separately, at the cost of "
                "imperfect protection: an index hedge only offsets the "
                "portion of the portfolio's risk that actually moves with "
                "the broad market, not risk specific to individual "
                "holdings.",
            ),
            Section(
                "Sizing the Hedge with Beta",
                "**Beta** measures a portfolio's sensitivity to the "
                "broad index - a portfolio with beta 1.2 tends to move "
                "about 20% more than the index itself. Sizing an index "
                "hedge without accounting for beta systematically under- "
                "or over-hedges the actual exposure; a portfolio's dollar "
                "value alone is not enough information to size the hedge "
                "correctly.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="What an Index Hedge Does Not Protect Against",
        topics=("basis risk", "idiosyncratic risk"),
        keywords=("basis risk", "idiosyncratic risk", "unhedged risk"),
        related_concepts=("LC-30-01",),
        sections=(
            Section(
                "Basis and Idiosyncratic Risk",
                "If a portfolio is concentrated in a sector or a handful "
                "of names that move differently from the broad index, an "
                "index hedge can leave substantial risk unaddressed even "
                "while showing a large notional hedge in place - the gap "
                "between the index's move and the portfolio's actual move "
                "is basis risk, and risk specific to individual holdings "
                "(a single company's news, for example) is idiosyncratic "
                "risk. Neither is removed by a broad index hedge, "
                "regardless of its size.",
            ),
        ),
    ),
]
