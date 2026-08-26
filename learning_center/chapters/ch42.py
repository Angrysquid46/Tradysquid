"""Chapter 42: Taxes."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 42

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="General Tax Concepts for Options",
        topics=("short-term vs long-term", "cost basis"),
        keywords=("options taxes", "cost basis", "holding period"),
        related_concepts=("LC-01-07",),
        sections=(
            Section(
                "Educational Only",
                "This lesson describes general concepts, not tax advice. "
                "Options tax treatment can vary by underlying, holding "
                "period, exercise, assignment, and specific contract "
                "status, and rules can change. Always confirm current "
                "treatment with a qualified tax professional and current "
                "IRS guidance for a specific situation.",
            ),
            Section(
                "Short-Term vs. Long-Term and Cost Basis",
                "Most listed equity option gains held over a year are "
                "eligible for long-term treatment, and under a year for "
                "short-term treatment, similarly to stock - but exercise "
                "and assignment change the calculation: a call's premium "
                "paid typically adds to the cost basis of shares acquired "
                "on exercise (Chapter 1, Lesson LC-01-07) rather than "
                "being a separate, immediately deductible loss.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Wash Sales and Straddle Rules",
        topics=("wash sale rule", "straddle tax rule"),
        keywords=("wash sale", "straddle rule"),
        related_concepts=("LC-42-01", "LC-20-01"),
        sections=(
            Section(
                "Why Multi-Leg and Repeated Trades Need Extra Care",
                "Rules exist specifically addressing repeated similar "
                "trades (wash sales) and certain offsetting multi-leg "
                "positions (straddle-related rules, distinct from this "
                "curriculum's 'straddle' strategy name in Chapter 20 but "
                "historically named after it) that can defer or disallow "
                "losses in ways that are easy to miss when simply adding "
                "up each individual trade's P&L. This is exactly the kind "
                "of situation where professional tax guidance matters "
                "most - the interactions are genuinely non-obvious even to "
                "experienced traders.",
            ),
        ),
    ),
]
