"""Chapter 17: Put Buying with Stock Ownership."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 17

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="The Protective Put",
        topics=("protective put", "married put", "portfolio insurance"),
        keywords=("protective put", "married put"),
        related_concepts=("LC-04-01", "LC-16-01"),
        sections=(
            Section(
                "Definition",
                "A **protective put** (or married put, when opened at the "
                "same time as the stock) combines owning shares with buying "
                "a put on the same underlying - the mirror image of the "
                "protective call on short stock from Chapter 4, Lesson "
                "LC-04-01. The put acts as insurance: below the strike, "
                "further stock losses are offset dollar-for-dollar by gains "
                "on the put.",
            ),
            Section(
                "The Cost of Insurance",
                "The put's premium is a known, fixed cost, paid regardless "
                "of whether the stock ever falls - exactly like an "
                "insurance premium. If the stock rises or stays flat, the "
                "put simply expires worthless (or is sold for a small "
                "residual value) and that premium is the total cost of "
                "having carried the protection.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk/Reward Profile",
        topics=("maximum loss", "unlimited upside", "floor"),
        keywords=("floor", "downside floor", "unlimited upside"),
        related_concepts=("LC-17-01", "LC-01-05"),
        sections=(
            Section(
                "A Defined Floor, Uncapped Upside",
                "Maximum loss = (stock cost basis - put strike) + put "
                "premium, no matter how far the stock falls beyond the "
                "strike - the put creates a hard floor. Upside remains "
                "completely uncapped, unlike the covered call in Chapter 2: "
                "a protective put only removes downside risk below the "
                "strike, it never limits how much the stock can gain.",
            ),
            Section(
                "Worked Example",
                "100 shares bought at $500.00; $490 put bought for $5.00. "
                "Maximum loss = ($500 - $490) + $5.00 = $15.00 per share, "
                "realized at any price at or below $490, no matter how far "
                "the stock keeps falling. If SPY rallies to $560: the put "
                "expires worthless, the shares gained the full $60.00, "
                "reduced only by the $5.00 already spent on insurance that "
                "was not needed.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="When to Use a Protective Put",
        topics=("suitability", "event risk", "large gains protection"),
        keywords=("when to hedge", "protecting gains"),
        related_concepts=("LC-17-01", "LC-13-01"),
        sections=(
            Section(
                "Common Use Cases",
                "Protective puts are frequently used ahead of a specific "
                "known event with real two-sided risk (earnings, a major "
                "economic release), or to protect a large unrealized gain "
                "in a position the trader does not want to sell outright "
                "(for tax or other reasons - see Chapter 42) while still "
                "wanting exposure to further upside.",
            ),
            Section(
                "Common Mistake",
                "Buying protection reflexively on every position, "
                "regardless of actual risk or cost, treats insurance as "
                "free - over time, the cumulative premium paid for "
                "protection that was rarely needed can exceed what any "
                "single large loss would have cost. Protective puts are "
                "most useful when sized to a specific, identified risk, not "
                "as a permanent default overlay.",
            ),
        ),
    ),
]
