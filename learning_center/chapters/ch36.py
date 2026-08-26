"""Chapter 36: Basics of Volatility Trading."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 36

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Historical vs. Implied Volatility",
        topics=("historical volatility", "implied volatility"),
        keywords=("historical volatility", "implied volatility", "HV", "IV"),
        related_concepts=("LC-01-03",),
        sections=(
            Section(
                "Two Different Measurements",
                "**Historical volatility** measures how much the "
                "underlying has actually moved in the past, computed "
                "directly from price data. **Implied volatility** is "
                "backed out of an option's current market price - it is "
                "the market's forward-looking estimate of future movement, "
                "not a measurement of movement that has already happened. "
                "The two are related but frequently diverge, sometimes "
                "significantly.",
            ),
            Section(
                "Why the Difference Matters",
                "An option's extrinsic value (Chapter 1, Lesson LC-01-03) "
                "is driven largely by implied volatility, not historical "
                "volatility - an underlying that has been calm historically "
                "can still have expensive options if the market expects "
                "future movement (an upcoming earnings report, for "
                "example), and vice versa.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Volatility as Its Own Tradable View",
        topics=("trading volatility", "long vega", "short vega"),
        keywords=("volatility trading", "vega exposure"),
        related_concepts=("LC-36-01", "LC-20-01"),
        sections=(
            Section(
                "Direction vs. Volatility",
                "Every strategy in this curriculum has both a directional "
                "lean (or lack of one) and a volatility lean, whether or "
                "not that second dimension was made explicit when it was "
                "introduced. A long straddle-like structure (built from "
                "long options) generally benefits from rising implied "
                "volatility independent of direction; a short "
                "straddle-like structure (Chapter 20) generally benefits "
                "from falling or stable implied volatility. Recognizing "
                "both dimensions of a position - not just its directional "
                "bias - is what this chapter and the two after it build "
                "toward.",
            ),
        ),
    ),
]
