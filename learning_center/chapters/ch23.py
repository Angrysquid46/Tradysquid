"""Chapter 23: Spreads Combining Calls and Puts."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 23

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="The Iron Condor",
        topics=("iron condor", "defined-risk range trade"),
        keywords=("iron condor",),
        related_concepts=("LC-08-01", "LC-22-02", "LC-20-01"),
        sections=(
            Section(
                "Mechanics",
                "An **iron condor** combines a bear call spread (Chapter "
                "8) above the current price with a bull put spread "
                "(Chapter 22, Lesson LC-22-02) below it, all four legs "
                "same expiration. It collects a net credit and profits if "
                "the underlying stays between the two short strikes "
                "through expiration - the defined-risk version of the "
                "short straddle's 'bet on low movement' (Chapter 20), "
                "referenced there as the alternative to unlimited two-"
                "sided risk.",
            ),
            Section(
                "Max Profit, Max Loss, Worked Example",
                "Maximum profit = net credit collected, between the two "
                "short strikes. Maximum loss = (width of either spread) - "
                "net credit, beyond either long strike - defined and known "
                "on both sides, unlike the short straddle. Example: sell "
                "the $510 call/buy $520 call for $1.50 credit, sell the "
                "$490 put/buy $480 put for $1.50 credit - total credit "
                "$3.00, max loss $10.00 - $3.00 = $7.00 on either side.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="The Collar",
        topics=("collar", "protective collar"),
        keywords=("collar", "protective collar"),
        related_concepts=("LC-02-01", "LC-17-01"),
        sections=(
            Section(
                "Mechanics",
                "A **collar** combines a covered call (Chapter 2) with a "
                "protective put (Chapter 17) on the same shares - selling "
                "an OTM call and buying an OTM put, often structured so the "
                "call's premium substantially offsets or fully pays for "
                "the put. It caps upside at the call strike and floors "
                "downside at the put strike, narrowing the position's "
                "entire range of outcomes to the band between them.",
            ),
            Section(
                "When It Is Used",
                "Collars are common for large, concentrated stock "
                "positions where the holder wants to sharply reduce risk "
                "cheaply (often near zero net cost) without selling the "
                "shares outright, typically accepting a hard cap on upside "
                "as the price for downside protection that costs little or "
                "nothing out of pocket.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="The Iron Butterfly",
        topics=("iron butterfly",),
        keywords=("iron butterfly",),
        related_concepts=("LC-10-01", "LC-23-01"),
        sections=(
            Section(
                "Mechanics",
                "An **iron butterfly** sells a call and a put at the same "
                "(middle) strike - like a short straddle (Chapter 20) - and "
                "buys a further OTM call and put to cap the risk on each "
                "side, like an iron condor's protective wings. It is "
                "economically similar to the butterfly spread in Chapter "
                "10, built from a straddle sale plus protection instead of "
                "a bull spread plus a bear spread, and shares that "
                "chapter's narrow-range, pinned-price thesis.",
            ),
        ),
    ),
]
