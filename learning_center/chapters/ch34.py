"""Chapter 34: Futures and Futures Options."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 34

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="What a Futures Contract Is",
        topics=("futures contract", "mark to market"),
        keywords=("futures contract", "mark to market"),
        related_concepts=("LC-01-06",),
        sections=(
            Section(
                "Definition",
                "A **futures contract** is an obligation - not a right "
                "like an option - to buy or sell an underlying at a fixed "
                "price on a fixed future date. Both sides are obligated "
                "from the start; there is no premium paid for a right, "
                "only margin posted against the obligation. Futures are "
                "**marked to market** daily - gains and losses are settled "
                "in cash every day, not only at expiration.",
            ),
            Section(
                "How This Differs from Options",
                "An option buyer's risk is capped at the premium paid, "
                "with no obligation to do anything further (Chapter 1). A "
                "futures position has no such cap - both the long and "
                "short side are obligated to the full move of the "
                "contract, marked to market daily, more comparable to "
                "outright long or short stock (Chapter 1, Lesson LC-01-01) "
                "than to a long option.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Options on Futures Contracts",
        topics=("futures options mechanics",),
        keywords=("options on futures mechanics",),
        related_concepts=("LC-34-01", "LC-29-02"),
        sections=(
            Section(
                "How Exercise Works",
                "Exercising a call option on a futures contract does not "
                "deliver the physical commodity or instrument the futures "
                "contract itself references - it creates a **long futures "
                "position** at the option's strike, which is then itself "
                "subject to daily mark-to-market like any other futures "
                "position (Lesson LC-34-01). A put similarly creates a "
                "short futures position on exercise. The option's own risk "
                "before exercise remains capped at the premium paid, "
                "exactly like an equity option (Chapter 1) - only "
                "*after* exercise does futures-style, uncapped, "
                "marked-to-market risk begin.",
            ),
        ),
    ),
]
