"""Chapter 7: Bull Spreads Using Call Options."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 7

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Bull Call Spread",
        topics=("bull call spread", "vertical spread", "debit spread"),
        keywords=("bull call spread", "vertical spread", "debit spread"),
        related_concepts=("LC-01-01", "LC-03-01"),
        sections=(
            Section(
                "Definition",
                "A **bull call spread** buys a call at one strike and sells "
                "a call at a higher strike, same expiration, same "
                "underlying. It is a **debit spread** - the long call "
                "(closer to the money) costs more than the short call "
                "(further away) collects, so the position costs money to "
                "open, paid up front.",
            ),
            Section(
                "Why Sell the Second Call",
                "Selling the higher-strike call reduces the net cost versus "
                "buying the call outright (Chapter 3), in exchange for "
                "capping the maximum profit at the short strike. It "
                "converts unlimited upside into a lower-cost, defined-"
                "range bullish bet.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Max Profit, Max Loss, and Breakeven",
        topics=("maximum profit", "maximum loss", "breakeven"),
        keywords=("max profit", "max loss", "breakeven"),
        related_concepts=("LC-07-01", "LC-01-05"),
        sections=(
            Section(
                "The Formulas",
                "Maximum loss = net debit paid, realized at or below the "
                "long strike. Maximum profit = (short strike - long strike) "
                "- net debit, realized at or above the short strike. "
                "Breakeven = long strike + net debit. Between the strikes, "
                "profit grows linearly with the underlying.",
            ),
            Section(
                "Worked Example",
                "SPY at $500. Buy the $500 call for $8.00, sell the $510 "
                "call for $4.00: net debit = $4.00. Max loss = $4.00 (SPY at "
                "or below $500). Max profit = ($510 - $500) - $4.00 = $6.00 "
                "(SPY at or above $510). Breakeven = $504.00. Compare to the "
                "outright $500 call from Chapter 3's example: the spread "
                "costs less ($4.00 vs $8.00) but caps profit at $6.00 "
                "instead of running unlimited.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Bull Spread vs. Outright Call",
        topics=("comparison", "capital efficiency"),
        keywords=("bull spread vs call", "cost comparison"),
        related_concepts=("LC-03-01", "LC-07-02"),
        sections=(
            Section(
                "When a Spread Makes Sense",
                "A bull call spread suits a trader whose thesis has a "
                "realistic target range, not an open-ended one - if the "
                "expectation is 'up to about $510,' capping profit there in "
                "exchange for a much lower cost is a direct, deliberate "
                "trade-off, not a compromise. If the thesis is genuinely "
                "open-ended, the outright call (Chapter 3) does not sacrifice "
                "upside for cost.",
            ),
            Section(
                "Common Mistake",
                "Choosing a spread purely because it is 'cheaper' without "
                "asking whether the capped profit level still satisfies the "
                "actual thesis is a common error - cost and payoff shape are "
                "two separate decisions that happen to move together in a "
                "spread.",
            ),
        ),
    ),
]
