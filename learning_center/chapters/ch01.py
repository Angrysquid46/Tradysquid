"""Chapter 1: Definitions."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 1

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Calls and Puts",
        topics=("call option", "put option", "buyer", "seller", "writer"),
        keywords=("call", "put", "option contract", "long", "short"),
        related_concepts=("LC-01-02", "LC-01-06", "LC-01-07"),
        sections=(
            Section(
                "Overview",
                "An option is a contract between two parties, a buyer and a seller "
                "(also called the writer), covering an underlying asset - a stock, "
                "an ETF, or an index. There are exactly two kinds: calls and puts. "
                "A **call** gives its buyer the right, but not the obligation, to "
                "**buy** the underlying at a fixed price. A **put** gives its buyer "
                "the right, but not the obligation, to **sell** the underlying at a "
                "fixed price. Every option that exists has both a buyer and a "
                "seller on the other side of the same contract - options are not "
                "created by an exchange the way shares are; they are written into "
                "existence when a buyer and a seller agree to trade one.",
            ),
            Section(
                "Rights vs. Obligations",
                "This is the single most important asymmetry in options: the "
                "**buyer** of a call or a put has a *right* they may or may not "
                "use, and the most they can ever lose is the price they paid for "
                "it (the premium). The **seller** (writer) of that same contract "
                "has accepted an *obligation* - if the buyer chooses to exercise "
                "their right, the seller must perform. A call writer must sell the "
                "underlying at the agreed price if assigned; a put writer must buy "
                "it. The seller was paid the premium up front for taking on that "
                "obligation. Nothing about being a buyer or a seller determines "
                "whether a trade is bullish or bearish by itself - direction comes "
                "from combining call/put with buy/sell, covered next.",
            ),
            Section(
                "The Four Basic Positions",
                "Combining call-or-put with buyer-or-seller gives exactly four "
                "starting positions:\n"
                "- **Long a call** (bought a call): bullish, defined risk (the "
                "premium paid), unlimited theoretical upside.\n"
                "- **Short a call** (sold/wrote a call): bearish-to-neutral, "
                "premium collected up front, risk depends on whether the seller "
                "already owns the underlying (covered) or not (naked - see "
                "Chapters 2 and 5).\n"
                "- **Long a put** (bought a put): bearish, defined risk (the "
                "premium paid), large but not unlimited profit potential (the "
                "underlying can only fall to zero).\n"
                "- **Short a put** (sold/wrote a put): bullish-to-neutral, "
                "premium collected up front, obligated to buy the underlying if "
                "assigned.\n"
                "Every strategy in this curriculum, no matter how many legs it "
                "has, is built from combinations of these four.",
            ),
            Section(
                "Common Mistakes",
                "New traders often assume 'buying' always means bullish and "
                "'selling' always means bearish - that's only true for calls. "
                "Buying a *put* is bearish, and selling a *put* is bullish-to-"
                "neutral. Always read call/put and buy/sell together, never one "
                "in isolation.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Strike Price and Expiration",
        topics=("strike price", "exercise price", "expiration date", "0DTE"),
        keywords=("strike", "exercise price", "expiration", "DTE", "days to expiration"),
        related_concepts=("LC-01-01", "LC-01-04", "LC-01-07"),
        sections=(
            Section(
                "Strike Price",
                "The **strike price** (or exercise price) is the fixed price at "
                "which the underlying will change hands if the option is "
                "exercised. It is set when the contract is created and never "
                "changes for the life of that contract. A single underlying "
                "typically has many strikes listed simultaneously, spaced at "
                "regular intervals (e.g. every $1 or $5 depending on the "
                "underlying's price and the exchange's listing rules), so a "
                "trader can choose how far the strike sits from the current "
                "price.",
            ),
            Section(
                "Expiration Date",
                "Every option contract has an **expiration date** - the last day "
                "the right it grants can be used. After expiration the contract "
                "ceases to exist; if it was never exercised or closed, it simply "
                "expires worthless (from the buyer's side) or the writer's "
                "obligation simply ends (from the seller's side), whichever "
                "applies. Contracts are commonly described by their **days to "
                "expiration (DTE)**. A **0DTE** option expires the same day it "
                "trades - same-day directional bets carry the fastest time decay "
                "of any listed option, discussed further once Chapter 4's Greeks "
                "material covers theta.",
            ),
            Section(
                "Why Strike and Expiration Together Define the Contract",
                "A strike price alone or an expiration date alone does not "
                "identify an option - the two together, plus the underlying and "
                "whether it's a call or a put, fully specify one unique contract. "
                "'The $500 call' is meaningless without also saying which "
                "expiration; 'the March calls' is meaningless without also "
                "saying which strike. A full option symbol encodes all four "
                "pieces (underlying, expiration, strike, call/put) so there is "
                "never ambiguity about which exact contract is being quoted or "
                "traded.",
            ),
            Section(
                "Worked Example",
                "Suppose SPY is trading at $500.00 and a trader looks at the "
                "$505 call expiring in 30 days. The strike ($505) is $5 above the "
                "current price - this call only has value at expiration if SPY "
                "closes above $505. The expiration (30 days out) sets how much "
                "time the underlying has to reach and clear that strike. Move "
                "the strike closer to $500 and the call becomes more likely to "
                "finish valuable, and costs more today; push expiration further "
                "out and the same thing happens, for a different reason - more "
                "time for the move to happen.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Premium, Intrinsic Value, and Extrinsic Value",
        topics=("premium", "intrinsic value", "extrinsic value", "time value"),
        keywords=("premium", "intrinsic value", "extrinsic value", "time value"),
        related_concepts=("LC-01-04", "LC-04-01"),
        sections=(
            Section(
                "Premium",
                "The **premium** is the price of the option contract itself - "
                "what the buyer pays and the seller receives. It is always "
                "quoted per share, and one standard equity option contract "
                "controls 100 shares, so a quoted premium of $2.50 costs the "
                "buyer $250 before fees (see Lesson LC-01-06 on contract "
                "specifications). Premium is set by supply and demand in the "
                "market, but it decomposes cleanly into two pieces: intrinsic "
                "value and extrinsic value.",
            ),
            Section(
                "Intrinsic Value",
                "**Intrinsic value** is the amount an option would be worth if "
                "exercised right now - the real, immediate value it already "
                "contains. A call's intrinsic value is `max(underlying price - "
                "strike, 0)`; a put's is `max(strike - underlying price, 0)`. "
                "Intrinsic value can never be negative - an option holder simply "
                "would not exercise a right that loses money, so a losing "
                "position's intrinsic value is defined as zero, not negative.",
            ),
            Section(
                "Extrinsic Value (Time Value)",
                "**Extrinsic value**, also called time value, is everything in "
                "the premium that isn't intrinsic value: `premium - intrinsic "
                "value = extrinsic value`. It represents the market's assessment "
                "of how likely the option is to become more valuable before "
                "expiration - driven mainly by how much time remains and how "
                "much the underlying is expected to move (implied volatility, "
                "covered in Chapter 36). Extrinsic value is highest for at-the-"
                "money options with plenty of time left, and it decays toward "
                "zero as expiration approaches - an option's entire extrinsic "
                "value is always zero at the moment it expires, because there is "
                "no time left for anything to change.",
            ),
            Section(
                "Worked Example",
                "SPY is at $500. The $495 call trades for $8.00 in premium. "
                "Intrinsic value = max(500 - 495, 0) = $5.00. Extrinsic value = "
                "$8.00 - $5.00 = $3.00. If SPY stayed exactly at $500 and 20 "
                "days passed with no other change, that $3.00 of extrinsic value "
                "would have decayed toward zero, and the option's premium would "
                "have fallen toward its intrinsic value of $5.00 - even though "
                "the underlying never moved. This is why an option can lose "
                "value while the trader is 'right' about direction but wrong "
                "about timing.",
            ),
        ),
    ),
    Lesson(
        lesson_number=4,
        title="Moneyness: ITM, ATM, and OTM",
        topics=("moneyness", "in the money", "at the money", "out of the money"),
        keywords=("ITM", "ATM", "OTM", "moneyness"),
        related_concepts=("LC-01-02", "LC-01-03"),
        sections=(
            Section(
                "The Three States",
                "**Moneyness** describes the relationship between the strike "
                "price and the current underlying price, and it applies "
                "identically at any point before expiration, not only at "
                "expiration. For a **call**: in-the-money (ITM) means "
                "underlying price > strike; at-the-money (ATM) means underlying "
                "price ≈ strike; out-of-the-money (OTM) means underlying price "
                "< strike. For a **put** it flips: ITM means underlying price < "
                "strike, OTM means underlying price > strike.",
            ),
            Section(
                "Moneyness Is Not Profitability",
                "A common and costly confusion: moneyness describes the "
                "contract's relationship to the current price, not whether the "
                "position that holds it is profitable. A trader who bought a "
                "call for $8.00 that is now $6.00 in-the-money is *ITM* but "
                "still *losing money* on the trade, because they paid more than "
                "the current intrinsic value. ITM/OTM/ATM is a statement about "
                "the option, not about the trader's P&L.",
            ),
            Section(
                "Why It Matters",
                "Moneyness drives several practical things covered later in "
                "this curriculum: how much of an option's premium is intrinsic "
                "versus extrinsic (Lesson LC-01-03), roughly how sensitive the "
                "option is to further underlying moves (delta, Chapter 4), and "
                "whether an option is likely to be automatically exercised at "
                "expiration (Lesson LC-01-07). Deep ITM options behave more like "
                "the underlying itself; deep OTM options behave more like a "
                "lottery ticket - cheap, with a real chance of expiring "
                "completely worthless.",
            ),
        ),
    ),
    Lesson(
        lesson_number=5,
        title="Breakeven Points",
        topics=("breakeven", "breakeven price"),
        keywords=("breakeven", "break-even"),
        related_concepts=("LC-01-01", "LC-01-03"),
        sections=(
            Section(
                "Definition",
                "The **breakeven point** is the underlying price at which a "
                "position's total profit or loss at expiration is exactly zero "
                "- the dividing line between where the position makes money and "
                "where it loses money. Every strategy in this curriculum has at "
                "least one breakeven, and spreads (Chapter 9 onward) can have "
                "two.",
            ),
            Section(
                "Single-Option Breakevens",
                "For a single long call: breakeven = strike + premium paid. The "
                "underlying has to rise enough to cover both getting the option "
                "in-the-money AND recovering the premium spent. For a single "
                "long put: breakeven = strike - premium paid. For the writer of "
                "either (the short side), the breakeven is the same price, but "
                "profit and loss are mirrored - the writer profits below "
                "breakeven on a short call, and above breakeven on a short put.",
            ),
            Section(
                "Worked Example",
                "A trader buys the SPY $500 call for $6.00 in premium. "
                "Breakeven = $500 + $6.00 = $506.00. If SPY closes at exactly "
                "$506 at expiration, the option is worth exactly $6.00 in "
                "intrinsic value - exactly what was paid, so P&L is zero. Above "
                "$506, the position is profitable dollar-for-dollar with the "
                "underlying past that point. Below $506 (down to $500), the "
                "option has some value but less than what was paid, so the "
                "trade shows a loss. Below $500, the call expires worthless and "
                "the loss is capped at the full $6.00 paid.",
            ),
            Section(
                "Common Mistake",
                "Breakeven is an *expiration* concept unless stated otherwise. "
                "An option can trade above or below its expiration breakeven "
                "at any point before expiration, because extrinsic value "
                "(Lesson LC-01-03) is still in the price - only at expiration "
                "does extrinsic value hit zero and the breakeven math above "
                "apply exactly.",
            ),
        ),
    ),
    Lesson(
        lesson_number=6,
        title="Contract Specifications",
        topics=("contract multiplier", "exercise style", "settlement"),
        keywords=("multiplier", "American style", "European style", "cash settlement", "physical settlement"),
        related_concepts=("LC-01-03", "LC-01-07"),
        sections=(
            Section(
                "Contract Multiplier",
                "One standard U.S. equity or ETF option contract controls "
                "**100 shares** of the underlying. A quoted premium of $2.30 "
                "therefore costs $230 to buy one contract (before fees), and "
                "selling one covered call against 100 owned shares uses exactly "
                "one contract. Index options (Chapter 29) are typically cash-"
                "settled against a multiplier applied to the index value "
                "instead of against real shares - always confirm an "
                "underlying's specific multiplier before sizing a trade; it is "
                "not always 100.",
            ),
            Section(
                "Exercise Style",
                "**American-style** options can be exercised by the holder on "
                "any business day up to and including expiration. **European-"
                "style** options can only be exercised at expiration itself. "
                "Most U.S. single-stock and ETF options are American-style; "
                "many broad-market index options are European-style. This "
                "matters directly for early-assignment risk, covered in Lesson "
                "LC-01-07 and again in Chapter 12.",
            ),
            Section(
                "Settlement: Physical vs. Cash",
                "**Physical settlement** means exercise/assignment actually "
                "delivers or receives shares - a call exercise buys 100 shares "
                "per contract at the strike; a put exercise sells 100 shares "
                "per contract at the strike. **Cash settlement** means no "
                "shares change hands at all - the in-the-money amount is simply "
                "paid in cash. Most equity and ETF options are physically "
                "settled; most broad index options are cash-settled. Knowing "
                "which applies to a given underlying before expiration matters "
                "- physical settlement on shares a trader did not intend to "
                "hold or short can create an unwanted, sudden stock position.",
            ),
        ),
    ),
    Lesson(
        lesson_number=7,
        title="Opening, Closing, Exercise, and Assignment",
        topics=("opening a position", "closing a position", "exercise", "assignment"),
        keywords=("buy to open", "sell to close", "exercise", "assignment", "expire worthless"),
        related_concepts=("LC-01-01", "LC-01-06"),
        sections=(
            Section(
                "Opening and Closing",
                "A position is **opened** with a buy-to-open or sell-to-open "
                "order, and **closed** with the opposite: sell-to-close for a "
                "long position, buy-to-close for a short one. Closing a "
                "position is not the same as exercising or being assigned - "
                "the large majority of listed options are opened and closed as "
                "trades in the option itself, and are never exercised at all.",
            ),
            Section(
                "Exercise",
                "**Exercise** is the buyer's choice to use the right the "
                "contract grants: a call holder who exercises buys the "
                "underlying at the strike; a put holder who exercises sells "
                "the underlying at the strike. Exercise only makes economic "
                "sense when the option has intrinsic value - exercising an "
                "out-of-the-money option would mean transacting at a worse "
                "price than the open market, so it essentially never happens "
                "voluntarily.",
            ),
            Section(
                "Assignment",
                "**Assignment** is what happens to the option's *seller* when "
                "the buyer on the other side of the contract exercises - the "
                "seller is obligated to perform: a short call gets assigned and "
                "must sell 100 shares per contract at the strike (delivering "
                "shares they may or may not already own - see Chapters 2 and 5 "
                "on covered vs. naked); a short put gets assigned and must buy "
                "100 shares per contract at the strike. Assignment is "
                "essentially random from the individual writer's point of view "
                "- it is allocated by the exchange/OCC among all sellers of "
                "that same contract, not chosen by the buyer.",
            ),
            Section(
                "Expiring Worthless",
                "If an option has zero intrinsic value at expiration, it "
                "**expires worthless** - the buyer loses the entire premium "
                "paid, and the writer keeps the entire premium received, with "
                "no exercise or assignment involved at all. This is the most "
                "common outcome for out-of-the-money options and is the entire "
                "basis for premium-selling strategies (covered starting in "
                "Chapter 2).",
            ),
            Section(
                "Common Mistake",
                "New traders sometimes assume they must actively do something "
                "to avoid exercise/assignment. In practice: a long OTM option "
                "simply expires worthless with no action needed and no further "
                "cost; a long ITM option held through expiration is typically "
                "auto-exercised by the broker under OCC rules (deadlines and "
                "exact procedures vary by broker, so this should always be "
                "confirmed directly, never assumed); a short option can be "
                "assigned at any time before expiration if it is American-"
                "style and has intrinsic value, which is exactly why 'I'll "
                "just wait and see' is a real, sometimes costly, risk for "
                "option sellers - not a passive default.",
            ),
        ),
    ),
]
