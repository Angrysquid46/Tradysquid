"""Chapter 10: Butterfly Spread."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 10

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Butterfly Spread",
        topics=("butterfly spread", "long butterfly"),
        keywords=("butterfly spread", "long butterfly"),
        related_concepts=("LC-07-01", "LC-08-01"),
        sections=(
            Section(
                "Definition",
                "A **long butterfly** combines three strikes, all calls (or "
                "all puts), same expiration: buy 1 contract at a lower "
                "strike, sell 2 contracts at a middle strike, buy 1 "
                "contract at a higher strike, with the middle strike evenly "
                "spaced between the outer two. It is equivalent to a bull "
                "spread (Chapter 7) and a bear spread (Chapter 8) sharing "
                "their middle strike, combined into one position.",
            ),
            Section(
                "The Shape of the Bet",
                "A butterfly is opened for a small net debit and profits "
                "most if the underlying finishes exactly at the middle "
                "strike at expiration - it is a bet on low movement, "
                "pinned near a specific price, the opposite kind of thesis "
                "from the directional strategies in Chapters 3 and 7.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Max Profit, Max Loss, and Breakevens",
        topics=("maximum profit", "maximum loss", "breakeven"),
        keywords=("max profit", "max loss", "two breakevens"),
        related_concepts=("LC-10-01", "LC-01-05"),
        sections=(
            Section(
                "The Formulas",
                "Maximum loss = net debit paid, realized at or below the "
                "lowest strike or at or above the highest strike. Maximum "
                "profit = (middle strike - lowest strike) - net debit, "
                "realized exactly at the middle strike. There are two "
                "breakevens, one on each side of the middle strike, "
                "bracketing the range where the position is profitable.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. Buy the $490 call for $14.00, sell 2 of the "
                "$500 calls for $8.00 each ($16.00 total), buy the $510 "
                "call for $4.00. Net debit = $14.00 - $16.00 + $4.00 = "
                "$2.00. Maximum profit = ($500 - $490) - $2.00 = $8.00, "
                "exactly at $500. Maximum loss = $2.00, at or below $490 or "
                "at or above $510.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="When a Butterfly Is Used",
        topics=("low volatility", "pinning", "cheap defined risk"),
        keywords=("low volatility strategy", "pinning"),
        related_concepts=("LC-10-01", "LC-36-01"),
        sections=(
            Section(
                "Expressing a Range-Bound View Cheaply",
                "A butterfly's net debit is typically small relative to "
                "the width between strikes, giving a favorable ratio of "
                "maximum profit to maximum loss for a correctly pinned "
                "outcome - the trade-off is that the profitable range is "
                "narrow, and most outcomes outside it produce the small, "
                "fixed loss.",
            ),
            Section(
                "Common Mistake",
                "Placing the middle strike at the current price out of "
                "convenience rather than at a level the trader actually "
                "expects the underlying to gravitate toward (a known "
                "support/resistance level, a strike with heavy open "
                "interest near expiration, etc.) turns a deliberate pinning "
                "thesis into an arbitrary guess.",
            ),
        ),
    ),
]
