"""Chapter 35: Futures Option Strategies for Futures Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 35

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Applying Equity Option Strategies to Futures Options",
        topics=("futures spreads", "strategy transfer"),
        keywords=("futures option strategies",),
        related_concepts=("LC-34-01", "LC-07-01"),
        sections=(
            Section(
                "Most of the Mechanics Transfer Directly",
                "Bull and bear spreads (Chapters 7, 8, 22), straddles "
                "(Chapter 20), and the other multi-leg structures in this "
                "curriculum apply to options on futures the same way they "
                "apply to equity options - same strike/expiration "
                "combinatorics, same max-profit/max-loss/breakeven "
                "reasoning. What changes is what happens on exercise "
                "(Chapter 34, Lesson LC-34-02: a futures position, not "
                "shares or cash) and the underlying futures contract's own "
                "characteristics (margin, daily mark-to-market, contract "
                "expiration distinct from the option's own expiration).",
            ),
            Section(
                "What Requires Extra Care",
                "A spread's two legs might reference futures contracts "
                "with *different* delivery months, adding a genuine "
                "futures-spread dimension (the price relationship between "
                "two delivery months of the same underlying commodity or "
                "instrument) on top of the options structure itself - "
                "worth understanding as its own source of risk/reward "
                "separate from the option strategy's usual behavior.",
            ),
        ),
    ),
]
