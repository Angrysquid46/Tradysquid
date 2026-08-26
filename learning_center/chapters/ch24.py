"""Chapter 24: Ratio Spreads Using Puts."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 24

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Put Ratio Spread and Put Backspread",
        topics=("put ratio spread", "put backspread"),
        keywords=("put ratio spread", "put backspread"),
        related_concepts=("LC-11-01", "LC-13-01"),
        sections=(
            Section(
                "Put Ratio Spread",
                "Mirroring Chapter 11's call ratio spread for puts: buy a "
                "put at one strike, sell a larger number of puts at a "
                "lower strike, same expiration. Uncovered short puts below "
                "the lower strike create large (though not unlimited, "
                "since the underlying floors at zero - Chapter 19, Lesson "
                "LC-19-03) risk on the downside, the mirror of the call "
                "ratio spread's uncapped upside risk.",
            ),
            Section(
                "Put Backspread",
                "Mirroring Chapter 13's call backspread for puts: sell "
                "fewer puts at a higher strike, buy more puts at a lower "
                "strike. This gives large gains if the underlying falls "
                "sharply (via the extra long puts), with defined risk if "
                "it does not - a bearish, large-move thesis expressed with "
                "bounded downside cost, the same structural logic as "
                "Chapter 13 mirrored for direction.",
            ),
        ),
    ),
]
