"""Chapter 18: Buying Puts with Call Purchases."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 18

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Locking In Gains on a Long Call",
        topics=("protective put on a call", "locking in gains"),
        keywords=("protecting call gains", "hedge a long call"),
        related_concepts=("LC-03-01", "LC-17-01"),
        sections=(
            Section(
                "The Situation",
                "A trader holding a long call (Chapter 3) that has moved "
                "significantly in-the-money faces a choice: sell the call "
                "and take the gain, hold and risk giving it back, or buy a "
                "put at the current price to lock in a floor while keeping "
                "the call open. That third option - adding a long put "
                "against an existing long call - is the subject of this "
                "lesson.",
            ),
            Section(
                "How the Combination Behaves",
                "With both a long call (at the original, lower strike) and "
                "a new long put (at a strike near the current, higher "
                "price) open at once, the position now profits both if the "
                "underlying keeps rising (via the call) and, down to the "
                "put's strike, is protected from giving back the gain "
                "already made (via the put) - at the cost of the "
                "additional put premium, which reduces the net locked-in "
                "gain by however much the put costs.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Worked Example",
        topics=("worked example",),
        keywords=("locking in gains example",),
        related_concepts=("LC-18-01", "LC-01-05"),
        sections=(
            Section(
                "Setup",
                "A trader bought the $480 call for $10.00 when SPY was "
                "$480. SPY has since risen to $520; the call is now worth "
                "roughly $42.00 of intrinsic value, an unrealized gain of "
                "about $32.00. To lock in most of that gain while staying "
                "open to further upside, the trader buys the $515 put for "
                "$3.00. Now: if SPY falls back below $515, the put's gains "
                "offset the call's shrinking value, protecting a floor gain "
                "of roughly ($515 - $480) - $10.00 - $3.00 = $22.00, "
                "instead of risking the full original $32.00 unrealized "
                "gain. If SPY keeps rising, the put simply expires "
                "worthless (cost: $3.00) and the call continues "
                "participating fully.",
            ),
        ),
    ),
]
