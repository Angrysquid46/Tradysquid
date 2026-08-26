"""Chapter 14: Diagonalizing a Spread."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 14

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="What Diagonalizing Means",
        topics=("diagonal spread",),
        keywords=("diagonal spread", "diagonalizing"),
        related_concepts=("LC-07-01", "LC-09-01"),
        sections=(
            Section(
                "Definition",
                "A **diagonal spread** differs in *both* strike and "
                "expiration between its legs - unlike a vertical spread "
                "(Chapter 7/8, same expiration, different strikes) or a "
                "calendar spread (Chapter 9, same strike, different "
                "expirations). 'Diagonalizing' a position means adjusting "
                "one of those two dimensions on an existing spread to "
                "change its behavior - for example rolling a calendar "
                "spread's long leg to a different strike, or a vertical "
                "spread's short leg to a different expiration.",
            ),
            Section(
                "Why Traders Diagonalize",
                "Combining the strike selection of a vertical spread with "
                "the time-decay dynamics of a calendar spread lets a "
                "trader express a directional lean (via differing strikes) "
                "while still benefiting from the differential decay "
                "between a near-term short option and a longer-term long "
                "option (via differing expirations) - a genuinely distinct "
                "third dimension of adjustment beyond the vertical and "
                "calendar structures on their own.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Worked Example",
        topics=("worked example",),
        keywords=("diagonal spread example",),
        related_concepts=("LC-14-01", "LC-09-01"),
        sections=(
            Section(
                "Setup",
                "SPY at $500. Sell the 15-day $510 call for $2.50, buy the "
                "45-day $500 call for $9.00: net debit = $6.50. This "
                "differs from a pure calendar (Chapter 9) by using "
                "different strikes, giving the position a bullish lean - it "
                "benefits both from SPY rising toward $510 and from the "
                "near-term short call's faster time decay, rather than "
                "needing SPY to sit still at one exact strike.",
            ),
        ),
    ),
]
