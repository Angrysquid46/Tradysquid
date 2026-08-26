"""Chapter 20: Sale of a Straddle."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 20

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Short Straddle",
        topics=("short straddle", "selling volatility"),
        keywords=("short straddle", "straddle sale"),
        related_concepts=("LC-05-01", "LC-19-01"),
        sections=(
            Section(
                "Definition",
                "A **short straddle** sells a call and a put at the *same* "
                "strike and expiration, both naked. It collects two "
                "premiums up front and profits if the underlying stays "
                "close to the strike through expiration - a pure bet that "
                "realized movement will be *smaller* than what the "
                "combined premium implies, with no directional lean at "
                "entry.",
            ),
            Section(
                "Combining Two Unlimited-Risk Legs",
                "Both legs are naked (Chapters 5 and 19): the short call "
                "carries unlimited risk to the upside, the short put "
                "carries large risk to the downside. A short straddle "
                "combines both, so it has risk exposure in *both* "
                "directions simultaneously, unlike either leg alone.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Max Profit, Breakevens, and Worked Example",
        topics=("maximum profit", "two breakevens"),
        keywords=("straddle breakeven", "max profit"),
        related_concepts=("LC-20-01", "LC-01-05"),
        sections=(
            Section(
                "The Formulas",
                "Maximum profit = total premium collected (call + put), "
                "realized only if the underlying finishes exactly at the "
                "strike. Breakevens = strike ± total premium - two "
                "breakevens bracketing the strike, defining a range where "
                "the position shows a profit at expiration.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. Sell the $500 call for $6.00 and the $500 "
                "put for $5.50: total premium = $11.50. Breakevens = "
                "$488.50 and $511.50. If SPY finishes at $500: both expire "
                "worthless, full $11.50 kept. If SPY finishes at $530: the "
                "call is $30.00 in-the-money, loss = $30.00 - $11.50 = "
                "$18.50, growing without bound the further SPY continues "
                "to rise.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Risk Management for Short Straddles",
        topics=("risk management", "defined-risk alternative"),
        keywords=("straddle risk management", "iron condor alternative"),
        related_concepts=("LC-20-02", "LC-23-01"),
        sections=(
            Section(
                "Two-Sided Unlimited Risk Demands Real Discipline",
                "Because a short straddle is exposed on both sides at "
                "once, the position-sizing and predefined-exit discipline "
                "from Chapters 5 and 10 apply doubly here - a single sharp "
                "move in *either* direction can produce a large loss, not "
                "only a move away from an established directional bias.",
            ),
            Section(
                "A Defined-Risk Alternative Exists",
                "A trader who wants the same 'bet on low movement' "
                "exposure without unlimited risk on either side can "
                "consider an iron condor instead (Chapter 23), which adds "
                "protective long options on both sides in exchange for "
                "collecting less net premium - the same trade-off bear "
                "call spreads offer relative to naked calls (Chapter 8).",
            ),
        ),
    ),
]
