"""Chapter 37: How Volatility Affects Popular Strategies."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 37

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Volatility's Effect, Strategy by Strategy",
        topics=("vega exposure by strategy",),
        keywords=("volatility effect on strategies", "vega by strategy"),
        related_concepts=("LC-36-02", "LC-02-01", "LC-05-01"),
        sections=(
            Section(
                "Long Single Options",
                "A long call or long put (Chapters 3, 16) generally "
                "benefits from rising implied volatility (more extrinsic "
                "value, Lesson LC-01-03) and is hurt by falling implied "
                "volatility - a real, separate source of gain or loss on "
                "top of whatever the underlying itself does.",
            ),
            Section(
                "Covered Calls and Cash-Secured Puts",
                "A covered call (Chapter 2) or cash-secured put (Chapter "
                "19) is short one option - it benefits from falling "
                "implied volatility (the short option loses value faster) "
                "and is hurt by rising implied volatility, the opposite "
                "exposure of the long positions above.",
            ),
            Section(
                "Spreads",
                "Vertical spreads (Chapters 7, 8, 22) are largely, though "
                "not perfectly, hedged against implied-volatility changes, "
                "since both legs move somewhat together - a materially "
                "smaller volatility exposure than a single long or short "
                "option, but rarely exactly zero, especially if the two "
                "strikes are far apart or the position is very "
                "unbalanced (Chapters 6, 11).",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Volatility Crush",
        topics=("volatility crush", "earnings IV"),
        keywords=("volatility crush", "IV crush"),
        related_concepts=("LC-13-01", "LC-37-01"),
        sections=(
            Section(
                "What It Is",
                "Implied volatility frequently rises into a known event "
                "(such as earnings) and then drops sharply immediately "
                "after, once the uncertainty resolves - a **volatility "
                "crush**. A long option bought right before the event can "
                "lose significant value from the IV drop alone, even if "
                "the underlying moves in the anticipated direction, "
                "because the extrinsic-value collapse can outweigh the "
                "intrinsic-value gain.",
            ),
        ),
    ),
]
