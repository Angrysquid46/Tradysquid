"""Chapter 28: Mathematical Applications."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 28

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Expected Value in Option Strategy Selection",
        topics=("expected value", "probability-weighted outcomes"),
        keywords=("expected value", "probability weighting"),
        related_concepts=("LC-15-02", "LC-01-05"),
        sections=(
            Section(
                "Beyond a Single Breakeven",
                "Every strategy in this curriculum has a breakeven "
                "(Lesson LC-01-05) - the price at which P&L is exactly "
                "zero at expiration. **Expected value** goes further: it "
                "weights every possible outcome by how likely that outcome "
                "is, not just whether the final result is above or below "
                "breakeven. A strategy can have a breakeven that looks "
                "favorable while still having a negative expected value, "
                "if the sizes and probabilities of the outcomes on each "
                "side are not accounted for together.",
            ),
            Section(
                "Worked Illustration",
                "Consider a simplified bet: 70% chance of winning $50, 30% "
                "chance of losing $150. Expected value = (0.70 x $50) + "
                "(0.30 x -$150) = $35 - $45 = -$10. Despite winning most of "
                "the time, this bet loses money on average - win rate "
                "alone (Chapter 15's education, not this curriculum's own "
                "trading system) never tells the whole story without also "
                "weighting the size of wins against the size and frequency "
                "of losses.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Position Sizing Math",
        topics=("position sizing", "risk of ruin"),
        keywords=("position sizing formula", "risk of ruin"),
        related_concepts=("LC-10-02", "LC-05-05"),
        sections=(
            Section(
                "Why Fixed-Fraction Sizing Matters",
                "Risking a fixed percentage of account equity per trade, "
                "rather than a fixed dollar amount, means a losing streak "
                "shrinks position size automatically (protecting the "
                "account from a full loss even after many consecutive "
                "losses), while a winning streak grows it. Risking a fixed "
                "dollar amount instead allows the *percentage* risked to "
                "silently grow as the account shrinks after losses - "
                "exactly when risk should be shrinking, not growing.",
            ),
        ),
    ),
]
