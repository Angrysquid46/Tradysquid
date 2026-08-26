"""Chapter 9: Calendar Spreads."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 9

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Calendar Spread",
        topics=("calendar spread", "time spread", "horizontal spread"),
        keywords=("calendar spread", "time spread", "horizontal spread"),
        related_concepts=("LC-01-02", "LC-01-03"),
        sections=(
            Section(
                "Definition",
                "A **calendar spread** (or time spread) sells a near-term "
                "option and buys a longer-term option at the *same strike*, "
                "same type (both calls or both puts). It is opened for a "
                "net debit - the longer-dated option, having more time "
                "value, costs more than the shorter-dated one collects.",
            ),
            Section(
                "Why It Can Profit With the Stock Unchanged",
                "Time decay (theta) accelerates as expiration nears "
                "(Lesson LC-01-03). The near-term short option decays "
                "faster than the far-term long option loses value from the "
                "same passage of time, so if the underlying sits near the "
                "strike, the spread can gain value purely from that "
                "difference in decay rates - a genuinely different profit "
                "source than direction.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk Profile",
        topics=("maximum loss", "pin risk", "ideal outcome"),
        keywords=("max loss", "pin risk"),
        related_concepts=("LC-09-01", "LC-12-01"),
        sections=(
            Section(
                "Maximum Loss and Ideal Outcome",
                "Maximum loss is capped at the net debit paid, realized if "
                "the underlying moves far from the strike in either "
                "direction before the near-term option expires. The ideal "
                "outcome is the underlying sitting close to the strike "
                "right at the near-term expiration - close enough that the "
                "short option expires cheap or worthless while the longer-"
                "dated long option retains substantial value.",
            ),
            Section(
                "After the Near-Term Leg Expires",
                "Once the short option expires, the trader holds a plain "
                "long option (the far-term leg), which can be held, sold, "
                "or turned into a new position - for example selling "
                "another near-term option against it to open a fresh "
                "calendar, repeating the cycle.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Worked Example",
        topics=("worked example",),
        keywords=("calendar spread example",),
        related_concepts=("LC-09-01", "LC-09-02"),
        sections=(
            Section(
                "Setup and Outcome",
                "SPY at $500. Sell the 15-day $500 call for $5.00, buy the "
                "45-day $500 call for $9.00: net debit = $4.00. If SPY is "
                "still at $500 when the near-term call expires: it expires "
                "worthless (loss limited to the $5.00 collected being kept "
                "in full), and the 30-day-remaining long call - still at-"
                "the-money - typically retains meaningfully more than the "
                "$4.00 paid for the whole spread, producing a profit "
                "despite the underlying not moving at all. If SPY instead "
                "moves sharply to $540: both options are now deep ITM and "
                "move together, and most of the spread's original time-"
                "decay edge is gone, typically leaving the position near or "
                "below its cost.",
            ),
        ),
    ),
]
