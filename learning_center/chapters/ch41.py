"""Chapter 41: Volatility Derivatives."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 41

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="The VIX and Volatility Indexes",
        topics=("VIX", "volatility index"),
        keywords=("VIX", "volatility index"),
        related_concepts=("LC-36-01",),
        sections=(
            Section(
                "What the VIX Measures",
                "The VIX is a widely-referenced index computed from a "
                "broad set of S&P 500 index option prices, representing "
                "the market's aggregate expectation of near-term implied "
                "volatility (Chapter 36) - it is a measurement derived "
                "*from* option prices, not an option itself, and it "
                "cannot be bought or sold directly.",
            ),
            Section(
                "Products Built on the VIX",
                "Futures and options exist on the VIX itself, letting "
                "traders take a position on expected future volatility "
                "somewhat directly, though these products carry their own "
                "distinct mechanics (including their own term structure, "
                "Chapter 39, Lesson LC-39-02) and often behave differently "
                "from a simple 'the VIX will go up or down' intuition "
                "would suggest.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Variance and Volatility Swaps",
        topics=("variance swap", "volatility swap"),
        keywords=("variance swap", "volatility swap"),
        related_concepts=("LC-41-01",),
        sections=(
            Section(
                "Pure Volatility Exposure",
                "A **variance swap** pays out based on the difference "
                "between realized variance (actual squared price moves "
                "over the period) and a variance level agreed at "
                "inception, giving close to pure exposure to realized "
                "volatility without the direction-dependent behavior that "
                "options-based volatility bets (Chapter 36) always carry "
                "to some degree. These are primarily institutional "
                "instruments, mentioned here for completeness rather than "
                "as a strategy most individual traders will directly "
                "access.",
            ),
        ),
    ),
]
