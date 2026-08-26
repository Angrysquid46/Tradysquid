"""Chapter 16: Put Option Buying."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 16

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Why Buy Puts: Bearish Exposure Without Shorting",
        topics=("bearish speculation", "defined risk", "alternative to shorting"),
        keywords=("long put", "bearish", "short stock alternative"),
        related_concepts=("LC-15-01", "LC-04-01"),
        sections=(
            Section(
                "The Core Appeal",
                "Buying a put is a bearish, defined-risk way to profit from "
                "a decline - the mirror image of buying a call (Chapter 3). "
                "The maximum loss is the premium paid; the maximum "
                "theoretical gain approaches (strike - premium) as the "
                "underlying approaches zero, since a stock cannot fall "
                "below zero the way it can rise without limit.",
            ),
            Section(
                "Compared to Shorting Stock",
                "Shorting stock outright carries unlimited risk (Chapter "
                "4, Lesson LC-04-01) and requires margin that can be called "
                "away with little notice. A long put expresses the same "
                "bearish view with risk capped at the premium paid and no "
                "margin call risk - at the cost of the premium itself, and "
                "a limited window (expiration) to be right.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Choosing Strike and Expiration",
        topics=("strike selection", "expiration selection"),
        keywords=("put strike selection", "put expiration selection"),
        related_concepts=("LC-03-02", "LC-03-03"),
        sections=(
            Section(
                "Same Trade-Offs as Call Buying, Mirrored",
                "Strike and expiration selection for long puts follow the "
                "same logic as long calls (Chapter 3, Lessons LC-03-02 and "
                "LC-03-03), mirrored for direction: deeper ITM puts behave "
                "more like a short-stock substitute with less time-decay "
                "sensitivity; further OTM puts offer more leverage but need "
                "a real move to profit. More time costs more but gives the "
                "decline more room to happen; less time is cheaper but "
                "requires the move sooner.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Worked P&L Example",
        topics=("maximum profit", "maximum loss", "worked example"),
        keywords=("put P&L", "worked example"),
        related_concepts=("LC-15-02", "LC-16-01"),
        sections=(
            Section(
                "Setup and Outcomes",
                "SPY at $500.00. Buy the $495 put, 30 days out, for $6.00. "
                "Breakeven = $489.00. If SPY finishes at $470: intrinsic "
                "value = $25.00, profit = $25.00 - $6.00 = $19.00 per share "
                "- over 300% return on premium risked. If SPY finishes at "
                "$495: the put expires worthless, full $6.00 premium lost, "
                "even though SPY fell $5.00 from where the put was bought - "
                "the decline never reached the strike. Maximum loss on this "
                "trade is always exactly $6.00 per share, at any price at "
                "or above $495.",
            ),
        ),
    ),
]
