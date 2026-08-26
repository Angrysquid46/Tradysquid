"""Chapter 22: Basic Put Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 22

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Bear Put Spread",
        topics=("bear put spread", "debit put spread"),
        keywords=("bear put spread", "debit spread"),
        related_concepts=("LC-16-01", "LC-07-01"),
        sections=(
            Section(
                "Mechanics",
                "A **bear put spread** buys a put at one strike and sells "
                "a put at a lower strike, same expiration - the put-side "
                "mirror of the bull call spread (Chapter 7). It is a debit "
                "spread: the higher-strike long put costs more than the "
                "lower-strike short put collects.",
            ),
            Section(
                "Max Profit, Max Loss, Breakeven",
                "Maximum loss = net debit paid, at or above the higher "
                "strike. Maximum profit = (higher strike - lower strike) - "
                "net debit, at or below the lower strike. Breakeven = "
                "higher strike - net debit. It expresses a bearish view "
                "with a defined range and lower cost than an outright long "
                "put (Chapter 16), capping profit at the lower strike in "
                "exchange.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Bull Put Spread",
        topics=("bull put spread", "credit put spread"),
        keywords=("bull put spread", "credit spread"),
        related_concepts=("LC-19-01", "LC-08-01"),
        sections=(
            Section(
                "Mechanics",
                "A **bull put spread** sells a put at one strike and buys "
                "a put at a lower strike, same expiration - the put-side "
                "mirror of the bear call spread (Chapter 8). It is a "
                "credit spread: the higher-strike short put collects more "
                "than the lower-strike long put costs.",
            ),
            Section(
                "Max Profit, Max Loss, Breakeven",
                "Maximum profit = net credit received, at or above the "
                "higher strike. Maximum loss = (higher strike - lower "
                "strike) - net credit, at or below the lower strike. "
                "Breakeven = higher strike - net credit. It is the "
                "defined-risk alternative to a naked/cash-secured short put "
                "(Chapter 19), the same trade-off bear call spreads offer "
                "relative to naked calls.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Choosing Between the Four Vertical Spreads",
        topics=("vertical spread selection", "debit vs credit"),
        keywords=("choosing a vertical spread",),
        related_concepts=("LC-07-01", "LC-08-01", "LC-22-01", "LC-22-02"),
        sections=(
            Section(
                "The Complete Set",
                "Between Chapters 7, 8, and 22, there are four vertical "
                "spreads: bull call spread and bull put spread both express "
                "a bullish view (one for a debit, one for a credit); bear "
                "call spread and bear put spread both express a bearish "
                "view (one for a credit, one for a debit). A debit spread "
                "and a credit spread with the same two strikes and the same "
                "expiration have mathematically related, often nearly "
                "equivalent, risk/reward profiles once financing and "
                "assignment mechanics are accounted for - the choice "
                "between them often comes down to margin treatment, "
                "assignment risk on the short leg, and personal preference "
                "for paying versus collecting premium up front, not a "
                "fundamentally different market view.",
            ),
        ),
    ),
]
