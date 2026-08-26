"""Chapter 2: Covered Call Writing."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 2

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Mechanics of a Covered Call",
        topics=("covered call", "buy-write"),
        keywords=("covered call", "buy-write", "covered write"),
        related_concepts=("LC-01-01", "LC-01-06", "LC-05-01"),
        sections=(
            Section(
                "Definition",
                "A **covered call** combines owning at least 100 shares of the "
                "underlying with selling (writing) one call per 100 shares "
                "owned. It is 'covered' because the shares already owned are "
                "what would be delivered if the call is assigned - the writer "
                "is never exposed to buying shares at an unknown, potentially "
                "much higher price to cover the obligation, unlike the naked "
                "call writing covered in Chapter 5. Opening both legs at once "
                "(buying the stock and selling the call together) is often "
                "called a **buy-write**.",
            ),
            Section(
                "Cash Flow at Entry",
                "The trader receives the option premium immediately when the "
                "call is sold, which effectively lowers the cost basis of the "
                "shares by that amount. If SPY is bought at $500.00 and the "
                "$510 call is sold for $4.00, the effective basis on the "
                "shares becomes $496.00 - the position now profits from that "
                "lower level, not from $500.00.",
            ),
            Section(
                "The Two Outcomes at Expiration",
                "At the call's expiration there are exactly two outcomes: (1) "
                "the underlying is **below the strike** - the call expires "
                "worthless, the writer keeps the full premium and still owns "
                "the shares, free to sell another call against them; or (2) "
                "the underlying is **above the strike** - the call is assigned, "
                "the writer must deliver (sell) 100 shares per contract at the "
                "strike, realizing the strike price plus the premium already "
                "collected, and no longer owns the stock.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Why Write Covered Calls",
        topics=("income generation", "yield enhancement", "reducing cost basis"),
        keywords=("income", "yield", "objective", "motivation"),
        related_concepts=("LC-02-01", "LC-02-04"),
        sections=(
            Section(
                "Primary Objectives",
                "Covered call writers generally pursue one or both of: (1) "
                "**income generation** - collecting premium on shares the "
                "trader already intends to hold, treating the option premium "
                "as an extra yield on top of any dividends; and (2) **modestly "
                "reducing the effective cost basis and downside risk** of an "
                "existing stock position, since the premium collected offsets "
                "some amount of decline before the position shows a loss.",
            ),
            Section(
                "The Trade-Off: Capped Upside",
                "A covered call gives up upside beyond the strike in exchange "
                "for the premium. If the stock rallies well past the strike, "
                "the covered-call writer's total gain is capped at (strike - "
                "cost basis + premium collected) per share - the same as if "
                "they had simply sold the shares at the strike, plus the "
                "premium. Owning the stock outright with no call sold would "
                "have captured the full rally instead. This is the central "
                "trade-off of the strategy, not a flaw to be engineered around "
                "- income and reduced risk are bought with capped upside.",
            ),
            Section(
                "Not a Bullish Strategy",
                "A covered call is a **neutral-to-mildly-bullish** strategy, "
                "not a strongly bullish one. A trader who is genuinely very "
                "bullish on a stock is typically better served owning it "
                "outright (or buying calls - Chapter 3) rather than capping "
                "the upside they expect to actually use.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Choosing Strike and Expiration",
        topics=("strike selection", "expiration selection", "delta"),
        keywords=("strike selection", "OTM call", "expiration"),
        related_concepts=("LC-01-02", "LC-01-04"),
        sections=(
            Section(
                "Strike Selection Trade-Off",
                "Selling a call **closer to the current price** collects more "
                "premium (more extrinsic value, since it's closer to at-the-"
                "money) but caps upside sooner and is more likely to be "
                "assigned. Selling a call **further out-of-the-money** "
                "collects less premium but leaves more room for the stock to "
                "appreciate before the cap applies, and is less likely to be "
                "assigned. There is no single correct strike - it directly "
                "reflects how much upside the trader is willing to trade away "
                "for how much income.",
            ),
            Section(
                "Expiration Selection Trade-Off",
                "Shorter-dated calls decay faster in percentage terms and can "
                "be resold more often (more total premium collected per year, "
                "if repeated), but each individual sale collects less premium "
                "and requires more active management. Longer-dated calls "
                "collect more premium per trade but tie up the position's "
                "upside cap for longer and react more slowly to the passage of "
                "time. Many covered-call writers favor a moderate horizon (for "
                "example a few weeks to a couple of months) as a practical "
                "middle ground, but this is a preference, not a rule.",
            ),
            Section(
                "Worked Example",
                "A trader owns 100 shares of SPY at $500.00 and is willing to "
                "sell if it reaches $515.00, but not below that. Selling the "
                "$515 call directly encodes that willingness: if SPY is called "
                "away, it happens at the exact price the trader already "
                "considered acceptable, plus the premium collected on top.",
            ),
        ),
    ),
    Lesson(
        lesson_number=4,
        title="Risk/Reward Profile and Worked P&L",
        topics=("maximum profit", "maximum loss", "P&L diagram"),
        keywords=("max profit", "max loss", "P&L"),
        related_concepts=("LC-01-05", "LC-02-01"),
        sections=(
            Section(
                "Maximum Profit",
                "Maximum profit = (strike - cost basis) + premium collected, "
                "realized at any underlying price at or above the strike at "
                "expiration. It does not improve further no matter how much "
                "higher the stock goes - this is the cost of the capped "
                "upside described in Lesson LC-02-02.",
            ),
            Section(
                "Maximum Loss",
                "Maximum loss = cost basis - premium collected, realized only "
                "if the stock goes to zero. The premium collected provides a "
                "real but limited cushion against decline - it reduces the "
                "loss at every price below the original cost basis, but it "
                "does not eliminate downside risk, which remains "
                "substantial: a covered call is still a long-stock position "
                "for risk purposes, just a slightly less risky one.",
            ),
            Section(
                "Worked Example",
                "100 shares bought at $500.00; $515 call sold for $4.00. "
                "Effective basis = $496.00. If SPY finishes at $520: shares "
                "are called away at $515, for a gain of $515 - $496 = $19.00 "
                "per share ($1,900 total), even though SPY itself gained $20. "
                "If SPY finishes at $505: the call expires worthless, shares "
                "are worth $505, unrealized gain is $505 - $496 = $9.00 per "
                "share, and the shares are still owned. If SPY finishes at "
                "$480: the call expires worthless, the position shows a loss "
                "of $496 - $480 = $16.00 per share - smaller than the $20.00 "
                "loss an uncovered stock-only position would show, but still "
                "a real loss.",
            ),
        ),
    ),
    Lesson(
        lesson_number=5,
        title="Rolling a Covered Call",
        topics=("rolling", "roll up", "roll out", "roll up and out"),
        keywords=("rolling", "roll"),
        related_concepts=("LC-02-03", "LC-11-01"),
        sections=(
            Section(
                "What Rolling Means",
                "**Rolling** means buying to close the existing short call and "
                "simultaneously selling to open a different one, usually with "
                "a higher strike, a later expiration, or both - typically done "
                "when the stock has approached or exceeded the strike and the "
                "writer wants to avoid assignment while staying in the "
                "covered-call strategy.",
            ),
            Section(
                "Roll Up, Roll Out, Roll Up and Out",
                "**Rolling up** moves to a higher strike at the same "
                "expiration, giving the stock more room before the cap "
                "applies, usually for a net debit (the new call is worth more "
                "than the old one being closed). **Rolling out** keeps the "
                "same strike but moves to a later expiration, usually for a "
                "net credit. **Rolling up and out** does both at once.",
            ),
            Section(
                "It Closes One Trade, Not Erases It",
                "Rolling is a new, separate transaction - it closes the "
                "current short call at whatever it costs to buy back (which "
                "may be a loss on that specific leg if the stock has rallied "
                "hard) and opens a new one. It does not undo or erase the "
                "result of the leg being closed; it only changes what "
                "happens going forward. A trader should evaluate a roll on "
                "its own merits (does the new strike/expiration still make "
                "sense right now?), not simply as a way to avoid ever "
                "realizing a loss on the option leg.",
            ),
        ),
    ),
    Lesson(
        lesson_number=6,
        title="When Covered Calls Are Inappropriate",
        topics=("suitability", "opportunity cost"),
        keywords=("inappropriate", "mistakes", "suitability"),
        related_concepts=("LC-02-02", "LC-02-04"),
        sections=(
            Section(
                "Strongly Bullish Conviction",
                "Selling calls against a stock the trader believes is about "
                "to make a large move higher caps exactly the outcome the "
                "trader is betting on. If the conviction is genuinely that "
                "strong, owning the stock uncapped (or buying calls, Chapter "
                "3) captures it; a covered call does not.",
            ),
            Section(
                "Stock the Trader Does Not Want to Sell",
                "Assignment is a real possible outcome, not a remote edge "
                "case, whenever the stock is above the strike at expiration. "
                "Writing calls against shares held for reasons other than "
                "trading - for example a large unrealized capital-gains "
                "position where a sale has real tax consequences (Chapter "
                "42), or shares held for a specific non-trading purpose - can "
                "create an outcome (forced sale) that costs more than the "
                "premium collected is worth.",
            ),
            Section(
                "Common Mistakes",
                "Two recurring mistakes: selling calls with strikes so close "
                "to the current price that ordinary volatility triggers "
                "assignment almost immediately, defeating any income-holding "
                "intent; and treating the premium collected as risk-free "
                "income while ignoring that the position is still "
                "fundamentally exposed to the stock falling - a covered call "
                "reduces downside risk modestly, it does not remove it.",
            ),
        ),
    ),
]
