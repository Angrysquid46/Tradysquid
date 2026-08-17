"""Authored Learning Center content.

The source material (`learning update.txt`) supplies real explanations for
only 17 of its 101 modules - 28-43 and 52. Everything from module 44 onward
is a title list, which is why 336 of 386 sections rendered as "Covered in
source module N. See the surrounding sections." Owner: "i should be able to
open everything and see what it means not get this generic go here and see
message."

So the bodies are written here, keyed by the exact topic title. The
installer prefers an authored body, falls back to the source body, and only
then to the placeholder - so this file can be filled in over several passes
without the structure changing and without a partial pass breaking anything
already published.

House style, matching the existing hand-authored channels:
- lead with what the thing IS in plain language, not a definition by synonym
- give the actual math where math exists
- say what it means for a decision, since a definition nobody can act on is
  trivia
- name the failure mode; most of these concepts cost people money in one
  specific, predictable way
"""

from __future__ import annotations

AUTHORED_BODIES: dict[str, str] = {

    # ---------------------------------------------------------------
    # The Greeks
    # ---------------------------------------------------------------
    "Delta: Price Sensitivity, Hedge Ratios, and Moneyness Probabilities":
        "Delta is how much the option price moves for a $1 move in the underlying. "
        "A 0.45-delta call gains roughly $0.45 of premium (i.e. $45 per contract) "
        "when SPY rises $1. It does three jobs at once: it is the sensitivity, it is "
        "the hedge ratio (100 shares per 1.00 of delta), and it is a rough "
        "market-implied probability the contract finishes in the money. "
        "For decisions: delta is what you are actually buying. A 0.20-delta lottery "
        "ticket needs a large move to pay; a 0.60-delta contract behaves more like "
        "stock and costs accordingly. The failure mode is treating delta as fixed - "
        "it changes constantly, which is what gamma measures.",

    "Gamma: The Acceleration Engine of Delta and Long Option Squeezes":
        "Gamma is the rate delta itself changes per $1 move. If delta is speed, gamma "
        "is acceleration. A 0.40-delta call with 0.08 gamma becomes a 0.48-delta call "
        "after a $1 rise, so the next dollar earns more than the last. "
        "Gamma is largest at the money and explodes as expiry approaches - which is "
        "the entire character of 0DTE. A same-day at-the-money contract can go from "
        "0.50 delta to 0.90 or to 0.10 within an hour. That cuts both ways: the "
        "convexity that makes a winner run is the same mechanism that makes a loser "
        "collapse before you can react. Long options own gamma; short options are "
        "short it, which is why selling naked near expiry is how accounts die.",

    "Theta: The Mechanics of Time Decay and Premium Bleed Schedules":
        "Theta is how much premium the contract loses per day purely from time "
        "passing, holding price and volatility constant. A theta of -0.25 means about "
        "$25 per contract per day evaporates if nothing else changes. "
        "Decay is not linear. It accelerates into expiry, and on the final day it is "
        "brutal: an at-the-money 0DTE option is nearly all extrinsic value at 09:45 "
        "and nearly all intrinsic by 15:59. That is the single most important fact "
        "for this system - our own Phase 5 modelling showed a flat session takes an "
        "ATM 0DTE call from $1.52 to the -50% stop without the underlying moving at "
        "all. Being right on direction and slow on timing still loses.",

    "Vega: Implied Volatility Sensitivity and the Impact of IV Expansion/Contraction":
        "Vega is how much premium changes per 1 percentage point change in implied "
        "volatility. A vega of 0.12 means the contract gains about $12 if IV rises "
        "from 15% to 16%, with price unchanged. "
        "This is how you lose money while being right about direction: buying calls "
        "into an event at inflated IV, watching the stock rise, and still losing "
        "because IV collapsed afterwards (\"IV crush\"). Vega is largest on longer-"
        "dated contracts and shrinks toward expiry - a 0DTE has very little vega and "
        "enormous gamma, which is why 0DTE is a bet on movement now rather than on "
        "volatility levels.",

    "Rho: Assessing the Structural Impact of Interest Rate Shifts on LEAPs":
        "Rho is sensitivity to interest rates: how much premium changes per 1 "
        "percentage point move in the risk-free rate. Calls gain value as rates rise "
        "(holding a call is cheaper than holding the stock, and that financing "
        "advantage is worth more when rates are high); puts lose. "
        "For day trading it is irrelevant - a 0DTE contract has essentially zero rho, "
        "which is why this system uses a flat 2% assumption in its pricing model "
        "without materially affecting anything. Rho matters for LEAPs and other "
        "year-plus contracts, where a rate regime change is a real component of "
        "return.",

    "Options Delta: Gauging Price Tracking Speed and Contract Probabilities":
        "The same measure as Delta above, framed as contract selection. This system's "
        "scanners choose by delta band rather than by strike, because the delta band "
        "is what actually fixes the trade's character: 0.40-0.60 keeps contracts "
        "responsive enough to capture a real move while staying liquid and inside the "
        "$5.00 ask cap. "
        "Picking a strike without checking delta means the same nominal distance from "
        "spot buys a very different trade on a quiet day than on a volatile one.",

    "Options Gamma: The Gas Pedal and Accelerator of Long Option Premiums":
        "Gamma restated as position management. Because gamma peaks at the money and "
        "near expiry, a 0DTE position's risk profile changes faster than a trader can "
        "monitor it manually. "
        "Practical consequence: exits must be rule-based and pre-committed. A stop "
        "you intend to \"watch for\" is not a stop on a contract whose delta can "
        "double in ten minutes - by the time you have decided, the premium has already "
        "made the decision for you.",

    "Options Theta: The Relentless Clock and Time Decay Bleed Schedules":
        "Theta restated as a schedule rather than a number. Decay is slow with weeks "
        "left, steep in the final days, and near-vertical in the final hours. "
        "This is why holding to the close is the worst pattern for a long 0DTE, and "
        "why our own backtest found the underlying edge in several strategies did not "
        "survive being expressed as same-day options: the entry was right, the "
        "holding period handed the profit to decay.",

    "Options Vega: Identifying How Changes in Market Implied Volatility Crash or Inflate Premiums":
        "Vega restated as event risk. Premium is inflated before scheduled events "
        "(earnings, FOMC, CPI) because the market prices in a larger expected move, "
        "and deflates immediately afterward regardless of outcome. "
        "The trap is buying the anticipation. If you are long premium into an event, "
        "you need the move to exceed what was already priced in - not merely to be "
        "directionally correct.",

    # ---------------------------------------------------------------
    # Option contracts: basics
    # ---------------------------------------------------------------
    "The Concept of Options: Rights vs. Obligations":
        "An option is a contract, not a share. Buying one gives you the RIGHT to buy "
        "(call) or sell (put) 100 shares at a fixed price before expiry, with no "
        "obligation to do so - your maximum loss is the premium paid. Selling one "
        "gives you the OBLIGATION to take the other side if assigned, in exchange for "
        "receiving that premium - and your loss can far exceed what you collected. "
        "That asymmetry is the whole subject. Everything else - the Greeks, spreads, "
        "assignment - is detail about how the right or the obligation is priced and "
        "managed. This system only ever BUYS options, so risk per trade is capped at "
        "the premium.",

    "Deconstructing the Option Premium: Intrinsic vs. Extrinsic Value":
        "Premium splits into two parts. Intrinsic value is the amount the contract is "
        "already in the money: for a call, max(spot - strike, 0). Extrinsic value is "
        "everything else - what you pay for the possibility of further movement in the "
        "time remaining. "
        "A $770 call with SPY at $775 trading at $6.20 is $5.00 intrinsic and $1.20 "
        "extrinsic. At expiry extrinsic value is zero by definition, so the entire "
        "$1.20 must be earned back by movement or it is lost. Theta is the schedule on "
        "which that $1.20 disappears; on a 0DTE it disappears within hours.",

    "Definition and Role of the Strike Price (Exercise Price)":
        "The strike is the fixed price at which the contract converts to shares. It "
        "determines moneyness, and through moneyness it determines almost everything "
        "else - delta, the intrinsic/extrinsic split, the cost, and the probability of "
        "finishing in the money. "
        "Strike selection is the trade. Two traders can be equally right about "
        "direction and get opposite results because one bought a strike needing a 0.3% "
        "move and the other bought one needing 1.5% in the same session.",

    "Option Expiration Dates and the Lifecycle of a Contract":
        "Every contract has a fixed death date. SPY now lists expirations every "
        "trading day, which is what makes 0DTE possible - but that is recent: daily "
        "expiries only became universal in 2023. Before that, same-day contracts "
        "existed on 38-157 days a year depending on the era, which is a real limit on "
        "how far back 0DTE strategies can honestly be tested. "
        "The lifecycle: extrinsic value decays continuously, gamma rises as expiry "
        "nears, and at the close the contract is worth exactly its intrinsic value or "
        "nothing. Anything not closed is auto-exercised if in the money, which is why "
        "this system forces every position flat before the bell.",

    "Common Stock vs. Preferred Stock Ownership":
        "Common stock is fractional ownership with voting rights and residual claim - "
        "you are paid last, after employees, suppliers, lenders and preferred holders. "
        "Preferred stock trades more like a bond: a fixed dividend, priority over "
        "common in a liquidation, usually no vote. "
        "For an options trader this matters mainly through capital structure: a company "
        "with heavy preferred or debt obligations has more leveraged common equity, "
        "which shows up as higher realised volatility.",

    "Market Capitalization Regimes (Mega, Large, Mid, Small Cap)":
        "Market cap is share price times shares outstanding. The conventional bands - "
        "mega above $200B, large $10-200B, mid $2-10B, small under $2B - matter to a "
        "trader because they proxy liquidity. "
        "Liquidity determines whether an options market is tradeable at all: tight "
        "spreads and real open interest exist on mega-caps and major ETFs, and "
        "essentially nowhere else at the size and speed 0DTE requires. It is not an "
        "accident that this system trades SPY exclusively.",

    "The Dividend Distribution Cycle (Declaration, Ex-Date, Record, Payment)":
        "Four dates. Declaration is the announcement; ex-dividend is the first day the "
        "stock trades without the right to the payout (and the price typically drops "
        "by roughly the dividend amount); record is who is on the books; payment is "
        "when cash arrives. "
        "The one that matters for options is the ex-date. It causes a mechanical price "
        "drop that is NOT a bearish signal, and it is the main trigger for early "
        "assignment on short in-the-money calls - someone exercising to capture the "
        "dividend. SPY pays quarterly, so the ex-date is a scheduled, checkable event.",

    "Stock Splits, Reverse Splits, and Fractional Share Mechanics":
        "A split multiplies share count and divides price, leaving market cap "
        "unchanged - a 4-for-1 turns one $400 share into four $100 shares. A reverse "
        "split does the opposite, usually to maintain an exchange listing. "
        "For options, splits trigger contract adjustment: strike and multiplier are "
        "restated so the economics are preserved. Adjusted contracts often become "
        "illiquid and behave oddly, and are best avoided. A price chart that has not "
        "been split-adjusted will show a phantom crash on the split date - a common "
        "way backtests get corrupted.",

    # ---------------------------------------------------------------
    # Indices and ETFs
    # ---------------------------------------------------------------
    "Market-Cap Weighted Indices (S&P 500) vs. Price-Weighted Indices (DJIA)":
        "The S&P 500 weights by market capitalisation, so a company's influence "
        "tracks its size - which means the largest handful of names drive most of the "
        "index's movement. The Dow weights by SHARE PRICE, an artefact of 1896 "
        "arithmetic, so a $500 stock moves it more than a $50 stock regardless of "
        "which company is larger. "
        "This is why SPY and DIA diverge, and why S&P breadth can be poor while the "
        "index rises: a handful of mega-caps can carry it while the median constituent "
        "falls.",

    "Understanding Exchange-Traded Funds (ETFs) vs. Mutual Funds":
        "Both pool assets, but an ETF trades continuously on an exchange at a market "
        "price, while a mutual fund transacts once daily at net asset value. That "
        "single difference gives ETFs intraday liquidity, short-ability, and an "
        "options market - none of which mutual funds have. "
        "SPY is the oldest and most liquid US ETF, which is precisely why it supports "
        "penny-wide spreads and daily expirations. The tradability of this entire "
        "system rests on that liquidity.",

    "Authorized Participants and the ETF Creation-Redemption Mechanism":
        "Large institutions (Authorized Participants) can exchange a basket of the "
        "underlying shares for new ETF units, or vice versa. If SPY trades above the "
        "value of its holdings, an AP buys the basket, creates units, and sells them - "
        "pushing the price back down. If it trades below, the reverse. "
        "This arbitrage is why an ETF tracks its index closely rather than drifting "
        "like a closed-end fund. It also explains why tracking breaks down in a "
        "crisis: when the underlying basket becomes hard to trade, the arbitrage "
        "widens and the ETF can dislocate.",

    "Leveraged and Inverse ETFs: Tracking Compounding Tracking Errors":
        "A 3x ETF targets three times the DAILY return, not three times the return "
        "over any longer period. Because it rebalances daily, returns compound "
        "path-dependently: an index that falls 10% then rises 11.1% is flat, while its "
        "3x version is down about 2%. Choppy markets grind these products down even "
        "when the index goes nowhere. "
        "They are instruments for a single session, not holdings. The decay is "
        "structural and is not a fee you can avoid by choosing a cheaper issuer.",

    # ---------------------------------------------------------------
    # Directional strategies
    # ---------------------------------------------------------------
    "Straight Outright Call Buying: Capitalizing on Aggressive Bullish Velocity":
        "Buy a call, pay the premium, keep unlimited upside with loss capped at what "
        "you paid. The simplest bullish expression and the one this system uses. "
        "The catch is that you need direction AND speed AND enough size of move to "
        "clear the extrinsic value you paid. Being right slowly is a loss. On a 0DTE "
        "the bar is highest: an at-the-money contract needs roughly a 0.3-0.5% move "
        "just to cover decay and the spread. That is why entry timing matters more "
        "here than in any other structure - the clock is the counterparty.",

    "Straight Outright Put Buying: Capitalizing on Catastrophic Bearish Cascades":
        "The mirror: buy a put to profit from a fall, loss capped at premium. Puts "
        "usually cost more than equivalent calls because of skew - the market pays up "
        "for downside protection, so implied volatility is higher on the put side. "
        "Downside moves are also faster than upside ones, which helps a long put fight "
        "decay. But that same skew means you are buying at a structurally worse price, "
        "and if the drop does not come quickly the inflated premium works against you "
        "twice: theta plus IV normalisation.",

    "Long Straddles: Profiting from Mass Volatility Explosions in Either Direction":
        "Buy a call and a put at the same strike and expiry. You profit from a large "
        "move in EITHER direction, and lose if price sits still. Cost is roughly double "
        "a single leg, so the breakeven is wide: the move must exceed the combined "
        "premium. "
        "The classic mistake is buying one before earnings. IV is already inflated to "
        "price the expected move, so a merely large move is not enough - you need one "
        "larger than the market already paid for, and the post-event IV crush hits both "
        "legs at once.",

    "Long Strangles: Budget-Conscious Volatility Plays with Out-of-the-Money Wings":
        "Same idea as a straddle but with out-of-the-money strikes on both sides. "
        "Cheaper to open, and therefore needs an even bigger move to pay. "
        "The trade-off is explicit: you save premium up front in exchange for a wider "
        "dead zone where both legs expire worthless. On short-dated contracts a strangle "
        "usually ends up as two lottery tickets that both lose - the discount is not "
        "free, it is a reduced probability.",

    "Bull Call Spreads: Capping Upside Profits to Drastically Reduce Contract Costs":
        "Buy a call, sell a higher-strike call in the same expiry. The sold leg pays "
        "for part of the bought leg, cutting cost and breakeven, at the price of a "
        "fixed maximum profit. "
        "The reason this works is that you are also selling vega and theta: the short "
        "leg decays in your favour, offsetting some of the bleed on the long leg. It "
        "is a more forgiving structure than an outright call when your view is "
        "'higher, but not dramatically' - which is most of the time.",

    "Bear Put Spreads: Capping Downside Gains to Mitigate Implied Volatility Crushes":
        "Buy a put, sell a lower-strike put. Bearish, defined risk, defined reward. "
        "Particularly useful when puts are expensive from skew: the short leg recovers "
        "some of that inflated premium, so you are not paying full price for fear. "
        "You give up the tail - a genuine crash pays the same as a moderate decline "
        "once price passes the short strike.",

    "Bull Put Credit Spreads: High-Probability Income Generation on Structural Floors":
        "Sell a put, buy a lower-strike put for protection. You are paid up front and "
        "keep the credit if price stays above the short strike. Maximum loss is the "
        "strike width minus the credit. "
        "The seduction is the win rate: these are right most of the time. The danger is "
        "the payoff shape - many small wins and occasional losses several times larger, "
        "so a single bad week erases months. **This system does not sell premium**; "
        "everything it trades is long-only with risk capped at the debit paid.",

    "Bear Call Credit Spreads: Systematically Selling Premium Beneath Ceilings":
        "The bearish mirror: sell a call, buy a higher-strike call. Collect credit, "
        "profit if price stays below the short strike. "
        "Same asymmetry as the bull put spread, with the added hazard that upside gaps "
        "in an index can be violent and the short call carries assignment risk if it "
        "goes in the money near a dividend date. Defined-risk on paper still means "
        "losing the full width in one session.",

    # ---------------------------------------------------------------
    # Neutral and multi-leg
    # ---------------------------------------------------------------
    "Classic Iron Condors: Exploiting Double-Sided Horizontal Sideways Chop":
        "Sell a call spread above the market and a put spread below it. You are paid "
        "to bet price stays between them. Profit is the credit; loss is capped at one "
        "wing's width minus the credit. "
        "It profits from time and from falling volatility, not direction. Its weakness "
        "is that the market only has to break one side to hurt you, and the losing side "
        "moves faster than the winning side decays. Phase 5 could not test this "
        "structure at all - its entire P/L is premium decay with no underlying entry "
        "to measure.",

    "Iron Butterflies: Pinning At-The-Money Premium to Maximize Intraday Theta Melt":
        "An iron condor with both short strikes at the same at-the-money price. "
        "Collects far more premium than a condor because at-the-money options are the "
        "richest, but the profitable zone is correspondingly narrow. "
        "Maximum profit requires price to finish almost exactly at the strike. It is a "
        "pure theta harvest and it is at its most dangerous into expiry, when gamma on "
        "the short strikes turns a small move into a large loss within minutes.",

    "Long & Short Calendar Spreads: Exploiting Differing Time Horizon Decay Horizons":
        "Sell a near-dated option and buy a longer-dated one at the same strike. The "
        "near leg decays faster than the far leg, and that difference is the profit. "
        "This is a bet on the TERM STRUCTURE of volatility, not on direction. It works "
        "when near-dated IV is elevated relative to longer-dated, and it fails when the "
        "underlying moves sharply away from the strike - both legs lose their "
        "at-the-money richness together.",

    "Long & Short Diagonal Spreads: Blending Structural Time and Strike Variations":
        "A calendar spread with different strikes as well as different expiries, so it "
        "carries both a time view and a directional lean. "
        "More flexible and correspondingly harder to reason about: you are simultaneously "
        "exposed to direction, term structure and skew. Position sizing should reflect "
        "that you have three ways to be wrong rather than one.",

    "Ratio Spreads: Unbalanced Contract Counts for Delta-Neutral Volatility Exploitations":
        "Buy one option and sell two or more further out, so the sold legs finance the "
        "bought one - sometimes for a net credit. "
        "The extra short contract is naked. Beyond the short strike, losses grow without "
        "limit on the call side. A structure that can be opened for a credit and still "
        "bankrupt the account is exactly the kind that reads as free money and is not.",

    "Broken Wing Butterflies: Structuring Zero-Downside Risk Profiles on Premium Spreads":
        "A butterfly with unequal wing widths, skewed so one side carries no risk - "
        "often opened for a credit, so one direction cannot lose. "
        "The risk is displaced, not removed: the wider wing carries a larger maximum "
        "loss than a standard butterfly. It is a way of choosing WHERE your risk sits, "
        "which is useful when you have a strong view about which side is safe.",

    "Box Spreads: Multi-Leg Arbitrage Matrix for Capturing Pure Synthetic Financing Rates":
        "A bull call spread plus a bear put spread on the same strikes creates a "
        "position worth exactly the strike width at expiry regardless of price - a "
        "synthetic loan. Traders use it to borrow or lend at the options market's "
        "implied rate. "
        "It is only riskless with EUROPEAN-style options. Doing it with American-style "
        "contracts exposes you to early assignment, which is how one retail account "
        "famously lost far more than it had - a 'riskless' trade that was not.",

    "Christmas Tree Spreads: Non-Standard Strike Configurations for Precision Targets":
        "Multi-leg structures using uneven strike spacing and contract counts to shape "
        "a payoff around a specific expected outcome. "
        "Precision costs complexity: more legs mean more commission, more spread paid on "
        "entry and exit, and more ways for a partial fill to leave you with a position "
        "you did not intend. Rarely worth it below institutional size.",

    # ---------------------------------------------------------------
    # Moneyness
    # ---------------------------------------------------------------
    "Deconstructing In-The-Money (ITM) vs. Out-of-The-Money (OTM) Contracts":
        "In the money means the contract already has intrinsic value - a call whose "
        "strike is below spot. Out of the money has none: all premium is time value, and "
        "it expires worthless unless price crosses the strike. "
        "ITM contracts cost more, move more closely with the stock (higher delta), and "
        "lose a smaller PERCENTAGE to decay because much of their value is intrinsic. "
        "OTM contracts are cheap, mostly decay, and need a real move to be worth "
        "anything. Neither is better; they are different trades.",

    "The Lottery-Ticket Fallacy: Why Buying Cheap Options Feels Good but Loses Money":
        "A $0.05 far-out-of-the-money contract looks like limited risk with huge upside. "
        "In practice it is nearly all decay with a very low probability of paying, and "
        "the bid/ask spread alone can be 20-50% of the price - you are down badly the "
        "instant you fill. "
        "The psychology is the problem: cheap contracts let you take many positions "
        "without feeling exposed, so total risk grows while each individual bet feels "
        "trivial. The system's $5.00 ask cap and 0.40-0.60 delta band exist "
        "specifically to keep contract selection out of this zone.",

    "At-The-Money (ATM) Options: Balancing Risk, Premium Price, and Directional Speed":
        "At the money means strike near spot - roughly 0.50 delta, the most extrinsic "
        "value, and the highest gamma. It responds fastest to movement in both "
        "directions. "
        "It is the standard choice for a short-dated directional trade because it "
        "balances responsiveness against cost. It also carries the most decay in "
        "absolute terms, which is why holding an ATM 0DTE through a quiet afternoon is "
        "the most reliable way to lose money in this entire system.",

    "Understanding Option Premiums: Separating True Cash Worth from Extrinsic Time Value":
        "Every premium answers two questions: what is this worth right now if exercised "
        "(intrinsic), and what am I paying for what might still happen (extrinsic). "
        "Only the extrinsic part decays. That makes the ratio the single most useful "
        "number when choosing a contract: a deep ITM call is mostly intrinsic and behaves "
        "like leveraged stock, while an ATM 0DTE is nearly all extrinsic and is a bet "
        "that must resolve within hours.",

    # ---------------------------------------------------------------
    # Expiration and assignment
    # ---------------------------------------------------------------
    "Long Call/Put Positions: The Rights of the Premium Buyer":
        "As the buyer you hold a right and no obligation. You can exercise, sell the "
        "contract, or let it expire. Maximum loss is the premium, known at entry and "
        "unchangeable. "
        "That certainty is why this system only buys. Position sizing becomes simple "
        "arithmetic - the $500 per-trade cap is genuinely the worst case, with no gap "
        "risk or margin call able to exceed it.",

    "Short Call/Put Positions: The Obligations of the Premium Seller (Writing Options)":
        "As the seller you receive premium and take on an obligation: deliver shares if "
        "a call is assigned, buy them if a put is. Gains are capped at the credit; "
        "losses are not. "
        "A naked short call is theoretically unlimited. Even 'defined risk' spreads can "
        "lose their full width overnight on a gap. Selling premium wins most of the time "
        "and loses large when it loses, which is the opposite payoff shape to everything "
        "this system trades.",

    "Understanding Options Exercise, Delivery, and Settlement Processes":
        "Exercise converts the contract into its underlying obligation. Equity and ETF "
        "options like SPY deliver 100 actual shares per contract; index options like SPX "
        "settle in cash. "
        "In-the-money contracts are AUTOMATICALLY exercised at expiry by the clearing "
        "house - by as little as a cent. That is why an unclosed 0DTE call can leave you "
        "holding $77,500 of SPY on Monday morning, and why every position in this system "
        "is forced flat before the close rather than left to expire.",

    "Navigating Assignment Risk, Early Assignment, and Margin Calls":
        "American-style options can be exercised by the holder at any time, so a short "
        "position can be assigned early - most commonly on in-the-money calls the day "
        "before an ex-dividend date, when exercising captures the dividend. "
        "Assignment arrives as shares plus a cash obligation you did not plan for, which "
        "is how a defined-risk spread becomes a margin call. Long-only positions are "
        "immune: you can be assigned only if you are short.",

    "The Mechanics of Pin Risk: Navigating 3:59 PM Expiration Imbalances":
        "Pin risk is the uncertainty when price finishes almost exactly at a strike. You "
        "do not know whether you will be assigned, so you do not know your Monday "
        "position or your overnight exposure. "
        "Large open interest at a strike also tends to ATTRACT price into expiry, because "
        "dealer hedging concentrates there - see the dealer gamma channel. The practical "
        "rule is simple: close near-the-money positions before the bell rather than "
        "gambling on which side of the strike the last print lands.",
}


def authored_body(title: str) -> str | None:
    """The written explanation for a topic, if one exists yet."""
    return AUTHORED_BODIES.get(title)


def coverage() -> dict[str, int]:
    return {"authored": len(AUTHORED_BODIES)}
