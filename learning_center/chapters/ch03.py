"""Chapter 3: Call Buying."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 3

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Why Buy Calls: Leverage and Defined Risk",
        topics=("leverage", "defined risk", "bullish speculation"),
        keywords=("leverage", "defined risk", "long call"),
        related_concepts=("LC-01-01", "LC-01-05"),
        sections=(
            Section(
                "The Core Appeal",
                "Buying a call is a bullish, **defined-risk** way to "
                "participate in a stock's upside. The most that can ever be "
                "lost is the premium paid, no matter how far the stock falls "
                "- unlike owning the stock outright, where the loss is "
                "unbounded down to zero. In exchange for that defined risk, "
                "the option can lose its entire value (100% of the premium), "
                "something outright stock ownership essentially never does in "
                "a single trade.",
            ),
            Section(
                "Leverage",
                "A call typically costs far less than 100 shares of the "
                "underlying, but its price moves in the same direction as the "
                "stock (approximated by delta, formally introduced in Chapter "
                "4). This means a given dollar amount controls more effective "
                "exposure through options than through shares - percentage "
                "gains (and losses) on the premium itself are usually much "
                "larger than the underlying's percentage move. Leverage cuts "
                "both ways: it amplifies gains on a correct call and can "
                "produce a 100% loss on an incorrect one that a comparable "
                "stock position would have merely dented.",
            ),
            Section(
                "Common Mistake",
                "Treating 'leverage' as free upside without weighing the "
                "corresponding downside is the single most common call-buying "
                "mistake. A call bought purely because it is 'cheaper than the "
                "stock' without a real thesis on direction, magnitude, and "
                "timing is a lottery ticket, not a leveraged investment - see "
                "Lesson LC-03-05.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Choosing a Strike",
        topics=("strike selection", "ITM call", "OTM call", "delta"),
        keywords=("strike selection", "in the money", "out of the money"),
        related_concepts=("LC-01-04", "LC-04-01"),
        sections=(
            Section(
                "In-the-Money Calls",
                "A deep in-the-money call costs more in absolute premium but "
                "consists mostly of intrinsic value (Lesson LC-01-03) and "
                "moves closely with the underlying dollar-for-dollar. It "
                "behaves more like a leveraged stock substitute: less "
                "sensitive to time decay and implied-volatility changes in "
                "percentage terms, more sensitive to the underlying's actual "
                "price path.",
            ),
            Section(
                "At- and Out-of-the-Money Calls",
                "At-the-money and out-of-the-money calls cost less in "
                "absolute dollars, consist mostly or entirely of extrinsic "
                "value, and offer more percentage leverage - but they need a "
                "real move in the underlying, not just 'up a little,' to "
                "become profitable, and they carry a real chance of expiring "
                "completely worthless if the move does not happen in time. "
                "The further out-of-the-money, the higher that chance.",
            ),
            Section(
                "Matching Strike to Thesis",
                "The right strike follows from the thesis, not from whichever "
                "premium looks 'cheap': a trader expecting a large, fast move "
                "may accept a lower-probability OTM call for the leverage; a "
                "trader who wants stock-like participation with less capital "
                "outlay, and is less interested in extreme leverage, is "
                "better served by an ITM call. Buying the cheapest available "
                "strike without asking what move is actually required to "
                "profit is a common, avoidable mistake.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Choosing an Expiration",
        topics=("expiration selection", "time decay", "theta"),
        keywords=("expiration selection", "time decay", "0DTE"),
        related_concepts=("LC-01-02", "LC-04-03"),
        sections=(
            Section(
                "The Time Trade-Off",
                "More time to expiration gives the underlying more room to "
                "make the anticipated move, and it costs more in premium for "
                "exactly that reason. Less time costs less but requires the "
                "move to happen faster - and time decay (theta, Chapter 4) "
                "accelerates as expiration approaches, working against the "
                "long-call holder every day the move has not yet happened.",
            ),
            Section(
                "Same-Day (0DTE) Calls",
                "0DTE calls carry the most extreme version of this trade-off: "
                "very cheap in absolute terms, but requiring the entire "
                "anticipated move to occur within a single session, with time "
                "decay running continuously against the position the whole "
                "time it is held. This is a fundamentally different, higher-"
                "variance activity than buying a call with weeks of runway, "
                "even when the strike and underlying are identical.",
            ),
            Section(
                "A Practical Rule of Thumb",
                "A frequently used guideline is to buy enough time for the "
                "expected move to plausibly happen *and* to have some cushion "
                "left over - buying exactly the amount of time the move is "
                "expected to take leaves no room for being early, which is a "
                "common and otherwise harmless kind of 'being right.'",
            ),
        ),
    ),
    Lesson(
        lesson_number=4,
        title="Risk/Reward and Worked P&L",
        topics=("maximum profit", "maximum loss", "breakeven"),
        keywords=("max profit", "max loss", "breakeven", "P&L"),
        related_concepts=("LC-01-05", "LC-03-01"),
        sections=(
            Section(
                "Maximum Loss and Maximum Profit",
                "Maximum loss on a long call = premium paid, period - "
                "realized at any underlying price at or below the strike at "
                "expiration. Maximum profit is theoretically unlimited: "
                "profit grows dollar-for-dollar with the underlying above the "
                "breakeven point (strike + premium paid, from Lesson "
                "LC-01-05), with no cap.",
            ),
            Section(
                "Worked Example",
                "SPY is at $500.00. A trader buys the $505 call, 30 days out, "
                "for $6.00 ($600 per contract). Breakeven = $511.00. If SPY "
                "finishes at $520: intrinsic value = $15.00, profit = $15.00 "
                "- $6.00 = $9.00 per share ($900 per contract) - 150% return "
                "on the premium risked, versus a 4% move in the underlying "
                "itself. If SPY finishes at $505: the call is worth exactly "
                "its intrinsic value of $0, a full loss of the $6.00 premium, "
                "even though the underlying only fell 1% from where the call "
                "was bought and did not fall at all from the strike. If SPY "
                "finishes below $505: same full loss of $600 per contract, "
                "regardless of how far below.",
            ),
        ),
    ),
    Lesson(
        lesson_number=5,
        title="Common Mistakes in Call Buying",
        topics=("mistakes", "position management"),
        keywords=("common mistakes", "lottery ticket", "position sizing"),
        related_concepts=("LC-03-01", "LC-10-01"),
        sections=(
            Section(
                "Being Right on Direction but Wrong on Everything Else",
                "A call can lose money even when the underlying eventually "
                "moves in the predicted direction, if it moves too slowly, "
                "too late, or not far enough past the strike to overcome the "
                "premium paid - direction alone is not a complete thesis; "
                "magnitude and timing have to be part of it too (see Lessons "
                "LC-03-02 and LC-03-03).",
            ),
            Section(
                "Oversizing a Defined-Risk Position",
                "Because the maximum loss on a long call is capped and known "
                "in advance, it is tempting to treat position size as less "
                "important than it is with unbounded-risk strategies. But a "
                "'small' premium repeated across an oversized number of "
                "contracts, or concentrated in one single all-or-nothing bet, "
                "produces the same account-level damage as any other "
                "oversized position - defined risk per contract is not the "
                "same as defined risk to the account. See Chapter 10 for "
                "position-sizing discipline that applies regardless of "
                "strategy.",
            ),
            Section(
                "No Exit Plan Before Entry",
                "Because a long call can go to zero, entering without a "
                "predefined target, stop, and time-based exit plan (what "
                "happens if the move hasn't occurred with only a few days "
                "left?) is a common way small, thesis-driven losses become "
                "full, avoidable ones. See Chapter 11 for trade planning and "
                "management.",
            ),
        ),
    ),
]
