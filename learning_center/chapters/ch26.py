"""Chapter 26: Buying Options and Treasury Bills."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 26

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="The Options-Plus-T-Bills Strategy",
        topics=("stock replacement", "capital preservation"),
        keywords=("options and treasury bills", "capital-efficient stock replacement"),
        related_concepts=("LC-25-02", "LC-03-01"),
        sections=(
            Section(
                "The Idea",
                "Instead of buying shares outright, a trader allocates "
                "most of that capital to safe, interest-bearing short-term "
                "instruments (historically Treasury bills) and uses a "
                "smaller portion to buy calls (Chapter 3) providing "
                "similar upside participation. This caps the total dollar "
                "risk at the (small) premium paid for the calls plus "
                "whatever yield is foregone, while the bulk of the capital "
                "remains safe and earning a return.",
            ),
            Section(
                "Trade-Offs vs. Owning Stock Outright",
                "This approach trades away dividends and the exact upside "
                "participation shares would give (calls have a strike, "
                "expiration, and premium cost that outright ownership does "
                "not) in exchange for a hard, known cap on total capital at "
                "risk from the equity component - only the premium paid "
                "for the calls can be lost to that specific bet, with the "
                "T-bill portion insulated entirely.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Worked Example",
        topics=("worked example",),
        keywords=("options T-bill example",),
        related_concepts=("LC-26-01",),
        sections=(
            Section(
                "Setup and Outcome",
                "A trader has $50,000. Instead of buying ~100 shares of "
                "SPY at $500, they put $47,000 into short-term T-bills "
                "(earning a modest, safe yield) and spend $3,000 on SPY "
                "calls. If SPY falls sharply, the calls may expire "
                "worthless - a maximum loss of $3,000 (plus any small "
                "T-bill yield foregone) versus a loss on the full $50,000 "
                "an outright stock position would have carried. If SPY "
                "rises substantially, the calls participate in a large "
                "share of that gain, though not identically to owning the "
                "full $50,000 of stock.",
            ),
        ),
    ),
]
