"""Chapter 29: Index Option Products and Futures."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 29

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Index Options vs. Equity/ETF Options",
        topics=("index options", "cash settlement", "European style"),
        keywords=("index options", "SPX vs SPY"),
        related_concepts=("LC-01-06",),
        sections=(
            Section(
                "Key Differences",
                "Broad-market index options (for example on the S&P 500 "
                "index itself, distinct from an ETF tracking it) are "
                "typically **cash-settled** and often **European-style** "
                "(Chapter 1, Lesson LC-01-06) - no shares ever change "
                "hands, and early exercise is not possible. ETF options on "
                "a similar underlying (such as an S&P 500 tracking ETF) "
                "are typically physically settled and American-style. Two "
                "products can track nearly the same index and still behave "
                "differently around exercise, assignment, and settlement.",
            ),
            Section(
                "Why the Distinction Matters",
                "European-style, cash-settled index options remove early-"
                "assignment risk (Chapter 12's diagonal spreads and "
                "collars, for example, behave more predictably without "
                "it), but they cannot be exercised early even when doing "
                "so might otherwise be advantageous - a genuine trade-off "
                "in flexibility, not a strictly better or worse "
                "arrangement.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Options on Futures",
        topics=("futures options", "underlying is a futures contract"),
        keywords=("options on futures",),
        related_concepts=("LC-34-01",),
        sections=(
            Section(
                "The Core Difference",
                "An option on a futures contract has a futures contract, "
                "not shares or cash, as its underlying - exercising it "
                "creates a futures position rather than a stock position "
                "or a cash payment. Chapter 34 covers futures and their "
                "own option strategies in depth; this lesson exists only "
                "to note that 'the underlying' is not always shares or an "
                "index level, and to read a futures option's contract "
                "specifications carefully before assuming equity-option "
                "conventions apply.",
            ),
        ),
    ),
]
