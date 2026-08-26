"""Chapter 12: Combining Calendar and Ratio Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 12

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="The Calendar Ratio Spread",
        topics=("calendar ratio spread", "ratio calendar"),
        keywords=("calendar ratio spread", "unbalanced calendar"),
        related_concepts=("LC-09-01", "LC-11-01"),
        sections=(
            Section(
                "Definition",
                "A **calendar ratio spread** sells more near-term options "
                "than the number of longer-term options bought at the same "
                "strike - for example selling 2 near-term calls against 1 "
                "far-term call, combining Chapter 9's time-decay mechanism "
                "with Chapter 11's unequal-quantity structure.",
            ),
            Section(
                "Why Combine Them",
                "The extra near-term short option collects more premium "
                "up front (often turning the position into a net credit "
                "instead of Chapter 9's net debit), increasing income if "
                "the underlying stays near the strike through the near-term "
                "expiration. It also reintroduces uncovered short exposure "
                "for the period after the near-term legs expire and before "
                "the long-term leg is closed, since more contracts were "
                "sold than are held long.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk Considerations",
        topics=("added risk", "position complexity"),
        keywords=("calendar ratio risk", "unequal quantities"),
        related_concepts=("LC-12-01", "LC-06-02"),
        sections=(
            Section(
                "Two Risk Sources Layered Together",
                "This structure inherits calendar spreads' sensitivity to "
                "a large, fast move away from the strike (Lesson LC-09-02) "
                "*and* ratio spreads' uncovered-quantity risk (Lesson "
                "LC-11-02) at the same time. It is a more complex position "
                "than either building block alone, and should only be used "
                "once both underlying mechanisms are separately "
                "understood - not assembled purely because it can be "
                "opened for a larger credit than a plain calendar spread.",
            ),
        ),
    ),
]
