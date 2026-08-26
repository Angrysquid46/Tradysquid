"""Chapter 8: Bear Spreads Using Call Options."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 8

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Bear Call Spread",
        topics=("bear call spread", "credit spread"),
        keywords=("bear call spread", "credit spread"),
        related_concepts=("LC-05-01", "LC-07-01"),
        sections=(
            Section(
                "Definition",
                "A **bear call spread** sells a call at one strike and buys "
                "a call at a higher strike, same expiration. It is a "
                "**credit spread** - the short call (closer to the money) "
                "collects more than the long call (further away) costs, so "
                "the position is opened for a net credit, received up "
                "front.",
            ),
            Section(
                "The Defined-Risk Alternative to Naked Calls",
                "This is the strategy referenced at the end of Chapter 5: "
                "the long call caps the otherwise-unlimited risk of the "
                "short call, at the cost of giving back some of the premium "
                "that a fully naked call would have collected. It expresses "
                "the same bearish-to-neutral view with a known, defined "
                "maximum loss.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Max Profit, Max Loss, and Breakeven",
        topics=("maximum profit", "maximum loss", "breakeven"),
        keywords=("max profit", "max loss", "breakeven"),
        related_concepts=("LC-08-01", "LC-01-05"),
        sections=(
            Section(
                "The Formulas",
                "Maximum profit = net credit received, realized at or "
                "below the short strike. Maximum loss = (long strike - "
                "short strike) - net credit, realized at or above the long "
                "strike. Breakeven = short strike + net credit.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. Sell the $510 call for $4.00, buy the $520 "
                "call for $1.50: net credit = $2.50. Max profit = $2.50 "
                "(SPY at or below $510). Max loss = ($520 - $510) - $2.50 = "
                "$7.50 (SPY at or above $520). Breakeven = $512.50. Compare "
                "to the naked $510 call from Chapter 5's example: this "
                "spread collects less credit ($2.50 vs $3.00) but caps the "
                "loss at $7.50 instead of leaving it unbounded.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Bear Call Spread vs. Naked Call",
        topics=("comparison", "defined risk"),
        keywords=("bear spread vs naked call", "risk comparison"),
        related_concepts=("LC-05-02", "LC-08-01"),
        sections=(
            Section(
                "The Direct Trade-Off",
                "Every dollar of long-call protection reduces net credit "
                "collected but converts unbounded risk into a fixed, known "
                "number. Traders without naked-option account approval, or "
                "who simply want the risk explicitly bounded regardless of "
                "approval level, use the credit spread version by default "
                "rather than as a downgrade.",
            ),
            Section(
                "Margin Impact",
                "Because maximum loss is fixed and known in advance, "
                "brokers require margin equal to (or close to) that maximum "
                "loss rather than the much larger, continuously "
                "recalculated margin a naked call requires - a defined-risk "
                "spread is materially more capital-efficient for the same "
                "directional view, not only safer.",
            ),
        ),
    ),
]
