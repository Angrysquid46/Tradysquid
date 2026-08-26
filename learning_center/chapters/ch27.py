"""Chapter 27: Arbitrage."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 27

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="What Arbitrage Means in Options",
        topics=("arbitrage", "riskless profit"),
        keywords=("arbitrage", "mispricing"),
        related_concepts=("LC-21-01",),
        sections=(
            Section(
                "Definition",
                "**Arbitrage** is capturing a genuinely riskless profit "
                "from a temporary pricing inconsistency between related "
                "instruments - for example if a call, a put, the stock, "
                "and a risk-free rate are priced inconsistently with "
                "put-call parity (Chapter 21), a combination of trades can "
                "lock in a profit regardless of which way the underlying "
                "moves.",
            ),
            Section(
                "Why It Is Rare and Small in Practice",
                "In liquid, closely-watched markets, genuine arbitrage "
                "opportunities are typically small, fleeting, and "
                "captured within moments by automated market participants "
                "specifically built to find them - by the time a retail "
                "trader notices a mispricing, transaction costs, "
                "execution slippage, and bid/ask spreads have usually "
                "already erased the opportunity. Understanding arbitrage "
                "is valuable mainly because it explains *why* options are "
                "priced the way they are (their prices are constrained by "
                "the threat of arbitrage, even when no one is actively "
                "arbitraging them at a given moment), not as a realistic "
                "primary strategy for most traders.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Conversion and Reversal",
        topics=("conversion", "reversal"),
        keywords=("conversion arbitrage", "reversal arbitrage"),
        related_concepts=("LC-21-01", "LC-27-01"),
        sections=(
            Section(
                "The Two Classic Structures",
                "A **conversion** combines long stock, a short call, and a "
                "long put (all same strike/expiration) - equivalent to "
                "synthetic short stock (Chapter 21) added against real "
                "long stock, locking in a fixed result. A **reversal** is "
                "the opposite: short stock, a long call, and a short put, "
                "combining real short stock with synthetic long stock. "
                "Both exist specifically to exploit or close out small "
                "put-call parity mispricings, and both are, by "
                "construction, market-neutral - their result does not "
                "depend on which direction the underlying moves.",
            ),
        ),
    ),
]
