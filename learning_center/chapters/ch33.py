"""Chapter 33: Mathematical Considerations for Index Products."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 33

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Index Value vs. Tradable Price",
        topics=("index construction", "tracking difference"),
        keywords=("index math", "tracking difference"),
        related_concepts=("LC-29-01",),
        sections=(
            Section(
                "Why an Index and Its ETF Are Not Identical",
                "A published index value is typically a weighted "
                "calculation over its constituents, while an ETF tracking "
                "that index holds real, tradable shares plus cash, incurs "
                "fees, and can trade at a small premium or discount to its "
                "underlying holdings - the two numbers move together "
                "closely but are not mathematically identical, and options "
                "on the index itself versus options on the tracking ETF "
                "(Chapter 29, Lesson LC-29-01) inherit that gap.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Dividend Adjustments in Index Pricing",
        topics=("dividend drag", "index option pricing"),
        keywords=("dividends and index options",),
        related_concepts=("LC-33-01",),
        sections=(
            Section(
                "Why Dividends Matter for Option Pricing",
                "Expected dividends over an option's life reduce a call's "
                "value and increase a put's value relative to a "
                "dividend-free underlying, since the underlying's price "
                "is expected to drop by roughly the dividend amount on the "
                "ex-dividend date. Index-level dividend assumptions feed "
                "into fair-value option pricing the same way a single "
                "stock's dividend does, just aggregated across every "
                "constituent.",
            ),
        ),
    ),
]
