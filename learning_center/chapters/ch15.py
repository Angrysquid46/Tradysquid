"""Chapter 15: Put Option Basics."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 15

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Put Mechanics Revisited",
        topics=("put option", "right to sell"),
        keywords=("put option", "put mechanics"),
        related_concepts=("LC-01-01", "LC-01-02"),
        sections=(
            Section(
                "Recap",
                "A **put** gives its buyer the right, but not the "
                "obligation, to *sell* the underlying at the strike price "
                "on or before expiration (Lesson LC-01-01). Strike, "
                "expiration, premium, intrinsic/extrinsic value, moneyness, "
                "and exercise/assignment (Chapter 1) all apply to puts "
                "exactly as they do to calls - only the direction of the "
                "right is different.",
            ),
            Section(
                "Moneyness for Puts",
                "A put is in-the-money when the underlying price is "
                "*below* the strike (the opposite of a call), at-the-money "
                "near the strike, and out-of-the-money above the strike. "
                "Intrinsic value = max(strike - underlying price, 0).",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Long Put and Short Put Breakevens",
        topics=("breakeven", "long put", "short put"),
        keywords=("put breakeven", "long put", "short put"),
        related_concepts=("LC-01-05", "LC-15-01"),
        sections=(
            Section(
                "The Formula",
                "For a single put, long or short: breakeven = strike - "
                "premium. A long put buyer needs the underlying to fall "
                "below that breakeven to profit at expiration; a short put "
                "writer profits at any price above it.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. The $495 put trades for $6.00. Breakeven = "
                "$495 - $6.00 = $489.00. A put buyer needs SPY below $489 "
                "to show a profit at expiration; a put seller keeps the "
                "full $6.00 at any price at or above $495, and profits "
                "(though less than the full premium) anywhere down to "
                "$489.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Why Puts Exist: Completing the Toolkit",
        topics=("bearish exposure", "hedging"),
        keywords=("why puts exist", "bearish tool"),
        related_concepts=("LC-01-01", "LC-16-01"),
        sections=(
            Section(
                "Two Distinct Uses",
                "Puts serve two purposes that calls alone cannot: "
                "expressing a **bearish view without shorting stock** "
                "(Chapter 16), and **insuring an existing long stock "
                "position** against decline (Chapter 17). Both are covered "
                "in depth in the next two chapters; this lesson exists to "
                "make clear that puts are not simply 'calls but bearish' - "
                "they enable a materially different set of strategies.",
            ),
        ),
    ),
]
