"""Chapter 11: Ratio Call Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 11

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Ratio Call Spread",
        topics=("ratio call spread", "front spread", "back spread setup"),
        keywords=("ratio spread", "1x2 spread"),
        related_concepts=("LC-06-01", "LC-07-01"),
        sections=(
            Section(
                "Definition",
                "A **ratio call spread** buys calls at one strike and sells "
                "a larger number of calls at a higher strike - commonly 1x2 "
                "(buy 1, sell 2) - same expiration. It resembles the bull "
                "spread in Chapter 7 with an extra short call added, "
                "financed by that extra short call's premium, often for a "
                "small net credit or near-zero cost.",
            ),
            Section(
                "Where the Naked Exposure Comes From",
                "The number of short calls exceeds the number of long "
                "calls, so above the upper strike, some short calls are "
                "uncovered - the same unlimited-risk mechanism as ratio "
                "call writing (Chapter 6), just built from all options "
                "instead of options plus stock.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk Profile and Worked Example",
        topics=("maximum profit", "unlimited risk", "upper breakeven"),
        keywords=("max profit", "upper breakeven", "unlimited loss"),
        related_concepts=("LC-11-01", "LC-06-02"),
        sections=(
            Section(
                "Shape of the Payoff",
                "Below the lower strike: small loss or gain equal to the "
                "net cost/credit. Between the strikes: profit grows toward "
                "a maximum at the upper strike. Above the upper strike: the "
                "extra uncovered short call(s) create losses that grow "
                "without bound, exactly like Chapter 6 and Chapter 5's risk "
                "profile.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. Buy 1 $505 call for $6.00, sell 2 $515 calls "
                "for $3.00 each ($6.00 total): net cost = $0.00. Maximum "
                "profit = $10.00 (($515 - $505)), at exactly $515. Above "
                "$515, the single uncovered short call produces unlimited "
                "loss growing dollar-for-dollar past that point, just as in "
                "Chapter 5 - this trade's zero up-front cost does not mean "
                "zero risk.",
            ),
        ),
    ),
]
