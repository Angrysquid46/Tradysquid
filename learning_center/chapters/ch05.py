"""Chapter 5: Naked Call Writing."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 5

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics and Margin",
        topics=("naked call", "uncovered call", "margin requirement"),
        keywords=("naked call", "uncovered call", "margin"),
        related_concepts=("LC-01-01", "LC-02-01"),
        sections=(
            Section(
                "Definition",
                "A **naked** (or uncovered) call is a short call written "
                "without owning the underlying shares to deliver if assigned "
                "- the opposite of the covered call in Chapter 2. Because the "
                "writer has no shares standing behind the obligation, the "
                "broker requires a **margin deposit** as collateral, "
                "recalculated continuously as the underlying and the option's "
                "value change. Naked option writing is a more advanced "
                "trading activity, typically requiring a higher account "
                "approval level than covered strategies or long options.",
            ),
            Section(
                "Why Margin, Not Just Cash",
                "If assigned, the writer must buy shares at the current "
                "market price and immediately deliver them at the (lower) "
                "strike price - a real, uncapped cash cost that grows with "
                "the underlying. Margin exists to make sure the writer can "
                "cover that obligation; it is not optional collateral the "
                "trader can choose to skip by holding enough unrelated cash "
                "in the account, and requirements can increase sharply, with "
                "little notice, as the position moves against the writer.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Unlimited Risk",
        topics=("unlimited risk", "maximum loss"),
        keywords=("unlimited risk", "unbounded loss"),
        related_concepts=("LC-01-01", "LC-05-01"),
        sections=(
            Section(
                "Why the Risk Is Unbounded",
                "A stock has no theoretical ceiling on how high it can rise. "
                "A naked call writer who is assigned must buy shares at "
                "whatever the market price is and deliver them at the fixed "
                "strike - the higher the stock has gone, the larger that gap, "
                "with no maximum. This is the mirror image of the defined-"
                "risk profile of the long call in Chapter 3: for every "
                "options position, someone's defined risk is someone else's "
                "unbounded risk, and naked call writing sits on the unbounded "
                "side.",
            ),
            Section(
                "This Is Not a Theoretical Risk",
                "Large, fast, unexpected rallies genuinely happen - takeover "
                "announcements, short squeezes, and broad market spikes have "
                "all produced real, account-threatening losses for naked "
                "call writers historically. 'Unlimited risk' in this chapter "
                "means exactly what it says, not a textbook exaggeration - it "
                "is the reason this strategy is gated behind higher account "
                "approval levels.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Why and When It Is Used",
        topics=("premium collection", "bearish/neutral outlook"),
        keywords=("premium selling", "bearish", "neutral"),
        related_concepts=("LC-02-02", "LC-05-02"),
        sections=(
            Section(
                "The Appeal",
                "Naked call writing collects premium without needing to "
                "already own (or want to own) the underlying shares, and "
                "profits if the stock stays flat, falls, or rises only a "
                "modest amount that stays below the strike. It expresses a "
                "bearish-to-neutral view with defined, known maximum profit "
                "(the premium collected) in exchange for the unbounded risk "
                "in Lesson LC-05-02.",
            ),
            Section(
                "Why Traders Choose It Over a Covered Call",
                "A covered call requires owning 100 shares per contract, "
                "tying up significant capital and taking on the stock's full "
                "downside risk. Naked call writing avoids owning the stock "
                "entirely, using margin instead of full share ownership - at "
                "the cost of the unlimited upside risk a covered writer does "
                "not have, since a covered writer's 'loss' from a rally is "
                "only the opportunity cost of upside already given up, not a "
                "new out-of-pocket loss.",
            ),
        ),
    ),
    Lesson(
        lesson_number=4,
        title="Worked P&L Example",
        topics=("maximum profit", "breakeven", "unlimited loss"),
        keywords=("P&L example", "worked example"),
        related_concepts=("LC-01-05", "LC-05-02"),
        sections=(
            Section(
                "Setup",
                "A trader sells the SPY $520 call naked for $3.00 ($300 per "
                "contract) with SPY at $500.00. Maximum profit = $3.00 per "
                "share, realized at any price at or below $520 at expiration "
                "- the premium collected is the entire profit potential, no "
                "matter how far SPY falls. Breakeven = strike + premium = "
                "$523.00.",
            ),
            Section(
                "Outcomes",
                "If SPY finishes at $515: the call expires worthless, full "
                "$300 profit kept. If SPY finishes at $523: intrinsic value "
                "equals the premium collected, P&L is exactly zero. If SPY "
                "finishes at $560: intrinsic value is $40.00 per share, and "
                "the position loses $40.00 - $3.00 = $37.00 per share "
                "($3,700 per contract) - more than twelve times the premium "
                "collected, from a single unexpected rally. There is no "
                "price at which the loss stops growing.",
            ),
        ),
    ),
    Lesson(
        lesson_number=5,
        title="Risk Management for Naked Calls",
        topics=("stop loss", "position sizing", "buying to close"),
        keywords=("risk management", "stop loss", "defined-risk alternative"),
        related_concepts=("LC-05-02", "LC-10-01"),
        sections=(
            Section(
                "A Predefined Exit Is Not Optional",
                "Because risk is unbounded, entering a naked call without a "
                "predetermined point at which the position will be closed - "
                "whether by a price level in the underlying, a loss "
                "threshold in the option, or both - is materially riskier "
                "than doing the same for a defined-risk strategy, where the "
                "worst case is already known. 'I'll close it if it gets bad' "
                "decided only after the position is already deep against the "
                "trader is a common, costly failure mode.",
            ),
            Section(
                "Position Sizing Against Real Tail Risk",
                "Because a single naked call can, in principle, produce a "
                "loss many multiples of the premium collected, position size "
                "has to be set against that realistic tail outcome, not "
                "against the much smaller premium collected or the much more "
                "common moderate-move outcome. See Chapter 10 for general "
                "position-sizing discipline, and note that it applies with "
                "particular force here.",
            ),
            Section(
                "A Defined-Risk Alternative Exists",
                "A trader who wants the same bearish-to-neutral premium-"
                "selling exposure without unbounded risk can consider a bear "
                "call spread instead (Chapter 8), which caps maximum loss by "
                "buying a further OTM call against the short one, in "
                "exchange for collecting less net premium. This trade-off - "
                "less income for a defined maximum loss - is worth knowing "
                "exists before committing to the naked version.",
            ),
        ),
    ),
]
