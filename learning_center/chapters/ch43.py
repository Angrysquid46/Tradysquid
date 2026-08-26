"""Chapter 43: The Best Strategy?"""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 43

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="There Is No Single Best Strategy",
        topics=("strategy selection", "matching strategy to view"),
        keywords=("best strategy", "strategy selection framework"),
        related_concepts=("LC-01-01", "LC-28-01"),
        sections=(
            Section(
                "Why the Question Itself Is the Wrong Frame",
                "Every strategy in this curriculum, from the single long "
                "call in Chapter 3 to the iron condor in Chapter 23, is a "
                "tool matched to a specific view: direction, magnitude, "
                "timing, and volatility expectation, together (Chapters "
                "36-39). A strategy that is excellent for one combination "
                "of those four is often poor for another - there is no "
                "strategy that is unconditionally best, only strategies "
                "that are well- or poorly-matched to the actual thesis at "
                "hand.",
            ),
            Section(
                "A Practical Selection Framework",
                "Before selecting a strategy: state the directional view "
                "(bullish, bearish, neutral, or no view), the expected "
                "magnitude and timing of the move, and the volatility "
                "expectation (rising, falling, stable) - only then choose "
                "the strategy whose risk/reward and Greek exposure "
                "(Chapters 4/40) actually matches all three, rather than "
                "picking a familiar strategy first and rationalizing a "
                "thesis around it afterward.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="What This Curriculum Was Actually For",
        topics=("closing summary",),
        keywords=("curriculum summary", "closing lesson"),
        related_concepts=("LC-10-01", "LC-14-01", "LC-28-01"),
        sections=(
            Section(
                "The Real Takeaway",
                "Every strategy from Chapter 2 onward is built from the "
                "definitions in Chapter 1 and combinations of long/short "
                "calls/puts (Lesson LC-01-01's four basic positions) - "
                "understanding those fundamentals well enough to see how "
                "each later chapter's structure is assembled from them "
                "matters far more than memorizing any single chapter's "
                "name or payoff diagram. Expected value (Chapter 28), "
                "position sizing, and process discipline (Chapter 10's "
                "risk management, referenced throughout) determine "
                "long-run outcomes far more than which specific strategy "
                "name was used on any individual trade.",
            ),
            Section(
                "Where to Go From Here",
                "Use `/learn topic:` to search back into any concept from "
                "this curriculum by name, `/ask` for quick curated "
                "questions, and #examples-and-reviews for worked, real "
                "paper-trade walkthroughs. Every strategy here remains "
                "educational, paper-trading material - individual "
                "verification of every quote, contract, and risk before "
                "acting stays the trader's responsibility, always.",
            ),
        ),
    ),
]
