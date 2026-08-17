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

    # ---------------------------------------------------------------
    # Risk architecture and backtesting
    # ---------------------------------------------------------------
    "Defining Expectancy, Profit Factor, and System Edge Metrics":
        "Expectancy is average profit per trade: (win rate x average win) - (loss rate "
        "x average loss). It is the only number that answers 'should I take this trade "
        "again'. Profit factor is gross wins divided by gross losses - above 1.0 is "
        "profitable, and below about 1.2 is too thin to survive costs. "
        "Win rate alone is meaningless. This system's own results make the point: the "
        "strongest strategy found wins 56.8% with a profit factor of 1.30, while "
        "several 60%+ win-rate variants lose money because their losses are larger "
        "than their wins.",

    "Sample Size Requirements, Out-of-Sample Testing, and Forward Testing":
        "Per-trade results scatter enormously, so a handful of trades tells you almost "
        "nothing. A rough guide: a few hundred trades before an expectancy estimate "
        "means anything, and more when the edge is small. "
        "Two entries in this system's own top-15 rest on 34 and 46 trades and are "
        "explicitly labelled unproven for exactly this reason. Out-of-sample testing "
        "means holding data back; forward testing means paper trading before real "
        "money. Both exist because a strategy fitted to history will always look good "
        "on that history.",

    "Identifying and Eliminating Over-Fitting and Curve-Fitting Bias Errors":
        "Overfitting is tuning a strategy until it describes past noise rather than a "
        "repeatable effect. The tell is fragility: change a threshold slightly and the "
        "result collapses. "
        "The defence is to count how many configurations you tried. This system tested "
        "336 combinations, so a naive 95% significance threshold of t=1.96 is far too "
        "loose - a Bonferroni correction at that width requires t=3.79. Reporting the "
        "size of the search is not modesty, it is part of the result.",

    "Monte Carlo Risk Simulations: Evaluating System Ruin Probability Curves":
        "Monte Carlo reshuffles your trade sequence thousands of times to see what ELSE "
        "could have happened. The same set of trades in a different order produces very "
        "different drawdowns, and the worst of those orderings is the risk you actually "
        "carry. "
        "It answers the question a single equity curve cannot: what is the probability "
        "this system draws down 40% before it works? A strategy with positive "
        "expectancy can still ruin an account through sequence risk alone.",

    "Walk-Forward Optimization: Testing Strategy Adaptability across Changing Regimes":
        "Walk-forward fits parameters on one period and tests them on the next, rolling "
        "forward - so every result is out-of-sample. It answers whether an edge persists "
        "when the regime changes. "
        "This system splits history into four eras (2008-2011 crisis, 2012-2015 low-vol "
        "bull, 2016-2019 late bull, 2020-2021 COVID) and reports each separately. That "
        "is how it found that most strategies with a good blended number were positive "
        "in only one or two eras - and that gap continuation held up in all four.",

    "Out-of-Sample Validation: Protecting Against Historical Data Curve-Fitting":
        "Any parameter chosen by looking at data is contaminated by that data. "
        "Out-of-sample validation reserves a slice the fitting process never saw. "
        "The subtle version of the mistake is choosing the best of many exit policies "
        "and then reporting its statistics as if it were the only one tried. This "
        "system's reports state explicitly that each headline t-statistic is the best "
        "of 12 exit policies, and is therefore an upper bound rather than an estimate.",

    "Monte Carlo Testing: Evaluating Strategy Ruin Risks across 10,000 Simulations":
        "The same technique applied at scale: simulate thousands of possible futures "
        "using your measured win rate and payoff distribution, and count how many end in "
        "ruin at your chosen position size. "
        "The output that matters is not average return but the left tail. If 5% of "
        "simulations wipe the account, the strategy is unusable at that size regardless "
        "of its expectancy.",

    "Historical Black Swan Replications: Stress-Testing Portfolios against 1987, 2008, and 2020":
        "Replay the worst days on record through your current positions. October 1987 "
        "(-20% in a session), 2008 (sustained collapse with liquidity failure), March "
        "2020 (fastest 30% drawdown in history, with circuit breakers). "
        "For 0DTE the specific hazard is not just the move but the market breaking: "
        "spreads widen to unusable, fills disappear, and a 'defined risk' position "
        "cannot be closed at any price you would accept.",

    "Backtest Speed Optimization: Vectorized Execution Arrays vs. Event-Driven Simulators":
        "Vectorised backtests compute across whole arrays at once - fast, but they make "
        "path-dependent logic (trailing stops, one-position-at-a-time) awkward and easy "
        "to get subtly wrong. Event-driven simulators walk bar by bar, which is slower "
        "but models reality directly. "
        "This system is event-driven for that reason. Speed came from data access "
        "instead: replacing per-session queries with one sequential scan took a full "
        "sweep from an hour of I/O to 103 seconds without changing a single result.",

    "Slippage and Fee Modeling: Incorporating Dynamic Maker-Taker Exchange Frictions":
        "A backtest that fills at the mid-price is fiction. Real entries pay the ask and "
        "real exits receive the bid, and every round trip pays that spread plus "
        "commission. "
        "At the profit factors typical of intraday strategies - 1.05 to 1.30 - costs "
        "decide the outcome. This system's option model pays ask on entry, bid on exit "
        "and $0.65 per contract each way, and a bug that let the bid clamp at zero on "
        "cheap contracts (halving the effective spread) had to be fixed precisely "
        "because that is where 0DTE costs bite hardest.",

    "Survivorship Bias Resolution: Incorporating Bankrupt and De-listed Assets into Data Sheets":
        "If your dataset contains only companies that still exist, your backtest has "
        "quietly excluded every failure. Returns look far better than reality because "
        "the losers were deleted from history. "
        "Less of an issue for an index ETF like SPY, but the same logic applies to "
        "strategies: a library of strategies that only keeps the ones that worked is "
        "survivorship bias applied to your own research, which is why failed strategies "
        "here are reported rather than deleted.",

    "Multi-Asset Rebalancing Delays: Simulating Real-World Execution Latencies":
        "Signals are computed on a closed bar, orders take time to route, and fills "
        "arrive after that. A backtest that acts instantly on the closing price of the "
        "bar it is evaluating has stolen a tick. "
        "This system fills at the NEXT bar's open for that reason, and enforces it with "
        "a test: a signal at bar i must still be a signal when every bar after i is "
        "deleted, because live that is all that exists.",

    "Volatility-Adjusted Trailing Safety Envelopes (ATR_14)":
        "Average True Range over 14 periods measures typical movement, including gaps. "
        "Using it to set stops means your risk adapts to conditions instead of being a "
        "fixed dollar amount that is too tight in volatile markets and too loose in "
        "quiet ones. "
        "This system reports all underlying results in ATR multiples specifically so "
        "that 2008 and 2021 are comparable - a 2-point move meant something very "
        "different in each.",

    "Worst-Case Peak-to-Trough Account Fuse Boxes (Max_Drawdown_60d)":
        "Maximum drawdown is the largest fall from a peak to a subsequent trough. It is "
        "the number that decides whether a strategy is survivable, because it describes "
        "the worst stretch you must sit through. "
        "Two strategies with identical total profit are not equivalent if one got there "
        "with a 7-unit drawdown and the other with 21. The second requires either more "
        "capital or more tolerance than most people actually have.",

    "Risk-Adjusted Portfolio Variance Scorecards (Rolling_Sharpe_60d)":
        "Sharpe divides excess return by its standard deviation - return per unit of "
        "volatility. Rolling it over 60 days shows whether risk-adjusted performance is "
        "improving or decaying rather than giving one blended number for all time. "
        "Its weakness is treating upside and downside volatility identically, which "
        "penalises a strategy for making money quickly. Useful as a comparison across "
        "strategies, misleading as a target to optimise.",

    # ---------------------------------------------------------------
    # Trade planning and position sizing
    # ---------------------------------------------------------------
    "Establishing the Hard Rules of Your Strategy before the Market Opens":
        "Every decision made while a position is open is made under pressure by a "
        "person who wants to be right. Rules written beforehand are made by someone "
        "with no money at stake. "
        "This is why this system's strategies carry explicit entry conditions and "
        "explicit exits (+150%/-75%, or +40%/-40% with a 30-minute time stop) rather "
        "than discretion. The rules can be wrong and still beat improvisation, because "
        "a wrong rule is measurable and improvisation is not.",

    "Defining Your Checklist: What Must Happen before You Click Buy":
        "A checklist converts a strategy into a repeatable procedure: what regime, what "
        "signal, what contract, what size, what invalidates it. If any item fails, there "
        "is no trade. "
        "Its real function is preventing the trade you take because you are bored or "
        "behind. Automation is a checklist that cannot be talked out of itself.",

    "Setting Your Maximum Capital Allocations and Risk per Single Position":
        "Decide the most one position may cost you BEFORE choosing the position. A "
        "common rule is 1-2% of account per trade; this system uses a hard $500 cap and "
        "one open position per strategy. "
        "Sizing from a fixed risk budget rather than from conviction is what keeps a "
        "losing streak survivable. Conviction is highest exactly when it is least "
        "reliable.",

    "Writing Down an Exit Plan for Your Profit Target and Stop-Loss Levels":
        "Both exits must exist before entry. Without a target you hold winners until "
        "they reverse; without a stop you hold losers hoping. "
        "For 0DTE the exit is more decisive than the entry. This system's Phase 5 work "
        "found the same signal returning -$156k with a +/-50% exit and +$211k with a "
        "+200/-80 exit - identical entries, opposite outcomes, purely from exit "
        "geometry.",

    "Calculating the Risk-per-Trade (The Core R-Multiple Principle)":
        "R is the amount you risk on a trade. Every result is then measured in R: a "
        "trade that makes twice what it risked is +2R, one that stops out is -1R. "
        "Thinking in R makes results comparable across sizes and account balances, and "
        "makes expectancy directly interpretable - 'this system averages +0.3R' is a "
        "complete description of an edge.",

    "Position Sizing: How to Determine Exactly How Many Contracts to Buy":
        "Contracts = risk budget / (premium x 100). At a $500 cap and a $1.50 contract, "
        "that is 3 contracts risking $450. "
        "The mistake is sizing from what you can afford rather than what you are willing "
        "to lose. Because a long option can go to zero, the premium paid IS the risk - "
        "there is no stop that saves you from a gap through your strike.",

    "The Exponential Math of Drawdowns: Why Rebounding from a Loss Gets Harder":
        "Losses and gains are asymmetric. Down 10% needs +11.1% to recover; down 50% "
        "needs +100%; down 80% needs +400%. "
        "This is why capital preservation outranks return capture. Avoiding a single "
        "catastrophic loss contributes more to long-run growth than several good months, "
        "and it is the entire argument for position limits.",

    "The Win Rate vs. Risk-Reward Intersect: Why You Can Be Wrong and Still Profitable":
        "Break-even win rate = 1 / (1 + reward-to-risk). At 2:1 you need only 33%; at "
        "1:1 you need above 50%; at 1:2 you need 67%. "
        "This is exactly why symmetric exits fail on 0DTE. A +/-50% target and stop "
        "needs above a 50% win rate to break even, and theta plus spread push realised "
        "win rates to 38-45% - which is how a genuinely positive underlying edge turns "
        "into a losing option strategy.",

    # ---------------------------------------------------------------
    # Psychology
    # ---------------------------------------------------------------
    "Cognitive Biases: Overconfidence, Confirmation, and Anchoring Pitfalls":
        "Overconfidence inflates your estimate of your own skill, usually after a "
        "winning streak that was mostly variance. Confirmation bias makes you seek "
        "evidence for the position you already hold. Anchoring fixes your judgement to "
        "an irrelevant reference price. "
        "The countermeasure is written records made before the outcome is known. A "
        "journal entry written at entry cannot be revised by memory afterwards.",

    "Emotional Friction: Navigating FOMO (Fear of Missing Out) and Revenge Trading":
        "FOMO is entering because a move is happening rather than because your setup "
        "occurred - reliably the worst entry price of the move. Revenge trading is "
        "sizing up to recover a loss, which converts a bad trade into a bad week. "
        "Both are consequences of treating a missed opportunity as a loss. There will be "
        "another setup; there is not always another account.",

    "Risk Management Psychology: Mastering Risk-Aversion and Loss-Mitigation":
        "People are risk-averse over gains and risk-SEEKING over losses: happy to take a "
        "small certain profit, but willing to gamble to avoid booking a loss. That is "
        "precisely backwards for a trading system. "
        "It produces cut winners and held losers, which inverts the payoff distribution "
        "any positive-expectancy strategy depends on.",

    "Prospect Theory: The Asymmetric Psychology of Utility and Financial Loss":
        "Kahneman and Tversky's finding that a loss hurts roughly twice as much as an "
        "equivalent gain pleases, and that both are judged against a reference point "
        "rather than in absolute terms. "
        "For traders this explains why a break-even trade after being up feels like a "
        "loss, and why the reference point - your entry price - has no bearing on what "
        "the position is worth now.",

    "The Disposition Effect: Why Traders Sell Winners Early and Hold Losers Natively":
        "The measured tendency to realise gains quickly and defer losses, because "
        "closing a loser makes it real. The result is a portfolio of losers and a "
        "history of small wins. "
        "It is the direct mechanism by which the previous two biases destroy an edge, "
        "and the reason exits should be rule-based rather than felt.",

    "Preventing Revenge Trading after a Loss: Maintaining Discipline in Drawdowns":
        "The most dangerous moment is immediately after a loss, when the impulse is to "
        "trade bigger and sooner to get it back. "
        "Practical defences: a fixed maximum number of trades per day, a daily loss "
        "limit that stops trading entirely when hit, and a required pause after any "
        "stop-out. This system's one-position-per-strategy rule serves the same purpose "
        "mechanically.",

    "Keeping a Consistent Journal: Documenting the Rationale behind Every Position":
        "Record before the outcome: what signalled, why now, what invalidates it, what "
        "size and why. Afterwards record what actually happened. "
        "Without the pre-trade note, review becomes storytelling - memory reliably "
        "rewrites the reasoning to fit the result. The journal's value is entirely in "
        "the part written while the outcome is still unknown.",

    "Categorizing Errors: Separating Flawed Strategies from Emotional Execution Failures":
        "Two different problems need two different fixes. A strategy error means the "
        "rules were followed and lost - that is data. An execution error means the rules "
        "were not followed - that is discipline. "
        "Conflating them is expensive in both directions: abandoning a sound strategy "
        "after a run of losses you caused, or blaming yourself for a losing month that "
        "was ordinary variance.",

    "Tracking Statistics: Finding Your True Historical Win Rate and Profit Factor":
        "Your actual numbers, from your actual fills - not the backtest's. Measured per "
        "strategy, because a blended figure hides which one is carrying the others. "
        "That is why every strategy in this system has its own channel and its own "
        "ledger: an aggregate P/L cannot tell you which of fourteen rules is worth "
        "keeping.",

    "Reviewing Past Data to Continuously Refine Rules and Protect Capital":
        "Regular review with a fixed cadence and a fixed question: is each rule still "
        "performing as measured, and has anything decayed? "
        "The discipline is changing rules on evidence rather than on the last few "
        "trades. A strategy that is positive in 4 of 4 eras and negative this month is "
        "probably fine; one positive in 1 of 4 was never fine.",

    # ---------------------------------------------------------------
    # Accounts, margin and day-trading rules
    # ---------------------------------------------------------------
    "Pattern Day Trader (PDT) Classification Boundaries and Capital Limits":
        "In a US margin account, four or more day trades within five business days "
        "makes you a Pattern Day Trader, which requires maintaining $25,000 in equity. "
        "Fall below it and day trading is restricted until the balance is restored. "
        "This is the single rule that shapes how most retail traders can operate. A "
        "0DTE strategy is by definition day trading, so a sub-$25k margin account "
        "cannot run one. A cash account avoids the PDT rule entirely but introduces "
        "settlement: proceeds are unavailable until the trade settles, so the same "
        "capital cannot be reused the next day. Verify current rules with your broker - "
        "these change and brokers apply them differently.",

    "Reg T Margin Accounts vs. Cash Accounts for Options Execution":
        "A Reg T margin account allows borrowing and immediate reuse of proceeds, and "
        "is required for most spread strategies - but it carries the PDT rule. A cash "
        "account has no PDT restriction and no borrowing, but each sale must settle "
        "before those funds are usable again. "
        "For long options specifically, a cash account is workable: buying premium "
        "needs no margin. The constraint is capital velocity, not permission.",

    "Navigating Assignment Risk, Early Assignment, and Cash Settlement":
        "Assignment risk exists only for short positions. American-style contracts "
        "(SPY, equities) can be assigned any time, most commonly on in-the-money calls "
        "the day before an ex-dividend. European-style index contracts (SPX) cannot be "
        "assigned early and settle in cash, removing the risk entirely. "
        "That distinction is a real reason some traders prefer SPX over SPY for "
        "short-premium structures. For a long-only system it is moot - you cannot be "
        "assigned on something you bought.",

    "Managing Trades across Accounts to Ensure Compliant Reporting":
        "Wash sale rules apply across ALL of your accounts, including an IRA. Selling "
        "at a loss in a taxable account and repurchasing in an IRA within 30 days "
        "permanently disallows the loss - it is not merely deferred. "
        "Brokers report per account, so reconciliation across accounts is the trader's "
        "responsibility. Frequent traders in similar instruments accumulate these "
        "quickly. Educational information only; confirm treatment with a tax "
        "professional.",

    # ---------------------------------------------------------------
    # Tax structures
    # ---------------------------------------------------------------
    "Internal Revenue Code Section 1256 Contracts: 60/40 Tax Multipliers":
        "Section 1256 contracts - broad-based index options such as SPX, plus futures - "
        "receive 60/40 treatment in the US: 60% of gains taxed as long-term and 40% as "
        "short-term, regardless of holding period. They are also marked to market at "
        "year end. "
        "For an active trader this can be a materially lower effective rate than "
        "ordinary short-term treatment on ETF options like SPY, which do not qualify. "
        "It is one of the few reasons an SPX-based version of a SPY strategy might be "
        "worth the wider spreads. Educational only - verify with a tax professional.",

    "The Wash Sale Rule: Identifying and Preventing Disallowed Capital Losses":
        "Selling at a loss and buying a 'substantially identical' security within 30 "
        "days before or after disallows the loss for that year; the amount is added to "
        "the new position's cost basis instead. "
        "For active options traders this is a constant hazard - repeatedly trading the "
        "same underlying can generate large disallowed amounts, and in an extreme case "
        "a trader can owe tax on gains while holding real net losses. Section 1256 "
        "contracts are exempt, which is part of their appeal.",

    "Trader Tax Status (TTS) Requirements and Business Expense Deductions":
        "TTS is a facts-and-circumstances determination, not an election: substantial, "
        "frequent, continuous activity carried on as a business. Qualifying allows "
        "deducting trading expenses - data, software, home office - as business "
        "expenses. "
        "It does not by itself change how gains are taxed; that requires the separate "
        "475(f) election. The bar is higher than most part-time traders assume.",

    "Section 475(f) Mark-to-Market Election: Eliminating Wash Sale Rules":
        "An election available to traders with TTS. Positions are marked to market at "
        "year end, gains and losses become ordinary, wash sale rules no longer apply, "
        "and the $3,000 capital loss limitation is removed. "
        "The trade-off is losing long-term capital gains treatment entirely, and the "
        "election must generally be made before the tax year begins - it cannot be "
        "applied retroactively after a bad year.",

    "LLC Entity Creation: Operating Trading Operations as a Business Structure":
        "An LLC provides liability separation and a formal structure for expenses, but "
        "trading through one does not by itself change tax treatment - a single-member "
        "LLC is disregarded by default. "
        "It is administrative structure, not a tax strategy. The costs (formation, "
        "filings, separate books) are real and should be weighed against benefits that "
        "are often smaller than advertised.",

    "S-Corporation Election: Optimizing Self-Employment and Salary Tax Dividends":
        "An S-corp election can reduce self-employment tax by splitting income between "
        "a reasonable salary and distributions. It is a genuine strategy for trading "
        "businesses with substantial income. "
        "But trading gains are generally not self-employment income to begin with, so "
        "the benefit is narrower than for a typical operating business - it usually "
        "applies to management or advisory income rather than to the trading profits "
        "themselves.",

    "Offshore and Trust Asset Protections: Safeguarding Compounding Trading Wealth":
        "Offshore structures and trusts are asset-protection and estate-planning tools. "
        "For US persons they generally do NOT reduce tax liability - worldwide income "
        "is taxable and foreign accounts carry heavy reporting obligations (FBAR, "
        "FATCA) with severe penalties for non-compliance. "
        "Anything marketed primarily as offshore tax avoidance for a US trader should "
        "be treated as a warning sign rather than an opportunity.",

    # ---------------------------------------------------------------
    # Prop firms
    # ---------------------------------------------------------------
    "Proprietary Trading Models: Evaluation Stages and Profit-Split Milestones":
        "Modern retail prop firms sell an evaluation: pay a fee, hit a profit target "
        "without breaching drawdown rules, and receive a funded account with a profit "
        "split, commonly 70-90% to the trader. "
        "The economics deserve scrutiny. Many firms earn primarily from evaluation fees "
        "rather than trader profits, which means the rules are calibrated so most "
        "participants fail. It is a real route to capital, but the pass rate - not the "
        "advertised split - is the number that matters.",

    "Trailing Drawdown Rules: Navigating Relative vs. Absolute Capital Loss Caps":
        "An absolute drawdown is measured from the starting balance; a trailing "
        "drawdown follows your high-water mark upward. Under a trailing rule, profit "
        "raises the level at which you are disqualified. "
        "This is where most funded accounts are lost. Up 4% then back to break-even can "
        "breach a 3% trailing limit despite the account never being down. Read whether "
        "the trail is on closed balance or intraday equity - the difference decides "
        "whether an open drawdown can end your account before you close it.",

    "Scaling Plans: Automatically Expanding Position Sizing via Profit Accrual":
        "A schedule granting larger size as the account grows - for example, size "
        "increases at each 10% profit milestone. "
        "Sound in principle, since risk stays proportional to capital. The hazard is "
        "psychological: size increases arrive after winning streaks, which is exactly "
        "when overconfidence peaks and when variance is most likely to mean-revert.",

    "Institutional Risk Auditing: Tracking Consistency Scores and Sharpe Thresholds":
        "Funded programmes and institutions evaluate HOW returns were earned, not just "
        "how much. Consistency rules cap the share of profit from any single day, so "
        "one lucky trade cannot pass an evaluation. "
        "The intent is to distinguish process from variance - the same reason this "
        "system reports per-era results rather than one blended number.",

    # ---------------------------------------------------------------
    # Calendar anomalies
    # ---------------------------------------------------------------
    "The Turn-of-the-Month Effect: Tracking Institutional Capital Inflows":
        "A documented tendency for equity returns to concentrate around the last day "
        "and first few days of a month, attributed to salary flows, retirement "
        "contributions and fund rebalancing. "
        "Treat with the same scepticism as any calendar effect: it is a small edge, "
        "widely known, and measured against SPY's unconditional 20-day win rate of "
        "64.5% it may be no edge at all. A raw win rate that ignores the base rate is "
        "the most common way calendar anomalies are oversold.",

    "Options Expiration (OpEx) Week Anomalies: Max Pain Strike Reversion":
        "Max pain is the strike where the largest total value of options expires "
        "worthless. Price sometimes gravitates toward it into expiry, plausibly through "
        "dealer hedging rather than manipulation - see the dealer gamma channel. "
        "The effect is weak, inconsistent, and easy to see in hindsight. It is better "
        "used as context for why price may stall near a heavily-traded strike than as "
        "a signal to trade.",

    "Quarter-End Window Dressing: Institutional Portfolio Rebalancing Loops":
        "The tendency for funds to buy recent winners and sell losers before quarterly "
        "reporting, so holdings look better than the decisions that produced them. "
        "It concentrates flow into the last days of a quarter and can extend momentum "
        "in already-strong names, then reverse in the first days of the new quarter.",

    "The Santa Claus Rally and January Effect: Tax-Loss Harvesting Cycles":
        "The Santa Claus Rally covers the last five sessions of December plus the first "
        "two of January; the January Effect is the historical tendency for small caps "
        "to outperform early in the year, linked to December tax-loss selling reversing. "
        "Both have weakened substantially since being widely publicised - a recurring "
        "pattern with calendar anomalies, and a reason to test rather than assume.",

    # ---------------------------------------------------------------
    # Portfolio construction
    # ---------------------------------------------------------------
    "Modern Portfolio Theory (MPT): Efficient Frontier Optimization Models":
        "Markowitz's framework: for any target return there is a portfolio with minimum "
        "variance, and the set of those portfolios forms the efficient frontier. "
        "Diversification works because assets are imperfectly correlated. "
        "Its weakness is that it needs expected returns, volatilities and correlations "
        "as inputs, and all three are estimated from history. Correlations in "
        "particular converge toward 1 during crises - exactly when diversification is "
        "supposed to help.",

    "The Black-Litterman Model: Blending Market Equilibrium with Trader Views":
        "Starts from the returns implied by current market weights - the market's own "
        "consensus - and adjusts only where you hold an explicit view, weighted by your "
        "confidence in it. "
        "It fixes MPT's tendency to produce extreme allocations from noisy return "
        "estimates: with no views you get the market portfolio, and deviations are "
        "deliberate rather than artefacts of estimation error.",

    "Risk Parity Allocation Frameworks: Equalizing Volatility Contributions":
        "Allocate so each asset contributes equally to portfolio RISK rather than "
        "equally to capital. Low-volatility assets get larger weights, often with "
        "leverage applied to the whole portfolio. "
        "It performed well through a decades-long bond bull market and struggles when "
        "stocks and bonds fall together, since the approach assumes a diversification "
        "benefit that a correlated selloff removes.",

    "Factor Investing Matrix Overlays: Value, Momentum, Quality, and Size Tilts":
        "Systematic tilts toward characteristics with documented long-run premia: cheap "
        "valuations, recent relative strength, profitability and stability, smaller "
        "capitalisation. "
        "Factors go through long periods of underperformance - value lagged for over a "
        "decade - so they demand a horizon most traders do not have. Momentum is the "
        "one that most closely resembles what intraday systems exploit, on a far "
        "shorter timescale.",
}


def authored_body(title: str) -> str | None:
    """The written explanation for a topic, if one exists yet."""
    return AUTHORED_BODIES.get(title)


def coverage() -> dict[str, int]:
    return {"authored": len(AUTHORED_BODIES)}
