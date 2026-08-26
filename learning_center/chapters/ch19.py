"""Chapter 19: Sale of a Put."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 19

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of Selling a Put",
        topics=("short put", "cash-secured put", "naked put"),
        keywords=("short put", "cash-secured put", "naked put"),
        related_concepts=("LC-01-01", "LC-05-01"),
        sections=(
            Section(
                "Definition",
                "Selling (writing) a put obligates the writer to *buy* the "
                "underlying at the strike if assigned. A **cash-secured "
                "put** holds enough cash to cover that purchase in full; a "
                "**naked put** does not, and instead posts margin, "
                "similarly to the naked call in Chapter 5.",
            ),
            Section(
                "The Bullish-to-Neutral View",
                "A short put profits if the underlying stays flat, rises, "
                "or falls only modestly and stays above the strike - the "
                "put-side mirror of the covered call's income objective "
                "(Chapter 2), and the bullish-to-neutral counterpart to the "
                "naked call's bearish-to-neutral view (Chapter 5).",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Cash-Secured Puts as a Stock-Acquisition Tool",
        topics=("acquiring stock", "effective purchase price"),
        keywords=("cash-secured put strategy", "buying stock at a discount"),
        related_concepts=("LC-19-01", "LC-02-02"),
        sections=(
            Section(
                "The Idea",
                "A trader willing to buy a stock at a specific lower price "
                "can sell a cash-secured put at that strike instead of "
                "placing a limit order: if assigned, the effective purchase "
                "price is the strike minus the premium collected - better "
                "than a plain limit order at that strike. If never "
                "assigned, the trader keeps the premium instead of the "
                "stock.",
            ),
            Section(
                "Worked Example",
                "A trader is willing to buy SPY at $490 (currently $500) "
                "and sells the $490 put for $4.00. If SPY falls to $485 by "
                "expiration: assigned, buys 100 shares at $490, effective "
                "cost basis = $490 - $4.00 = $486.00 - better than the "
                "$485 market price would have suggested paying via a plain "
                "limit order placed at $490. If SPY stays above $490: the "
                "put expires worthless, the $400 premium is kept, and no "
                "stock is acquired.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Risk: Cash-Secured vs. Naked",
        topics=("margin", "risk comparison"),
        keywords=("cash-secured vs naked put", "put margin"),
        related_concepts=("LC-19-01", "LC-05-01"),
        sections=(
            Section(
                "Maximum Loss",
                "For both versions, maximum loss = strike - premium "
                "collected, realized if the underlying goes to zero - large "
                "but not unlimited, since a stock price cannot fall below "
                "zero (unlike the naked call's genuinely unbounded risk in "
                "Chapter 5). A cash-secured put's cash is already set aside "
                "for that worst case; a naked put instead relies on margin, "
                "which can be recalled or increased as the position moves "
                "against the writer, the same operational risk naked "
                "calls carry.",
            ),
        ),
    ),
]
