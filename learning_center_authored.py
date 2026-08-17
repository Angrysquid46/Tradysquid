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

    # ---------------------------------------------------------------
    # Hedging and synthetics
    # ---------------------------------------------------------------
    "Covered Calls: Liquidating Short Upside Premium Against Core Underlying Stock":
        "Own 100 shares, sell a call against them. You collect premium and keep gains "
        "up to the strike; above it your shares are called away. "
        "It is often sold as 'income', which understates the trade. You have exchanged "
        "an unlimited upside for a fixed payment while keeping the entire downside - "
        "the risk profile of a short put. It works in flat-to-mildly-up markets and "
        "costs you exactly the move you were waiting for when the stock finally runs.",

    "Protective Puts: Establishing Institutional Tail-Risk Capital Insurance Policies":
        "Own the stock, buy a put. Downside is capped below the strike, upside is "
        "intact, and the premium is the cost of the insurance. "
        "Like all insurance it is a persistent drag: buy protection continuously and "
        "premium costs will exceed payouts across most periods, because that is how "
        "the seller makes money. Protection is worth buying around identifiable risk, "
        "not as a permanent subscription.",

    "The Collar Strategy: Financing Downside Puts via Short Out-of-the-Money Calls":
        "Own stock, buy a protective put, sell a call above to pay for it - sometimes "
        "for zero net cost. Downside is floored, upside is capped. "
        "The favourite structure of anyone holding a large concentrated position they "
        "cannot sell for tax reasons. The honest description is that you have "
        "converted a stock position into a range, and you should want the stock to "
        "finish inside it.",

    "Stock Repair Strategies: Using Spreads to Recover Trapped Capital without Adding Risk":
        "Holding a loser, add a ratio call spread - buy one at-the-money call, sell two "
        "further out - usually for near-zero cost. It roughly doubles gains up to the "
        "short strike, letting you break even on a smaller bounce. "
        "It does not reduce your existing loss and it caps the recovery. The real "
        "question it dodges is whether you would open this position today at this "
        "price; 'repairing' is often anchoring wearing a strategy's clothes.",

    "Put-Call Parity: The Core Mathematical Rule of Derivatives Pricing":
        "For European options: C - P = S - K x e^(-rt). A call minus a put at the same "
        "strike and expiry equals the stock minus the discounted strike. "
        "This is the equation that makes options a coherent system rather than "
        "independent bets. It means any position can be built several ways, and if "
        "prices drift apart arbitrageurs close the gap. When you see a put far richer "
        "than its call, you are usually looking at skew and dividends, not free money.",

    "Synthetic Long Stock: Combining Long Calls and Short Puts to Mimic Shares":
        "Buy a call and sell a put at the same strike and expiry, and you have "
        "replicated 100 shares: the same payoff in both directions, for far less "
        "capital. "
        "The leverage is the point and the danger. Downside is identical to owning the "
        "stock, but the capital committed is a fraction, so the loss relative to money "
        "posted is much larger. It is stock exposure without the feeling of owning "
        "stock.",

    "Synthetic Short Stock: Combining Long Puts and Short Calls to Mimic Short Selling":
        "Buy a put, sell a call at the same strike. Replicates a short position without "
        "borrowing shares, which matters when a stock is hard to borrow or the borrow "
        "fee is punitive. "
        "The short call carries unlimited risk and assignment exposure, exactly as a "
        "real short does. Nothing about the synthetic form makes the risk smaller - it "
        "only changes where the risk is booked.",

    "Conversion and Reversal Arbitrage: Risk-Free Exploitations of Mispriced Spreads":
        "A conversion is long stock plus a synthetic short; a reversal is the inverse. "
        "When put-call parity is violated these lock a small riskless profit. "
        "In practice they are market-maker trades: the edges are pennies, they require "
        "minimal transaction costs and instant execution, and for retail the spread "
        "consumes the profit before the position is complete. Their real value here is "
        "conceptual - they are why parity holds.",

    "Dynamic Delta Hedging: Calculating Real-Time Portfolio Share Rebalancing":
        "Holding a position delta-neutral by trading shares against the option's "
        "changing delta. Sell shares as delta rises, buy as it falls. "
        "This is what market makers do continuously, and it is the mechanism behind "
        "dealer gamma effects: their hedging is forced, mechanical flow that either "
        "damps or amplifies price depending on whether they are long or short gamma.",

    "Gamma Scalping: Trading Stock Around Short-Term Options Positions":
        "Long an option and therefore long gamma, you re-hedge repeatedly - buying low "
        "and selling high mechanically as delta shifts. The profits from those hedges "
        "are meant to exceed the theta you pay. "
        "It is a bet that realised volatility will exceed implied. It requires "
        "frequent, cheap execution, and it is precisely the trade that dies from "
        "transaction costs at retail size.",

    "Vanna and Volga Risk Multipliers: Implied Volatility and Spot Price Intersects":
        "Second-order Greeks. Vanna is how delta changes when volatility changes; volga "
        "is how vega changes when volatility changes. "
        "They explain why hedges that look right at one volatility level fail at "
        "another - the sensitivities themselves move. Relevant to anyone running a "
        "book; largely academic for a single long 0DTE contract, where gamma dominates "
        "everything.",

    "Tail-Risk Hedging: Executing Low-Probability Out-of-the-Money Option Insurances":
        "Buying far out-of-the-money puts as protection against a crash. Most expire "
        "worthless; the rare payoff is enormous. "
        "The difficulty is that the strategy bleeds continuously and the drag is felt "
        "every month while the benefit arrives once a decade - so it tends to be "
        "abandoned shortly before it would have paid. Sizing it as a small permanent "
        "cost rather than a trade is the only way it survives contact with impatience.",

    "Variance Swaps vs. Volatility Swaps: Exploiting Pure Implied Variance Returns":
        "Instruments paying the difference between realised and implied volatility "
        "directly, without the delta and path-dependence of an options position. "
        "Variance swaps pay on variance (volatility squared), which makes them convex - "
        "large moves pay disproportionately. Volatility swaps are linear. Institutional "
        "instruments, but the concept matters: they are the clean expression of the "
        "bet that options only express approximately.",

    "VIX Options Pricing: Navigating Volatility of Volatility Surges Natively":
        "VIX options are priced off VIX FUTURES, not the spot index - which is why a "
        "VIX spike does not move them the way traders expect. The futures curve moves "
        "far less than spot. "
        "They also settle in cash, European-style, on an unusual Wednesday cycle. More "
        "retail money has been lost to these mechanics than to being wrong about "
        "volatility direction.",

    "Log-Contract Replications: The Mathematical Foundation of the VIX Index Engine":
        "The VIX is not a forecast in the usual sense; it is computed from a strip of "
        "SPX option prices that replicates a log contract, giving the market-implied "
        "expected variance over the next 30 days. "
        "Knowing it is a derived calculation rather than an opinion explains its "
        "behaviour: it rises mechanically when option prices rise, and its level is "
        "constrained by the same put-call relationships everything else obeys.",

    "Vanna-Volga Pricing Modifiers: Formulating Advanced Exotic Strike Corrections":
        "A practical method for pricing exotics by adjusting a Black-Scholes value "
        "using the market cost of hedging vega, vanna and volga - widely used in FX "
        "options where the smile is pronounced. "
        "It is a correction technique rather than a model, and it exists because "
        "Black-Scholes assumes one volatility while the market quotes a different one "
        "at every strike.",

    # ---------------------------------------------------------------
    # Fixed income and commodities
    # ---------------------------------------------------------------
    "Bond Pricing Foundations: Inverse Pricing-to-Yield Vector Rules":
        "Bond prices and yields move in opposite directions by definition: a fixed "
        "coupon becomes worth less when prevailing rates rise. Duration measures how "
        "much - a 7-year duration bond loses roughly 7% per 1% rate rise. "
        "For an equity trader this is the transmission mechanism. Rate moves reprice "
        "bonds instantly, and equity valuations follow because the discount rate on "
        "future earnings has changed.",

    "The Treasury Yield Curve: Fed Funds Rate, 2-Year, and 10-Year Notes":
        "Yields plotted across maturities. The Fed sets the very short end directly; "
        "the 2-year reflects rate expectations over the policy horizon; the 10-year "
        "reflects longer-run growth and inflation expectations. "
        "The curve is the market's aggregated forecast of policy. Watching the 2-year "
        "is usually more informative about what the Fed will do than listening to what "
        "the Fed says.",

    "Yield Curve Inversions and Macro Recessionary Filtering Signals":
        "Inversion - short yields above long - has preceded every US recession in "
        "recent decades, and is a genuine signal that the market expects rates to fall "
        "because growth is weakening. "
        "Its practical weakness is timing: the lag from inversion to recession has run "
        "from 6 to 24 months, and equities have often risen substantially during that "
        "window. A real signal on a horizon no day trader can act on.",

    "Currency Cross-Rates: The US Dollar Index (DXY) vs. Equity Assets":
        "DXY measures the dollar against a basket of major currencies. A strong dollar "
        "pressures US multinationals (foreign earnings translate to fewer dollars), "
        "commodities priced in dollars, and emerging markets holding dollar debt. "
        "The relationship is real but unstable - it inverts across regimes, which makes "
        "it context rather than a signal.",

    "Crude Oil, Natural Gas, and Energy Sector Capital Dependencies":
        "Energy prices feed directly into inflation and into corporate margins as an "
        "input cost. Oil shocks have historically preceded recessions. "
        "Natural gas is more regional and weather-driven than oil, and is far more "
        "volatile as a result - it is not a substitute for crude as a macro read.",

    "Gold and Silver: Safe-Haven Precious Metal Inflows vs. Risk Assets":
        "Gold usually strengthens when real interest rates fall or confidence in "
        "currencies weakens - it pays no yield, so its opportunity cost is the real "
        "rate. Silver behaves partly as an industrial metal and is more volatile. "
        "The 'safe haven' label holds in some crises and fails in others: in an acute "
        "liquidity event gold is often sold precisely because it CAN be sold.",

    "Copper and Agricultural Futures: Real Economy Demand Radar Systems":
        "Copper is used across construction, electronics and grid infrastructure, which "
        "is why it is nicknamed a leading indicator of industrial demand. Agricultural "
        "futures respond to weather and geopolitics more than to the business cycle. "
        "Neither is a trading signal for SPY intraday, but copper's trend is a useful "
        "check on whether a growth narrative is supported by physical demand.",

    "The Commodity Research Bureau (CRB) Continuous Index Tracker":
        "A broad basket index of commodity prices, used as a single read on commodity "
        "inflation rather than any one market's idiosyncrasies. "
        "Useful as a regime marker: sustained CRB strength alongside rising yields is a "
        "different environment for equities than commodity weakness with falling "
        "yields, regardless of where the index level sits.",

    "Physical Storage Arbitrage: Cost of Carry and Financial Futures Convergence":
        "A futures price should equal spot plus the cost of carrying the commodity - "
        "storage, insurance and financing. If it exceeds that, buy physical, store it, "
        "and sell the future for a locked profit. "
        "This arbitrage is what forces futures to converge to spot at expiry, and it is "
        "why term structure carries real information about physical supply rather than "
        "just sentiment.",

    "Super-Contango Regimes: Exploiting Floating Storage Maritime Arbitrage Plays":
        "Contango is futures above spot. When the gap exceeds storage costs - "
        "super-contango - traders buy physical oil, charter tankers as floating "
        "storage, and sell forward. This happened dramatically in 2020, when land "
        "storage filled and front-month crude briefly traded negative. "
        "It is the clearest example that a futures price is a claim on a physical thing "
        "that must be somewhere.",

    "Backwardation Injections: Evaluating Physical Inventory Shortfalls on Ticker Spikes":
        "Backwardation is futures BELOW spot - buyers paying a premium for immediate "
        "delivery, which signals genuine physical scarcity. "
        "For anyone holding a commodity ETF this determines roll yield: backwardation "
        "pays you to roll forward, contango charges you. It is why long-dated holdings "
        "in contangoed commodity ETFs decay regardless of the commodity's direction.",

    "The Crack Spread and Crush Spread: Processing Raw Materials into Final Deliverables":
        "The crack spread is the margin between crude oil and the refined products made "
        "from it; the crush spread is soybeans versus meal and oil. Both are traded "
        "directly as a bet on processing margins. "
        "They are pure examples of a spread trade: the directional price risk is netted "
        "out and what remains is the economics of the transformation itself.",

    # ---------------------------------------------------------------
    # Orders and execution
    # ---------------------------------------------------------------
    "Defining Market Orders vs. Limit Orders and Avoiding Entry Slippage":
        "A market order guarantees execution but not price; a limit order guarantees "
        "price but not execution. That single trade-off governs every fill you will "
        "ever get. "
        "On a liquid SPY option a market order is usually fine. On anything with a wide "
        "spread it is how you hand away 5-10% of the position instantly. The working "
        "rule: limit orders by default, market orders only when getting out matters "
        "more than the price you get out at - which on a 0DTE approaching the close is "
        "genuinely sometimes true.",

    "Inside Bid-Ask Spreads, Market Orders, and Limit Order Ingestion":
        "The inside spread is the best bid and best ask currently displayed. Buying at "
        "the ask and selling at the bid means you pay the spread on every round trip, "
        "before commission. "
        "That cost is the reason this system's option model always fills entries at the "
        "ask and exits at the bid rather than at the mid. Mid-price fills in a backtest "
        "are how a strategy invents money it never earned.",

    "Conditional Order Routing (Stop-Market, Stop-Limit, Trailing Stops)":
        "A stop-market becomes a market order when triggered - it will fill, possibly "
        "far from your stop price in a fast move. A stop-limit becomes a limit order - "
        "it protects your price and may not fill at all, leaving you in the position "
        "you were trying to exit. A trailing stop follows price by a set distance. "
        "Neither is safe in every case, and choosing wrongly is worse in a crash than "
        "having no stop: stop-limits are the ones that fail to fill exactly when you "
        "need them.",

    "Immediate-or-Cancel (IOC), Fill-or-Kill (FOK), and Good-Til-Canceled (GTC)":
        "IOC fills whatever is available immediately and cancels the rest. FOK requires "
        "the entire order to fill at once or nothing. GTC persists across sessions "
        "until filled or cancelled. "
        "GTC is the one that catches people: an order you forgot about can fill days "
        "later on a spike into a position you no longer want. Most brokers expire them "
        "after 30-90 days, which is a limit, not a safety feature.",

    "Scaling Into and Out of Positions without Impacting the Active Price":
        "Splitting a large order into smaller pieces so you do not exhaust the "
        "available liquidity and move the price against yourself. "
        "At retail size in SPY this is rarely necessary; in a thin option chain it is "
        "essential. The tell you needed it is a fill that is materially worse than the "
        "quote you clicked.",

    "How Illiquid Order Books and Wide Spreads Quietly Steal Pennies from Beginners":
        "On an illiquid contract the spread can be 20-50% of the price. Buy and "
        "immediately sell and you have lost that much with no price movement at all. "
        "This is the mechanical reason cheap far-out-of-the-money options are worse "
        "than they look, and why this system enforces a liquidity check plus a "
        "0.40-0.60 delta band rather than simply capping the dollar cost.",

    "The Bid-Ask Matrix: Knowing Who Is Buying the Floor and Who Is Selling the Ceiling":
        "The bid is what buyers will pay; the ask is what sellers will accept. Sizes at "
        "each show how much conviction sits at those prices. "
        "Displayed size is only part of the truth - hidden and iceberg orders mean the "
        "book shows less than exists. Reading the book as a complete picture of supply "
        "and demand is a reliable way to be faded.",

    "Level 1 Data (Top of Book) vs. Level 2 Data (Order Book Depth)":
        "Level 1 is the best bid, best ask and last trade. Level 2 shows resting orders "
        "at multiple price levels. "
        "Level 2 is genuinely useful in slow markets and genuinely misleading in fast "
        "ones, where displayed orders are pulled faster than a human can react. The "
        "depth you are watching may not exist by the time your order arrives.",

    "Time and Sales (The Tape): Decoding Real-Time Transaction Logs":
        "Every actual execution, with price, size and time. Unlike the order book it "
        "shows what happened rather than what was advertised. "
        "The useful read is trades printing at the ask (buyers lifting offers) versus "
        "at the bid (sellers hitting bids), and unusual size. This system's relative "
        "volume feature is a systematised version of the same question.",

    "Order Book Imbalances: Bid-Ask Net Order Flow Analytics":
        "Measuring whether resting size and executed volume lean to the buy or sell "
        "side. Sustained imbalance often precedes short-term direction. "
        "It decays fast, is easily spoofed by orders never intended to fill, and works "
        "best as confirmation of a level rather than as a standalone trigger.",

    "Identifying Block Trades, Iceberg Orders, and Hidden Algo Footprints":
        "Blocks are large negotiated trades, often printed away from the lit market. "
        "Icebergs display a small quantity while holding much more behind it. "
        "The recognisable footprint is repeated identical-size prints at one price - a "
        "large order being worked. It tells you a level is defended; it does not tell "
        "you the defender is right.",

    "Retail Brokers, Clearing Firms, and Payment for Order Flow (PFOF)":
        "Most zero-commission brokers sell retail orders to wholesalers, who execute "
        "them internally and pay the broker for the flow. Retail orders are attractive "
        "because they are uninformed relative to institutional flow. "
        "Execution is often at or slightly better than the displayed quote, so 'free' "
        "is not simply a lie - but the cost is invisible and unmeasurable to you, which "
        "is a different thing from being zero.",

    "Dark Pools, Internalizers, and Lit Public Exchange Order Routing":
        "Lit exchanges display orders publicly. Dark pools match large orders without "
        "pre-trade transparency, so institutions can trade size without showing their "
        "hand. Internalizers fill retail orders in-house. "
        "The consequence for a chart reader is that a meaningful share of volume never "
        "appears on the tape until after it executes - so 'no volume at this level' is "
        "not proof that nothing happened there.",

    "Lit Exchanges (NYSE/NASDAQ) vs. Dark Pools (Alternative Trading Systems)":
        "The same distinction from the venue side. ATSs are regulated but not required "
        "to display quotes, and typically execute at the midpoint of the public spread. "
        "Roughly 40%+ of US equity volume trades off-exchange. Any analysis assuming "
        "the lit book represents the whole market is working from a partial picture.",

    "Reg NMS Rule 611 (Order Protection Rule): The Mandated Public Market Intersection":
        "Trade-through protection: an order may not execute at a worse price than the "
        "best displayed quote on another exchange. It is what makes the fragmented US "
        "market behave as one. "
        "It also created the need for smart order routing and much of modern HFT - the "
        "rule requires checking every venue, and the fastest checker wins.",

    "Direct Market Access (DMA) vs. Retail Payment for Order Flow (PFOF)":
        "DMA sends your order straight to an exchange of your choosing, with visible "
        "fees and rebates. PFOF routes it to a wholesaler. "
        "DMA gives control and measurability; PFOF gives zero commission and price "
        "improvement you cannot audit. For a strategy sensitive to a penny per share, "
        "control is worth paying for.",

    "Maker-Taker Fee Models: Rebate Optimization across Execution Venues":
        "Venues pay a rebate for adding liquidity (resting limit orders) and charge a "
        "fee for taking it (marketable orders). Fractions of a cent per share. "
        "Irrelevant at retail size, decisive for high-frequency strategies - and it "
        "shapes routing decisions that ultimately determine where your order goes.",

    "Smart Order Routers (SOR): How Algos Shred and Distribute Order Blocks":
        "Software that splits an order across venues to get the best aggregate fill, "
        "accounting for displayed size, fees and expected impact. "
        "It is why a single large order appears on the tape as many small prints across "
        "several exchanges within milliseconds.",

    "Volume-Weighted Average Price Execution Loops (Algorithmic Ingestion)":
        "A VWAP algorithm works an order through the day in proportion to expected "
        "volume, aiming to finish near the day's volume-weighted average price. "
        "This is why VWAP is a meaningful level rather than an arbitrary line: large "
        "institutional orders are explicitly benchmarked against it, so it attracts "
        "real flow. That is the basis for this system's VWAP-anchored strategies.",

    "Time-Weighted Average Price Block Distribution Engines":
        "TWAP spreads an order evenly across time rather than across volume - simpler, "
        "and preferable when volume forecasts are unreliable. "
        "It leaves a recognisable footprint: regular same-size prints at fixed "
        "intervals regardless of activity.",

    "Percentage-of-Volume (POV) Slicers: Hiding Institutional Transactions Natively":
        "Participates at a fixed share of market volume - trade more when the market is "
        "active, less when it is quiet - so the order hides inside natural flow. "
        "The trade-off is that completion time is unknown: in a quiet session the order "
        "may not finish at all.",

    "Minimum-Quantity, Discretionary, and Pegged Order Microstructure Codes":
        "Conditional instructions attached to orders. Minimum-quantity refuses partial "
        "fills below a size; discretionary orders show one price while willing to "
        "execute at another; pegged orders float with the bid, ask or midpoint. "
        "Mostly institutional plumbing, but pegged orders in particular explain "
        "liquidity that appears to move with price rather than sitting still.",

    "Alternative Trading Systems (ATS): Tracking Institutional Tier Block Crosses":
        "Registered venues matching orders outside the exchanges. FINRA publishes "
        "weekly ATS volume, so off-exchange activity can be tracked, just with a lag. "
        "A sustained rise in off-exchange share is a signal about institutional "
        "positioning that the lit tape does not show.",

    "Wholesaler Internalization: Payment for Order Flow (PFOF) Order Ingestion Routing":
        "A handful of wholesalers execute a large share of US retail orders against "
        "their own inventory, capturing the spread and offering slight price "
        "improvement. "
        "It concentrates enormous flow information in very few firms - the structural "
        "criticism of PFOF, distinct from whether any individual fill was fair.",

    "Continuous Crossing vs. Midpoint Match Execution Venue Frictions":
        "Continuous markets match orders as they arrive; crossing networks match "
        "periodically at a reference price, usually the midpoint. "
        "Midpoint execution splits the spread between both sides, which is why "
        "institutions favour it for size - and why some liquidity is only available if "
        "you are willing to wait for a cross.",

    # ---------------------------------------------------------------
    # Gaps and oscillators
    # ---------------------------------------------------------------
    "Common Gaps, Breakaway Gaps, Runaway Gaps, and Exhaustion Gaps":
        "Common gaps occur in quiet ranges and usually fill. Breakaway gaps start a new "
        "trend out of a base and often do not. Runaway gaps appear mid-trend and "
        "confirm it. Exhaustion gaps come at the end of an extended move and reverse "
        "sharply. "
        "The classification is only reliable after the fact, which limits its use as a "
        "signal. What survives testing is the measurable version: gap SIZE and "
        "direction, which is what this system's gap-continuation strategy uses.",

    "The Mechanics of Opening Gaps and Overnight Order Re-Matching":
        "A gap is the difference between today's open and yesterday's close, created by "
        "overnight news and orders accumulating against a closed book. The opening "
        "auction resolves them all at one clearing price. "
        "This system measures gap in dollars, percent and ATR multiples, because the "
        "same half-point gap means something different in a calm market than in a "
        "volatile one. Gap continuation at 0.5% was the strongest edge found across "
        "3,347 sessions - t=+3.33, positive in all four eras.",

    "Relative Strength Index (RSI): Evaluating Overbought/Oversold Overextensions":
        "RSI compares average gains to average losses over 14 periods, scaled 0-100. "
        "Above 70 is conventionally overbought, below 30 oversold. "
        "The standard mistake is treating those as reversal signals. In a strong trend "
        "RSI stays above 70 for extended periods, and every short taken on that basis "
        "loses. It is far more reliable as a divergence tool - price making a new high "
        "while RSI does not - than as a level.",

    "Moving Average Convergence Divergence (MACD): Signal Line Cross-Overs":
        "MACD is the 12-period EMA minus the 26-period EMA; the signal line is a "
        "9-period EMA of that; the histogram is the difference. Crossovers indicate "
        "momentum shifts. "
        "It lags by construction - it is built from moving averages of moving averages "
        "- so it confirms rather than predicts. This system's expansion strategy used "
        "MACD histogram colour across three timeframes, and measured at -0.0044 "
        "ATR/trade, which is a fair illustration of the limits of crossover logic.",

    "Stochastic Oscillator: Tracking Fast and Slow Closing Placements":
        "Measures where the close sits within the recent high-low range: 80+ means "
        "closing near the top of the range, 20- near the bottom. %K is the raw line, "
        "%D its smoothed average. "
        "More sensitive than RSI, which means more signals and more false ones. Its "
        "genuine use is spotting where closes cluster within a range, which is the same "
        "question this system's `range_position` feature answers per bar.",

    "Commodity Channel Index (CCI) and Williams %R Oscillator Ingestion":
        "CCI measures deviation from a moving average scaled by mean deviation, "
        "unbounded, with ±100 as conventional thresholds. Williams %R is stochastics "
        "inverted onto a -100 to 0 scale. "
        "Both measure essentially the same thing as RSI and stochastics with different "
        "arithmetic. Stacking several is not confirmation - they are correlated by "
        "construction and will agree with each other while all being wrong together.",

    "Bollinger Bands: Standard Deviation Volatility Envelope Widths":
        "A 20-period moving average with bands at ±2 standard deviations. Bands widen "
        "as volatility rises and contract as it falls. "
        "Touching a band is not a signal - in a trend price rides the upper band for a "
        "long time. The informative part is WIDTH: a squeeze (unusually narrow bands) "
        "precedes expansion, which is the basis of compression-breakout strategies.",

    "Keltner Channels: Average True Range (ATR) Envelope Boundaries":
        "Similar to Bollinger Bands but built from ATR rather than standard deviation, "
        "which makes them smoother and less prone to whipsaw. "
        "Because ATR includes gaps, Keltner channels handle overnight moves more "
        "sensibly than standard deviation of closes.",

    "Keltner Channels vs. Bollinger Bands: Measuring Volatility Squeezes":
        "The classic squeeze indicator: when Bollinger Bands contract INSIDE the "
        "Keltner channels, volatility is unusually low relative to its own recent "
        "range, and expansion often follows. "
        "It signals that a move is likely, not which direction - which is why it pairs "
        "with a directional trigger rather than standing alone.",

    "Donchian Channels: High-Low Range Breakout Tracking Matrices":
        "The highest high and lowest low over N periods. A close outside them is a "
        "breakout - the original Turtle Traders rule. "
        "Its virtue is that it has no parameters beyond the lookback and no smoothing "
        "to lag behind price. This system's opening-range logic is a session-scoped "
        "Donchian channel.",

    "Moving Average Envelopes and Percentage Band Filters":
        "Bands drawn a fixed percentage above and below a moving average. Simpler than "
        "Bollinger or Keltner, and unresponsive to volatility - the band is the same "
        "width in a calm market as in a crisis. "
        "That fixed width is the flaw: the same percentage is far too wide on one day "
        "and far too tight on another.",

    "Ichimoku Kinko Hyo: Tenkan-Sen, Kijun-Sen, and Cloud Equilibrium":
        "A complete system in one overlay: two averages of range midpoints (Tenkan 9, "
        "Kijun 26), a projected cloud showing future support and resistance, and a "
        "lagging line. Price above the cloud is bullish, below bearish. "
        "The cloud's genuine contribution is being projected forward, which gives "
        "levels before price reaches them. The cost is visual complexity that "
        "encourages seeing whatever you already believe.",

    "Parabolic SAR: Systematic Stop-and-Reverse Directional Wave Gauges":
        "Dots that trail price and accelerate toward it, flipping sides when touched. "
        "Designed as an always-in-the-market stop-and-reverse system. "
        "Excellent in a sustained trend and disastrous in a range, where it flips "
        "repeatedly and loses on every flip. It is a trailing-stop mechanism more than "
        "an entry signal.",

    "Linear Regression Channels: Standard Deviation Trend Variance Channels":
        "A best-fit line through price over a window, with parallel bands at standard "
        "deviation intervals. It defines a trend's slope and how far price typically "
        "strays from it. "
        "More statistically grounded than a hand-drawn trendline, and it makes the "
        "trend's slope explicit - which is the difference between 'uptrend' as an "
        "opinion and as a measurement.",

    # ---------------------------------------------------------------
    # Volatility surface
    # ---------------------------------------------------------------
    "Historical Realized Volatility vs. Forward-Looking Implied Volatility (IV)":
        "Realised volatility is what price ACTUALLY did, measured from past returns. "
        "Implied volatility is what the option market expects, backed out of current "
        "premiums. They are different quantities and routinely disagree. "
        "The gap between them is the trade. Buying options is a bet realised will "
        "exceed implied; selling is the reverse. This system's option model takes IV "
        "from the real chain and prices from there - the IV is real data, the resulting "
        "premium is modelled.",

    "The Theoretical Baseline: Demystifying the Black-Scholes-Merton Pricing Model":
        "Prices an option from five inputs: spot, strike, time, rate and volatility. "
        "Four are observable; volatility is not, which is why quoting 'implied' "
        "volatility means solving the formula backwards from the market price. "
        "Its assumptions are all wrong - constant volatility, no jumps, lognormal "
        "returns - and it remains the universal language anyway, because everyone "
        "agrees to speak in its terms. This system uses it, validated against real "
        "1DTE quotes at a median error of -8.2% with 87% within 25%: good enough to "
        "rank strategies, not good enough to quote a market.",

    "Modern Real-World Variations: The Binomial Options Pricing Framework":
        "Models price as a tree of discrete up/down steps, valuing the option backwards "
        "from expiry. Slower than Black-Scholes but it handles EARLY EXERCISE, which "
        "closed-form solutions cannot. "
        "That makes it the correct tool for American-style options like SPY, where the "
        "right to exercise early has real value near dividends.",

    "Implied Volatility Percentile (IVP) vs. Implied Volatility Rank (IVR)":
        "IV Rank places current IV between its 52-week low and high: (IV - low) / "
        "(high - low). IV Percentile is the share of days in the past year IV was "
        "LOWER than today. "
        "They diverge when the year contained one spike: a single crisis inflates the "
        "high, so rank reads low while percentile correctly reports that IV is elevated "
        "relative to most days. Percentile is the more robust of the two.",

    "The Volatility Risk Premium (VRP): Why Options Are Systematically Overpriced":
        "Implied volatility exceeds subsequent realised volatility most of the time - "
        "buyers pay a premium for protection, sellers are compensated for carrying the "
        "risk. That persistent gap is the VRP. "
        "It is the structural reason option SELLING wins most months and loses "
        "catastrophically in the rest. It is also the headwind every long-premium "
        "strategy, including this one, trades against: you are paying an insurance "
        "premium and need the move to be worth more than it.",

    "Understanding the Implied Volatility Smile: Out-of-the-Money Tail Risk Pricing":
        "Plot IV against strike and it curves upward at both ends rather than sitting "
        "flat - out-of-the-money options in both directions carry higher implied "
        "volatility than at-the-money. "
        "This exists because real returns have fatter tails than the lognormal "
        "assumption. The smile is the market correcting Black-Scholes for a known flaw "
        "in its own assumptions.",

    "Understanding the Implied Volatility Skew: Equity Puts vs. Commodities Calls":
        "In equity indices the curve is a lopsided SKEW rather than a symmetric smile: "
        "downside puts carry much higher IV than equidistant calls, because crashes are "
        "faster and more feared than rallies. Commodities often skew the other way, "
        "since supply shocks spike prices upward. "
        "Practically: SPY puts are structurally more expensive than equivalent calls. "
        "You are always buying downside protection at a worse price.",

    "Mapping the Three-Dimensional Volatility Surface Matrix":
        "IV plotted across both strike and expiry simultaneously - skew in one "
        "dimension, term structure in the other. The surface is the complete statement "
        "of how the market prices risk. "
        "Distortions in it are information: a bulge at one expiry usually marks a known "
        "event date, and a steepening skew marks rising demand for protection before "
        "price has moved.",

    "Volatility Term Structure: Navigating Contango vs. Backwardation Regimes":
        "Normally longer-dated options carry higher IV than short-dated - contango, "
        "reflecting greater uncertainty further out. In stress this inverts: near-term "
        "IV spikes above long-term, which is backwardation. "
        "Inversion is one of the more reliable stress signals available, because it "
        "means the market is pricing danger NOW rather than someday. For 0DTE it "
        "directly inflates the premium you must pay.",

    # ---------------------------------------------------------------
    # Dealer gamma
    # ---------------------------------------------------------------
    "Estimated Net Dealer Gamma Exposure Thresholds (GEX)":
        "GEX estimates the aggregate gamma dealers hold across the option chain. When "
        "dealers are net LONG gamma they hedge against the move - selling rallies, "
        "buying dips - which damps volatility. When net SHORT they hedge WITH the move, "
        "amplifying it. "
        "The zero-gamma level is the flip point, and it is the single most useful "
        "number from this framework: above it expect mean reversion, below it expect "
        "trend and acceleration. Estimates vary by provider because dealer positioning "
        "is inferred, not published.",

    "Intraday Volatility Buffering via Positive Gamma Anchors":
        "In a positive-gamma regime, dealer hedging mechanically opposes price. Rallies "
        "meet selling, dips meet buying, and the market grinds in a range. "
        "This is why some sessions refuse to trend despite news - the flow is "
        "structurally mean-reverting. It is the environment where breakout strategies "
        "fail repeatedly and fade strategies work.",

    "Intraday Volatility Acceleration via Negative Gamma Cascades":
        "In negative gamma, hedging runs WITH price: dealers sell as it falls and buy "
        "as it rises, feeding the move. Small imbalances become large ones. "
        "This is the mechanism behind sessions that go one way all day, and behind "
        "crash dynamics generally. It is the environment where a 0DTE directional trade "
        "pays best - and where fading is most dangerous.",

    "The Mechanics of Delta-Neutral Dealer Re-Hedging Profiles":
        "A dealer who sells you a call is short delta and must buy stock to neutralise "
        "it. As price moves, the required hedge changes, forcing continuous trading "
        "that is mechanical rather than opinionated. "
        "Understanding this reframes 'the market did X' as often just hedging flow. It "
        "is not manipulation and it is not a view - it is an obligation being "
        "discharged.",

    "Option Strike Pinning and Expiration Gamma Clustered Volume":
        "Price tends to gravitate toward strikes with very large open interest into "
        "expiry, because dealer hedging around those strikes is self-correcting - "
        "buying below and selling above. "
        "The effect is real but weak and easy to over-read. It matters most on large "
        "monthly expirations, and far less on a single daily expiry where open interest "
        "is thinner.",

    "Pin Risk Optimization: Hedging At-The-Money Contracts at Friday 3:59 PM EST":
        "In the final minutes, an at-the-money contract's outcome is genuinely "
        "uncertain - assigned or not, depending on the last print. Dealers hedge this "
        "aggressively, which itself concentrates volume at the strike. "
        "The retail lesson is simply not to be there: close near-the-money positions "
        "before the bell rather than gambling on which side the close lands. This "
        "system forces flat at 15:45 for exactly that reason.",

    "At-The-Money Implied Volatility Straddle Matrix":
        "The ATM straddle price is the market's direct quote for the expected move: "
        "roughly, call + put at the money is what the market thinks the underlying will "
        "travel by expiry. "
        "It is the cleanest read available on expected magnitude - and the number any "
        "long-premium trade must beat to be worth taking.",

    "Out-of-the-Money Implied Volatility Smile Wings":
        "The far ends of the smile, where IV rises steeply. Wings price tail risk, and "
        "they are where the largest gaps between implied and realised volatility "
        "usually sit. "
        "It is why far-OTM options are persistently expensive relative to how often "
        "they pay, and why buying them systematically is a slow bleed.",

    "Intermarket Volatility Cross-Correlations (VIX vs. VVIX)":
        "VIX measures expected S&P volatility; VVIX measures expected volatility OF "
        "VIX. High VVIX with low VIX means the market is calm but pricing the "
        "possibility of a sudden shift. "
        "That combination is one of the more useful early warnings available, because "
        "it appears before VIX itself moves.",

    "Volatility Skew Term Structure Contango vs. Backwardation":
        "Skew and term structure interact: skew steepness varies by expiry, so "
        "protection can be cheap in one tenor and expensive in another. "
        "Near-dated skew steepens fastest in stress, which is precisely when short-"
        "dated downside protection becomes most expensive - the insurance reprices as "
        "you reach for it.",

    "Bid-Ask Inventory Management: Skewing Pricing Sheets to Force Retail Order Flow":
        "Market makers do not quote symmetrically around fair value. Holding too much "
        "of one side, they skew quotes to attract the offsetting flow - making it "
        "slightly cheaper to trade in the direction that reduces their risk. "
        "So the quoted mid is not necessarily fair value; it is fair value adjusted for "
        "someone else's inventory problem.",

    "Adverse Selection Risks: How Toxic Institutional Order Flow Burns Option Dealers":
        "Dealers profit from uninformed flow and lose to informed flow. Order flow that "
        "systematically knows something is 'toxic', and dealers respond by widening "
        "spreads or refusing to quote size. "
        "This is why retail flow is valuable enough to pay for, and why spreads widen "
        "immediately before major announcements - the dealer cannot tell who is "
        "informed, so charges everyone.",

    "Inter-Exchange Arbitrage: High-Frequency Sweep Models Aligning Fragmented Options Order Books":
        "US options trade across many exchanges. When prices drift apart, "
        "high-frequency firms arbitrage the difference within microseconds, which is "
        "what keeps the fragmented market coherent. "
        "For anyone slower, the practical consequence is that visible cross-exchange "
        "discrepancies are already gone by the time a human sees them.",

    # ---------------------------------------------------------------
    # Expiration mechanics
    # ---------------------------------------------------------------
    "Cash Settlement vs. Physical Delivery: Index Options (SPX/NDX) vs. Equity Options (SPY/QQQ)":
        "SPX and NDX settle in CASH: the difference is paid, no shares change hands, "
        "and there is no assignment risk. SPY and QQQ deliver actual shares. "
        "This is a meaningful practical difference. An unclosed in-the-money SPY call "
        "leaves you holding roughly $77,500 of stock; the SPX equivalent simply pays "
        "cash. Combined with Section 1256 tax treatment, it is why many serious 0DTE "
        "traders prefer SPX despite wider spreads.",

    "Understanding American-Style Options vs. European-Style Options Contract Rules":
        "American-style can be exercised any time before expiry; European-style only at "
        "expiry. US equity and ETF options are American; index options like SPX are "
        "European. "
        "The distinction only matters if you are SHORT - it determines whether you can "
        "be assigned early. It is also why a box spread is genuinely riskless in "
        "European-style contracts and dangerous in American-style ones.",

    "Introduction to Binary Options, Barrier Options, and Exotic Derivatives Structures":
        "Binaries pay a fixed amount if a condition is met, nothing otherwise. Barrier "
        "options activate or extinguish when price touches a level. Both are exotics "
        "with discontinuous payoffs. "
        "Retail 'binary options' platforms are largely unregulated and structured so the "
        "house holds the edge - closer to a betting product than to a derivatives "
        "market. Legitimate exotics trade institutionally, over the counter.",

    "Special Cash Dividends: Structural Adjustments to Options Strike Matrices":
        "Ordinary dividends do not adjust option contracts; special dividends above a "
        "threshold (typically 12.5% of share price) do - strikes are reduced by the "
        "dividend amount. "
        "The trap is assuming an adjustment where none occurs. An ordinary dividend "
        "still drops the share price on the ex-date, and option holders absorb that "
        "with no compensating change to the strike.",

    "Spin-offs and Carve-outs: Managing Deliverable Basket Options Changes":
        "When a company spins off a division, existing options are adjusted to deliver "
        "a BASKET - shares of both entities - rather than 100 shares of one. "
        "Adjusted contracts become illiquid, quote poorly, and are easy to misprice. "
        "Generally best exited before the corporate action rather than held through it.",

    "Rights Offerings and Warrants: Evaluating Synthetic Dilution Vectors":
        "A rights offering lets existing holders buy new shares at a discount; warrants "
        "are long-dated call-like instruments issued by the company itself. Both dilute "
        "existing shareholders when exercised. "
        "Unlike exchange-traded options, warrants create NEW shares - so the dilution is "
        "real rather than a transfer between traders.",

    "Tender Offers and Stock Buyback Mechanics: The Impact on Floating Liquidity":
        "A tender offer bids for shares at a premium, usually to acquire control. "
        "Buybacks reduce shares outstanding, mechanically raising earnings per share "
        "without any improvement in the business. "
        "Both shrink the tradeable float, which reduces liquidity and can amplify "
        "subsequent volatility - fewer shares available means each order moves price "
        "more.",
}


def authored_body(title: str) -> str | None:
    """The written explanation for a topic, if one exists yet."""
    return AUTHORED_BODIES.get(title)


def coverage() -> dict[str, int]:
    return {"authored": len(AUTHORED_BODIES)}
