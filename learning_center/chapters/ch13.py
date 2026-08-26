"""Chapter 13: Reverse Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 13

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Backspread",
        topics=("backspread", "reverse ratio spread"),
        keywords=("backspread", "reverse spread"),
        related_concepts=("LC-11-01", "LC-01-01"),
        sections=(
            Section(
                "Definition",
                "A **backspread** (reverse ratio spread) sells fewer "
                "options at a lower strike than it buys at a higher strike "
                "- the mirror image of the ratio spread in Chapter 11. For "
                "example: sell 1 call at a lower strike, buy 2 calls at a "
                "higher strike, same expiration. Because more options are "
                "bought than sold, the position typically has **defined "
                "risk in the direction the extra long options point**, and "
                "can have unlimited profit potential rather than unlimited "
                "risk.",
            ),
            Section(
                "Where the Long Exposure Comes From",
                "Above the higher strike, the extra long call (the one not "
                "offset by a short call) participates fully and without "
                "limit in further upside - the reverse of Chapter 11's "
                "extra *short* call creating unlimited *risk* on the "
                "upside. A backspread deliberately trades away some "
                "near-term credit (or pays a small debit) for that "
                "unlimited-upside characteristic.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk Profile and When It Is Used",
        topics=("risk profile", "large move thesis"),
        keywords=("backspread risk", "volatility expansion"),
        related_concepts=("LC-13-01", "LC-36-01"),
        sections=(
            Section(
                "The Shape of the Bet",
                "A call backspread tends to lose the most (though still a "
                "defined amount) if the underlying finishes right around "
                "the higher strike, and gains if the underlying either "
                "stays well below the lower strike (small gain or "
                "breakeven from the short call's credit) or moves well "
                "above the higher strike (unlimited gain from the extra "
                "long call). It suits a trader who expects a large move but "
                "is uncertain of the exact magnitude, more than a trader "
                "expecting a moderate, contained move.",
            ),
            Section(
                "Comparison to a Plain Long Call",
                "Compared to simply buying calls (Chapter 3), a backspread "
                "can be financed more cheaply (sometimes for a credit) by "
                "selling the near strike, at the cost of a range around "
                "the strikes where it performs worse than an outright long "
                "call would have.",
            ),
        ),
    ),
]
