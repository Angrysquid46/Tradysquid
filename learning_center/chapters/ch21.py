"""Chapter 21: Synthetic Stock Positions."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 21

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Synthetic Long Stock",
        topics=("synthetic long stock", "put-call parity"),
        keywords=("synthetic long stock", "combo"),
        related_concepts=("LC-01-01", "LC-03-01"),
        sections=(
            Section(
                "Definition",
                "Buying a call and simultaneously selling a put at the "
                "*same* strike and expiration creates a **synthetic long "
                "stock** position: its profit/loss shape tracks the "
                "underlying almost exactly like owning the shares outright, "
                "dollar-for-dollar above and below the strike, without ever "
                "owning the shares.",
            ),
            Section(
                "Why the Two Sides Combine Into Stock-Like Exposure",
                "Above the strike, the long call drives the position's "
                "gains like owning stock would. Below the strike, the "
                "short put's losses grow exactly like owning stock falling "
                "would. There is no range where the position behaves "
                "differently from the stock itself - this equivalence is "
                "known as **put-call parity**, and it is what makes the "
                "combination 'synthetic' stock rather than merely a "
                "similar-shaped bet.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Synthetic Short Stock and Why This Matters",
        topics=("synthetic short stock", "capital efficiency"),
        keywords=("synthetic short stock", "reverse combo"),
        related_concepts=("LC-21-01", "LC-04-01"),
        sections=(
            Section(
                "Synthetic Short Stock",
                "The mirror position - selling a call and buying a put at "
                "the same strike and expiration - creates **synthetic "
                "short stock**, tracking a short-stock position's P&L "
                "dollar-for-dollar without borrowing and shorting shares "
                "directly.",
            ),
            Section(
                "Practical Uses",
                "Synthetic positions can require less capital than the "
                "equivalent real stock position (options margin/premium "
                "outlay versus the full share price), can be used where "
                "shorting shares directly is restricted or inconvenient, "
                "and make explicit exactly what combination of options "
                "reproduces plain directional stock exposure - a reference "
                "point for evaluating whether a more complex multi-leg "
                "position is actually adding something beyond what "
                "synthetic stock alone would provide.",
            ),
        ),
    ),
]
