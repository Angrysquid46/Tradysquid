"""Chapter 6: Ratio Call Writing."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 6

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Ratio Call Write",
        topics=("ratio write", "variable ratio write"),
        keywords=("ratio call write", "2:1 write", "partial cover"),
        related_concepts=("LC-02-01", "LC-05-01"),
        sections=(
            Section(
                "Definition",
                "A **ratio call write** combines owning shares with selling "
                "*more* calls than the shares fully cover - for example "
                "owning 100 shares and selling 2 calls (a 2:1 ratio) instead "
                "of the 1:1 covered call in Chapter 2. The first call is "
                "covered by the shares; every call beyond that is naked, "
                "carrying the unlimited-risk profile from Chapter 5.",
            ),
            Section(
                "Why Combine Them",
                "The extra naked call collects additional premium beyond "
                "what a plain covered call would, increasing income and "
                "lowering the effective breakeven - in exchange for "
                "introducing real unlimited risk above the upper breakeven "
                "that a fully covered 1:1 write does not have.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Risk Profile",
        topics=("upper breakeven", "unlimited risk", "naked portion"),
        keywords=("upper breakeven", "naked portion"),
        related_concepts=("LC-05-02", "LC-06-01"),
        sections=(
            Section(
                "Two Breakevens",
                "Below the strike, the position behaves like a covered call "
                "- premium collected is profit, shares are held. As the "
                "stock rises past the strike, gains on the covered portion "
                "are offset by losses on the naked portion; past a second, "
                "**upper breakeven**, the naked call(s) dominate and losses "
                "become unbounded, exactly like naked call writing.",
            ),
            Section(
                "This Is Not a Pure Income Strategy",
                "A ratio write is often marketed as 'extra income on stock "
                "already owned,' which understates that it is a naked-call "
                "position layered on top of a covered one. Position sizing "
                "and a predefined exit for the upper breakeven scenario "
                "(Chapter 5, Lesson LC-05-05) apply here with the same "
                "force.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Choosing the Ratio and Strike",
        topics=("ratio selection", "strike selection"),
        keywords=("2:1", "3:1", "ratio selection"),
        related_concepts=("LC-06-01", "LC-06-02"),
        sections=(
            Section(
                "Higher Ratios Trade Income for Risk",
                "A 2:1 write has one naked call; a 3:1 write has two. Each "
                "additional naked call increases premium collected and "
                "narrows the range where the position is most profitable, "
                "while widening the eventual unlimited-risk exposure above "
                "the upper breakeven. The ratio is a direct risk dial, not "
                "a free income multiplier.",
            ),
            Section(
                "Worked Example",
                "100 shares owned at $500.00; 2 calls sold at the $510 "
                "strike for $5.00 each ($10.00 total premium, one covered, "
                "one naked). If SPY finishes at $510: both expire worthless, "
                "full $1,000 premium kept, shares still held. If SPY "
                "finishes at $530: the covered call costs $20.00 in capped "
                "upside as usual, but the naked call also owes $20.00 "
                "against no shares - net loss on the naked portion "
                "widening the further SPY rises, only partly offset by the "
                "premium already collected.",
            ),
        ),
    ),
]
