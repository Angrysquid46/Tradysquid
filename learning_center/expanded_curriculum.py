"""Owner-requested Phase 16 depth remediation.

The first Phase 16 pass reduced many source topics to a mention or omitted them.
This module adds original, human-facing lessons for those gaps while preserving
the stable IDs of already-published lessons.  Every supplement teaches four
things: mechanics, a decision process, a worked application, and failure/risk
management.  It is educational content only and is isolated from both traders.
"""

from __future__ import annotations

from dataclasses import dataclass

from learning_center_publish import Lesson, Section


@dataclass(frozen=True)
class Supplement:
    title: str
    topics: tuple[str, ...]
    mechanics: str
    decision: str
    example: str
    risks: str


def _lesson(chapter: int, number: int, spec: Supplement) -> Lesson:
    """Build a remediation lesson with its immediate study prerequisite."""
    return Lesson(
        lesson_number=number,
        title=spec.title,
        topics=spec.topics,
        keywords=spec.topics,
        related_concepts=(f"LC-{chapter:02d}-{number - 1:02d}",),
        sections=(
            Section("Mechanics and purpose", spec.mechanics),
            Section("Selection and decision process", spec.decision),
            Section("Worked application", spec.example),
            Section("Risks, follow-up, and common mistakes", spec.risks),
        ),
    )


def supplement_lessons(chapter: int, first_number: int) -> list[Lesson]:
    return [
        _lesson(chapter, first_number + offset, spec)
        for offset, spec in enumerate(SUPPLEMENTS.get(chapter, ()))
    ]


SUPPLEMENTS: dict[int, tuple[Supplement, ...]] = {
    1: (
        Supplement(
            "Option Prices, Markets, Symbols, and Orders",
            ("factors influencing option price", "option markets", "option symbology", "details of option trading", "order entry"),
            "An option quote is produced in a two-sided auction. Underlying price, strike, time remaining, expected volatility, rates, dividends, exercise style, and supply and demand jointly shape premium. The standardized symbol identifies underlying, expiration, call or put, and strike; it is the final identity check, not decoration.",
            "Before an order, verify the full symbol, action (buy/sell), effect (open/close), quantity, order type, limit, time in force, and whether the displayed bid and ask are fresh. Prefer a patient limit order inside a liquid market; use a multi-leg net limit for a spread so one leg is not left naked.",
            "If a call is quoted 2.10 by 2.30, a 2.20 limit represents $220 per standard contract. A fill is not guaranteed. Replacing the order at 2.25 changes the maximum debit to $225; a market order gives up that price boundary and may fill outside the displayed spread.",
            "Last price and midpoint are not executable promises. Wide spreads, stale trades, halts, complex-order legging, incorrect open/close flags, and symbols with the wrong expiration or strike are common causes of avoidable loss. Cancel or replace deliberately and confirm the final fill before managing the position.",
        ),
        Supplement(
            "Profit Graphs and Position Payoffs",
            ("profits and profit graphs",),
            "A payoff graph places underlying price on the horizontal axis and position profit or loss on the vertical axis at a stated time, usually expiration. Kinks occur at strikes. Premium shifts the graph away from the raw exercise payoff, while pre-expiration value also depends on time and volatility.",
            "Mark maximum profit, maximum loss, every breakeven, and the slope in each price region. Then ask what changes before expiration: theta, implied volatility, dividends, early assignment, and execution costs can make the live P&L differ materially from the expiration diagram.",
            "A 100-strike call bought for 4 has expiration P&L `max(S-100,0)-4`, or $400 maximum loss per contract and a 104 breakeven. At S=112 the gain is 8 points, or $800. Before expiration the option can still trade above intrinsic value because time remains.",
            "A graph can conceal path dependence, early assignment, margin calls, slippage, and inability to exit. Never infer probability from the width or visual attractiveness of a payoff region, and never compare diagrams without using the same date and cost assumptions.",
        ),
    ),
    2: (
        Supplement(
            "Covered-Write Return, Execution, and Underlying Selection",
            ("total return concept of covered writing", "computing return on investment", "execution of the covered write order", "selecting a covered writing position", "writing against stock already owned"),
            "Covered-call return has two components: option premium and stock gain or loss. Return-on-capital must use a declared denominator—share cost, net debit, or broker buying power—and a declared time period. A buy-write opens both legs together; writing against owned stock opens only the call and may change the tax lot ultimately delivered.",
            "Select liquid, optionable shares the trader is genuinely willing to hold and sell at the strike. Compare call yield, upside to strike, downside breakeven, days held, dividend and earnings dates, spread quality, assignment exposure, concentration, and the annualization assumptions rather than ranking by premium alone.",
            "Buy 100 shares at 50 and sell a 55 call for 2. Net debit is 48. If assigned at 55, profit is 7 points and return on net debit is 7/48=14.58% before fees and tax. If stock closes at 40, the position loses 8 points; the 2-point premium did not create downside protection beyond the new 48 breakeven.",
            "Do not annualize a short sample as if it repeats safely, ignore the stock loss because premium was collected, or overwrite tax and assignment consequences. Use a net limit for a buy-write, define whether shares may be called away, and recalculate return after every roll as a new trade.",
        ),
        Supplement(
            "Covered-Call Portfolio Management and Partial Extraction",
            ("diversifying return and protection in a covered write", "follow-up action", "partial extraction strategy", "special writing situations"),
            "Diversification means controlling correlated stock exposure, expiration clustering, sector concentration, and event risk—not merely holding several tickers. Partial extraction sells calls on only part of a share position, preserving some uncapped upside while monetizing another portion.",
            "At each review choose among hold, buy back, roll out, roll up, roll down, permit assignment, or close both legs. Base the choice on the current combined-position value and revised thesis, not the original premium. Treat ex-dividend dates, earnings, takeovers, splits, hard-to-borrow conditions, and deep ITM calls as special situations requiring explicit review.",
            "With 300 shares, selling two calls covers 200 shares and leaves 100 shares uncapped. If the stock rallies sharply, two lots may be assigned while one participates fully. If it falls, premium protects only by the amount collected and all 300 shares retain downside exposure.",
            "Repeated tiny premiums can mask a large equity drawdown. Rolling for a credit can extend exposure and increase opportunity cost. Verify contract adjustments after corporate actions and never sell more calls than the shares intentionally committed unless naked-call risk is separately approved and understood.",
        ),
    ),
    3: (
        Supplement(
            "Advanced Call Selection, Ranking, and Follow-Up",
            ("advanced selection criteria", "ranking prospective call purchases", "follow-up action", "comment on spreads"),
            "Call candidates should be ranked on thesis fit rather than cheapness: delta and gamma for directional sensitivity, theta per day, vega and event IV, spread as a percentage of premium, volume/open interest, DTE, distance to invalidation and target, and total premium at risk.",
            "Estimate the option outcome under several underlying prices, dates, and IV levels. Reject contracts whose target outcome does not overcome spread and decay. After entry, follow the prewritten price invalidation, time stop, event policy, profit-taking plan, and liquidity rule; do not wait for expiration merely because risk is defined.",
            "Two calls may both cost $2: a near-dated OTM call with 0.20 delta and an ITM call with 0.70 delta. For a modest expected move, the higher-delta contract may retain more value, while the cheap OTM contract can expire worthless. A debit spread may reduce cost and vega but caps profit at the short strike.",
            "Ranking by percent upside alone systematically favors lottery contracts. Buying after IV expansion, choosing an expiration shorter than the thesis, and converting a loser into an unplanned spread are process errors. Any spread comparison must include capped upside, short-leg assignment, and execution risk.",
        ),
    ),
    4: (
        Supplement(
            "Synthetic Put, Reverse Hedge, and Portfolio Margin",
            ("protected short sale or synthetic put", "portfolio margin", "synthetic straddle reverse hedge", "altering the ratio of long calls to short stock"),
            "Short stock plus a long call creates a protected short with a floor-like bearish payoff and capped upside loss; by put-call parity it is economically related to a long put after financing and dividends. A reverse hedge changes call-to-short-share ratios to reshape delta and convexity. Portfolio margin estimates scenario risk across the account rather than granting permission to ignore gross exposure.",
            "Choose the call strike and DTE from the maximum acceptable short-stock loss and hedge horizon. Measure net delta for the chosen ratio, stress large gaps, check borrow cost and dividend liability, and compare the synthetic with simply buying a put. Margin treatment must be confirmed with the actual broker because offsets and house requirements vary.",
            "Short 100 shares at 50 and buy one 55 call for 2. Above 55, the call offsets further stock losses; the approximate maximum loss is 7 points plus costs. Buying two calls creates net positive convexity above the strike, while buying only half the needed coverage leaves part of the short uncapped.",
            "Synthetic equivalence is not identical cash flow: rates, dividends, early exercise, borrow availability, spreads, and tax treatment differ. A margin reduction is not a reduction in economic loss. Recalculate ratios after stock movement because option delta changes continuously.",
        ),
    ),
    5: (
        Supplement(
            "Naked-Call Capital, Philosophy, and Follow-Up",
            ("investment required", "philosophy of selling naked options", "follow-up action"),
            "An uncovered call receives a finite credit while accepting theoretically unlimited upside loss. Required capital is a broker formula and can expand as price or volatility rises; the economically relevant capital is the loss the account can survive under severe stress, not merely today's displayed margin.",
            "Use only when the bearish/neutral thesis, liquidity, event calendar, borrow and assignment effects, and account-level stress limits are explicit. Predefine buy-to-close, roll, or conversion to a spread; compare the same view with a bear call spread before accepting unlimited exposure.",
            "Sell a 105 call for 2. Maximum profit is $200 and breakeven is 107. At stock 130, expiration loss is 23 points or $2,300. A broker that initially requires $1,500 may demand more during the rally, forcing closure before the thesis can recover.",
            "A stop order cannot cap a gap, and doubling down increases convex loss. Earnings, takeovers, hard-to-borrow stock, thin options, and short squeezes are hostile. Follow-up must be based on total account stress and executable buyback prices, not hope that time decay will eventually win.",
        ),
    ),
    6: (
        Supplement(
            "Ratio-Write Selection, Variable Ratios, and Management",
            ("investment required", "selection criteria", "variable ratio write synthetic short strangle", "follow-up action"),
            "A ratio call write owns shares and sells more calls than the shares cover; the excess calls create naked upside risk. A variable ratio changes strike quantities, and some combinations resemble a synthetic short strangle with losses outside a central range.",
            "Calculate covered and uncovered contracts separately, both breakevens, broker margin under stress, and the ratio's changing net delta. Select strikes only after stating the expected range and maximum tolerable breakout. Management choices include reducing naked calls, buying an upper-wing call, rolling, or closing the entire package.",
            "Long 100 shares and short two 55 calls leaves one call uncovered. If net premium lowers cost basis to 47, downside resembles stock below the lower breakeven while upside loss begins beyond the upper breakeven because two short calls outrun 100 shares.",
            "The maximum initial credit is not the maximum profit in every ratio design, and the apparent flat zone can be narrow. Volatility expansion and an upside gap can increase both loss and margin. Never describe the whole position as covered when any short contract lacks share coverage.",
        ),
    ),
    7: (
        Supplement(
            "Bull-Spread Aggressiveness, Ranking, and Follow-Up",
            ("degrees of aggressiveness", "ranking bull spreads", "follow-up action", "other uses of bull spreads"),
            "A bull call spread becomes more aggressive as strikes move farther OTM, width changes, or expiration shortens: debit may fall, but probability and delta also fall. ITM spreads cost more and behave more like stock. Bull spreads can express a target, reduce long-call cost, define event risk, or replace stock temporarily.",
            "Rank candidates using debit, width, maximum profit, maximum loss, breakeven, reward/risk, delta, distance from spot, target capture, DTE, liquidity, and probability assumptions. Follow-up choices are hold, close, roll, take partial value, or remove the short leg only when the newly naked long call is independently justified.",
            "A 100/105 spread for 2 risks $200 to make $300; a 105/110 spread for 0.75 risks $75 to make $425 but needs a larger move. The second has better nominal reward/risk and usually lower probability. Ranking must incorporate the thesis distribution, not reward/risk alone.",
            "Near expiration, a spread near the short strike has pin and assignment risk. Legging out can turn defined risk into open directional exposure. Do not hold a nearly max-valued spread for a few remaining dollars when exercise, assignment, and liquidity risk dominate.",
        ),
    ),
    8: (
        Supplement(
            "Selecting and Managing Bear Call Spreads",
            ("selecting a bear spread", "follow-up action"),
            "A bear call spread sells a lower-strike call and buys a higher-strike call, receiving a credit and defining upside loss. Strike placement determines probability, credit, maximum loss, delta, and distance to invalidation.",
            "Select candidates by comparing credit to width, breakeven versus resistance, short-leg delta, event exposure, liquidity, DTE, and account risk. Manage using the underlying invalidation and spread price; choices include closing, rolling both legs together, or taking profit after sufficient credit has decayed.",
            "Sell the 105/110 call spread for 1.20. Maximum profit is $120, maximum loss is $380, and breakeven is 106.20. If the thesis fails at 105 while time remains, closing may preserve more capital than waiting for the full $380 expiration loss.",
            "A high probability of profit can conceal poor loss severity. Never roll only the short call and leave the hedge behind unintentionally. Assignment of the short leg can create stock exposure even though the expiration diagram was defined-risk.",
        ),
    ),
    9: (
        Supplement(
            "Neutral, Bullish, and Multi-Expiration Calendars",
            ("neutral calendar spread", "bullish calendar spread", "using all three expiration series", "follow-up action"),
            "A neutral calendar uses the same strike and sells nearer expiration while buying farther expiration, seeking front-month decay near the strike. A bullish calendar shifts the strike above spot or uses diagonality to combine positive delta with the time spread. Three-series structures stagger short expirations against a longer option.",
            "Choose strike from the expected price at the first expiration, then compare front/back IV, term structure, theta, vega, event placement, and liquidity. Manage when price leaves the profitable tent, volatility relationships reverse, the short option approaches assignment, or the front expiration arrives.",
            "With stock 100, sell a 30-day 105 call and buy a 60-day 105 call. The position is bullish relative to a 100-strike calendar because its peak is shifted upward. Adding a 15-day short requires explicit quantity accounting; it is not free extra decay and can create overlapping short obligations.",
            "Maximum profit is not known exactly in advance because the back option's value at front expiration depends on IV. Early assignment, ex-dividend dates, and closing one leg independently can change risk. Do not treat every calendar as neutral or assume positive theta in every price/volatility state.",
        ),
    ),
    10: (
        Supplement(
            "Butterfly Selection and Follow-Up",
            ("selecting the spread", "follow-up action"),
            "A butterfly concentrates payoff around the body strike. Selection requires choosing direction, body location, wing width, debit/credit, expiration, and whether the structure is call-, put-, iron-, or broken-wing based.",
            "Place the body near the forecast expiration price, not automatically ATM today. Compare width, debit, probability of reaching the tent, liquidity of all legs, and the amount of profit sacrificed for wider wings. Follow-up uses price relative to the tent, remaining time, and attainable exit value.",
            "A 95/100/105 long call butterfly entered for 1 risks $100 and can be worth $500 at stock 100 at expiration, for $400 maximum profit. At 95 or 105 it expires worthless. Before expiration, profit is usually much smaller than the diagram's peak.",
            "The maximum-profit point is narrow and difficult to capture. Four-leg slippage can dominate a cheap debit. Near expiration, assignment and pin risk around the body can create unwanted shares; close the package when operational risk exceeds remaining reward.",
        ),
    ),
    11: (
        Supplement(
            "Ratio-Spread Philosophies and Follow-Up",
            ("differing philosophies", "follow-up action"),
            "A call ratio spread can be entered as an income trade expecting price near the short strikes, a financed directional trade, or a volatility structure. Those philosophies are not interchangeable because each implies different strike placement, acceptable tail risk, and exit behavior.",
            "State whether the goal is peak payoff, low-cost upside, or short-volatility carry. Compute the upper breakeven and stress moves far above it. Follow-up may remove excess shorts, buy a disaster wing, roll the ratio, or close before gamma makes adjustment expensive.",
            "Buy one 100 call and sell two 105 calls for near zero cost. The position benefits up to 105, then gives gains back and eventually loses above the upper breakeven. Adding a 115 call converts the naked tail into a defined-risk broken-wing structure.",
            "Calling a zero-cost position riskless is false. Upside acceleration, volatility expansion, and margin escalation can overwhelm the initial credit. An adjustment made after the stock crosses the short strike is often more expensive than protection purchased at entry.",
        ),
    ),
    12: (
        Supplement(
            "Choosing and Managing Delta-Neutral Ratio Calendars",
            ("choosing the spread", "follow-up action", "delta-neutral calendar spreads"),
            "A ratio calendar combines unequal contract quantities across expirations. Delta-neutral construction selects quantities whose starting deltas offset, while theta and vega remain intentionally exposed. Neutrality is a snapshot, not a permanent property.",
            "Choose expirations from the catalyst and term structure, strikes from the forecast range, and ratios from actual position Greeks. Establish rebalance bands before entry. Follow up when delta breaches its band, front gamma accelerates, IV term structure changes, or a short leg nears exercise risk.",
            "If a back-month call has 0.60 delta and each front-month short has 0.30 delta, one long versus two shorts begins near zero delta. A price move changes all three deltas at different rates, so the position may quickly become directional despite its neutral start.",
            "Greek estimates depend on model inputs and market quality. Frequent rehedging creates cost and can turn a theoretical edge negative. Never increase short quantity merely to display zero delta without stress-testing the resulting gamma and tail exposure.",
        ),
    ),
    13: (
        Supplement(
            "Reverse Calendar Spreads",
            ("reverse calendar spread",),
            "A reverse calendar buys the nearer-expiration option and sells the farther-expiration option at the same or related strike. It reverses the usual calendar's time exposure: commonly negative theta and negative vega, with substantial risk from the longer-dated short after the front option disappears.",
            "Use only when the near-term move or front IV is expected to outperform the back month enough to cover decay, spread, and the later short obligation. Compare event placement, term structure, exercise style, margin, and the plan for closing the back option.",
            "Buy a 20-day 100 call and sell a 60-day 100 call. A sharp immediate move can favor the front call, but after day 20 the long protection ends while the 60-day short remains. The trade must normally be closed as a package before that exposure is created.",
            "The initial debit or credit does not reveal maximum risk. Assignment, different volatility responses, and an uncovered back-month option are central hazards. This is not merely a calendar entered in the opposite order; it requires a distinct exit plan.",
        ),
    ),
    14: (
        Supplement(
            "Diagonal Bull Spreads, Free Calls, and Diagonal Backspreads",
            ("diagonal bull spread", "owning a call for free", "diagonal backspreads"),
            "A diagonal varies both strike and expiration. A bullish diagonal typically owns a longer-dated lower-strike call and sells a nearer higher-strike call. Repeated short-call credits may recover the original debit—informally called owning the call for free—but prior risk and realized losses do not vanish. A diagonal backspread adds more long deferred calls than near shorts.",
            "Select the long option for durable thesis exposure and the short option for a realistic near-term ceiling. Track cumulative net cash flow, remaining basis, net delta/theta/vega, event dates, and assignment. A diagonal backspread additionally requires tail and term-structure stress tests.",
            "Pay 8 for a six-month 95 call and sell monthly 105 calls for credits of 1.50, 1.20, and 1.30. Net unrecovered debit becomes 4, not zero. Even after total credits reach 8, the sequence had capital at risk and adverse moves or buybacks may have produced losses.",
            "Never call a recovered basis riskless: the long call can fall, short calls can be assigned, and rolls can consume prior credits. Expiration mismatch means an expiration payoff graph is insufficient; model each short-expiration decision separately.",
        ),
    ),
    15: (
        Supplement(
            "Put Pricing, Dividends, Exercise, and Conversion",
            ("pricing put options", "effect of dividends on put option premiums", "exercise and assignment", "conversion"),
            "Put value responds to stock price, strike, time, implied volatility, rates, and expected dividends. All else equal, a larger expected dividend tends to support put value because the stock is expected to drop by the distribution. Exercise transfers shares at the strike; assignment imposes the matching obligation on a writer. A conversion combines long stock, long put, and short call at one strike/expiration to lock a bond-like payoff.",
            "Compare market premium with intrinsic value and model inputs, then inspect ex-dividend timing and exercise style. For conversions, calculate every cash flow—stock, option premiums, dividends, financing, fees, and expiration proceeds—before calling a discrepancy arbitrage.",
            "Stock at 100, buy the 100 put for 4 and sell the 100 call for 4 while owning shares. At expiration the package delivers approximately 100 whether stock is above or below strike. Profit depends on the initial net cost and carrying cash flows, not on direction.",
            "American puts can be exercised early, especially when deep ITM and carrying value dominates remaining time. Quotes may be stale and apparent conversion profit can disappear after spreads, borrow, dividends, and financing. Assignment is operationally real even when positions are economically offset.",
        ),
    ),
    16: (
        Supplement(
            "Ranking Put Purchases and Managing the Position",
            ("ranking prospective put purchases", "follow-up action", "loss-limiting actions", "equivalent positions"),
            "Put candidates differ in delta, gamma, theta, vega, DTE, moneyness, liquidity, and event exposure. Equivalent bearish positions—long put, short stock plus protective call, or bear put spread—may express similar direction with different capital, tail, volatility, and execution profiles.",
            "Rank contracts using scenario P&L at target price/date/IV, premium at risk, spread percentage, theta budget, desired delta, and exit liquidity. Predefine underlying invalidation, option-price stop, time stop, event decision, profit plan, and whether a spread is preferable.",
            "A 100 put for 3 has a 97 expiration breakeven. At stock 90 it earns 7 points; at 100 it loses the $300 premium. A 100/90 bear put spread for 2 lowers cost to $200 but caps expiration value at 10, so maximum profit is $800.",
            "A put can lose while stock falls if the fall is too small, late, or accompanied by IV collapse. Averaging down extends risk rather than limiting it. Equivalent expiration payoffs can have different path, assignment, borrow, margin, and tax behavior.",
        ),
    ),
    17: (
        Supplement(
            "Choosing Protective Puts and Managing Collars",
            ("which put to buy", "tax considerations", "put buying as protection for the covered call writer", "no-cost collars", "adjusting the collar"),
            "Protective-put selection trades insurance cost against floor location and duration. A collar adds a short call to help finance the put, capping upside; a nominal no-cost collar uses call credit near the put debit but still has opportunity cost, spreads, tax, and assignment consequences. Covered-call shares can be collared to define both tails.",
            "Choose the put strike from the maximum acceptable portfolio drawdown, not from the cheapest premium. Align expiration with the protected horizon, review delta and event IV, and choose the call strike from a price at which sale is acceptable. Confirm current tax treatment with a professional because collars and protective puts may affect holding periods or straddle rules.",
            "Own stock at 100, buy a 90 put for 2, and sell a 110 call for 2. The option cash flow is zero, but downside below 90 is floored and upside above 110 is surrendered. If stock rises to 108, rolling both boundaries changes the hedge and creates a new economic decision.",
            "Do not advertise a collar as free. Early assignment, dividends, tax effects, and foregone gains matter. Adjusting only one leg can temporarily create naked or unprotected exposure; calculate the combined position before and after every roll.",
        ),
    ),
    18: (
        Supplement(
            "Buying Straddles and Strangles",
            ("straddle buying", "selecting a straddle buy", "follow-up action", "buying a strangle"),
            "A long straddle buys a call and put at the same strike and expiration; a long strangle buys an OTM call and OTM put with different strikes. Both seek movement and/or volatility expansion rather than a single direction. The strangle costs less but requires a larger move through a wider no-profit region.",
            "Select expiration to include the catalyst and enough follow-through time. Compare total debit, two breakevens, combined gamma/theta/vega, event IV, expected move, liquidity in both legs, and the historical relationship between implied and realized movement. Define whether legs will be managed together or separately.",
            "With stock 100, buy the 100 call for 4 and 100 put for 3. The $7 straddle breaks even at 93 and 107 at expiration. A 95 put plus 105 call costing 4 creates strangle breakevens at 91 and 109. The cheaper structure needs a larger move.",
            "Direction can be right on one leg while total position loses to theta and IV crush. Selling the winning leg leaves a naked long option with a new directional thesis. Follow-up should use total package value, realized movement, remaining catalyst, and decay—not the emotional urge to rescue the losing leg.",
        ),
    ),
    19: (
        Supplement(
            "Evaluating and Managing Put Writes",
            ("follow-up action", "evaluating a naked put write", "buying stock below its market price", "covered put sale", "ratio put writing"),
            "A short put is evaluated as a conditional stock purchase plus short-volatility exposure. A covered put combines short stock with a short put, capping some downside gain while retaining upside short-stock loss. Ratio put writing sells more puts than another leg or stock hedge covers, creating nonlinear downside exposure.",
            "Measure effective purchase price, maximum loss to zero, buying power under stress, assignment capacity, dividend/event risk, and alternative covered-call economics. Follow-up choices include buy to close, accept assignment, roll as a new trade, add a defined-risk wing, or close related stock.",
            "Sell a 95 put for 3 with stock 100. Effective assignment cost is 92, but if stock falls to 60 the loss is 32 points—not a bargain merely because purchase is below the original market. Selling two puts doubles the obligation to 200 shares.",
            "Premium yield can obscure crash exposure and correlation across several put writes. Naked and cash-secured describe funding, not different expiration payoff. Covered puts are frequently misunderstood; short stock does not make every short-put quantity safe.",
        ),
    ),
    20: (
        Supplement(
            "Covered and Uncovered Straddles, Strangles, and Follow-Up",
            ("covered straddle write", "uncovered straddle write", "selecting a straddle write", "follow-up action", "equivalent stock position follow-up", "starting with protection in place", "strangle combination writing"),
            "A short straddle sells same-strike call and put; a short strangle separates the strikes. Owning shares covers only the call side of one contract—the short put still obligates another purchase—so a so-called covered straddle can increase share exposure on a decline. Protection can be added at entry with outer wings, creating an iron butterfly or condor.",
            "Select only after comparing total credit, breakevens, expected move, IV versus expected realized movement, event calendar, margin, assignment capacity, and wing cost. Follow up from total package delta/gamma/vega and executable close price; equivalent shares after assignment must be included in account exposure.",
            "Stock at 100: sell the 100 call and put for total 8, giving 92 and 108 breakevens. If already long 100 shares and the put is assigned below 100, the account can become long 200 shares. Buying 90 put and 110 call wings defines both tails.",
            "The premium is the maximum profit, not a cushion against unlimited movement. Gamma accelerates near expiration, and assignment can transform the position. Never call a short strangle safer solely because strikes are wider; credit, tail loss, and margin must be evaluated together.",
        ),
    ),
    21: (
        Supplement(
            "Split-Strike Synthetic Stock",
            ("splitting the strikes",),
            "Classic synthetic stock uses the same call and put strike. Splitting strikes creates a different payoff: long call above one strike and short put below another leaves a middle region with reduced or flat exposure, resembling a risk reversal rather than exact stock replication.",
            "Choose strikes from the desired purchase floor and upside participation point, then calculate net premium, both obligations, delta across regions, margin, and assignment. Compare with a collar or stock limit order because the split structure may embed the same economic intent differently.",
            "Buy a 105 call and sell a 95 put. Between 95 and 105 both expire worthless and only net premium remains; above 105 gains begin, while below 95 losses mimic ownership acquired at 95. It does not track stock dollar-for-dollar in the middle.",
            "Calling this synthetic stock without the split-strike qualifier is misleading. Tail downside remains substantial, upside begins late, and early assignment is possible. Financing and dividends prevent exact equivalence across all dates.",
        ),
    ),
    22: (
        Supplement(
            "Put Calendar Spreads",
            ("calendar spread using puts",),
            "A put calendar sells a nearer put and buys a farther put at the same strike. It generally seeks front-month decay near the strike while retaining back-month vega and downside exposure; strike placement can make it neutral or bearish.",
            "Select strike from the expected price at front expiration and expirations from catalyst placement and term structure. Compare net debit, front/back IV, theta, vega, liquidity, and early-assignment risk on the short put.",
            "With stock 100, sell the 30-day 95 put and buy the 60-day 95 put. A drift toward 95 can help, but a violent early drop may make the front short put dominate temporarily. At front expiration the back put still has uncertain time value.",
            "Profit is not fixed in advance, and assignment can create long shares before the farther put is monetized. Close or roll the short leg deliberately; never let the calendar become an accidental standalone long put or stock-plus-put position.",
        ),
    ),
    23: (
        Supplement(
            "Combined Call/Put Butterflies and Purchase-Plus-Spread Structures",
            ("butterfly spread", "condor spreads", "combining an option purchase and a spread", "follow-up action for bull or bear spreads", "useful bull complex strategies", "selecting the spreads"),
            "Calls and puts can be combined into iron butterflies, iron condors, collars, seagulls, and purchased-option-plus-credit-spread structures. Equivalent expiration payoffs may use different legs, but liquidity, assignment, and cash flow differ.",
            "Start with direction, target range, acceptable tail loss, volatility view, and capital. Then compare total net debit/credit, wing width, breakevens, Greeks, leg liquidity, early exercise, and operational complexity. Select the simplest structure that expresses the view without redundant legs.",
            "A long call plus a bear call spread can create staged upside: the outright call participates first while the spread finances part of cost and caps a region. An iron condor combines a bull put spread and bear call spread; maximum loss is one wing width minus total credit when widths match.",
            "More legs do not create more edge. Follow-up must account for the whole package; closing one profitable side of a condor leaves the other side's risk. Equivalent payoff diagrams can have very different fill quality and assignment paths.",
        ),
    ),
    24: (
        Supplement(
            "Delta-Based Put Ratios and Ratio Calendars",
            ("using deltas", "ratio put calendar spread", "ratio calendar combination"),
            "Delta can choose contract ratios that begin directionally balanced, but different strikes and expirations have different gamma. A put ratio calendar uses unequal quantities across expirations; the ratio-calendar combination extends that idea across multiple strikes or dates.",
            "Calculate net delta, gamma, theta, vega, downside tail, and assignment quantity under several prices. Choose ratios from risk objectives rather than rounding until the opening delta displays zero. Define rebalance and front-expiration actions before entry.",
            "One back-month put with -0.60 delta versus two front puts with -0.30 each begins near delta-neutral when the fronts are short. A decline changes front and back deltas at different speeds, so the neutral reading can vanish and short downside can emerge.",
            "Model Greeks are estimates and ratios amplify errors. A front short put can be assigned while the back hedge remains an option. Never add short contracts solely to finance the debit without quantifying the new crash exposure.",
        ),
    ),
    25: (
        Supplement(
            "Pricing, Comparing, Buying, Selling, and Spreading LEAPS",
            ("pricing LEAPS", "comparing LEAPS and short-term options", "LEAPS strategies", "speculative option buying with LEAPS", "selling LEAPS", "spreads using LEAPS"),
            "LEAPS use the same pricing inputs as shorter options but carry more vega, more interest/dividend sensitivity, and slower daily theta initially. They support stock replacement, long-dated speculation, protective positions, diagonals, verticals, and covered-call overlays. Selling a LEAPS option accepts a long-lived obligation.",
            "Compare total extrinsic value, extrinsic value per day, delta, vega, breakeven, liquidity, event horizon, capital, and adjustment flexibility. Match expiration to the thesis plus a margin of time; decide whether a vertical or diagonal reduces cost without removing the expected payoff.",
            "A 12-month 80-delta call may cost 20 while a 30-day call costs 3. The short option is cheaper in dollars but may require repeated correct timing. A 100/120 LEAPS call spread costing 8 risks $800 to make at most $1,200 and reduces vega compared with the outright call.",
            "Long duration does not prevent loss. IV contraction, wide spreads, dividends, path changes, and thesis decay matter. Selling short-dated calls against a LEAPS call can create assignment and coverage mismatches; verify broker treatment and manage both expirations together.",
        ),
    ),
    27: (
        Supplement(
            "Put-Call, Dividend, Carry, and Box Arbitrage",
            ("basic put and call arbitrage discounting", "dividend arbitrage", "carrying costs", "box spread", "interest play"),
            "Put-call parity links stock, call, put, strike present value, dividends, and financing. A box combines a bull call spread and bear put spread with the same strikes/expiration to create a fixed expiration payoff; its price implies a financing rate. Dividend arbitrage examines exercise and stock/dividend cash flows rather than treating the dividend as free.",
            "Synchronize executable quotes, include bid/ask on every leg, commissions, stock borrow, dividend timing, exercise fees, rate convention, and capital. Compare the net package cost with the present value of the locked payoff only after confirming all legs can fill together.",
            "A 100/110 long box pays exactly 10 at expiration. If executable net debit is 9.80, the gross financing gain is 0.20, but fees and capital usage may erase it. Using midpoint prices for four legs can fabricate an apparent profit that cannot be executed.",
            "Retail traders rarely receive true riskless fills. Early exercise, dividend changes, borrow recalls, stale quotes, tax, and pin handling introduce risk. Never leg into an arbitrage package or call a theoretical parity difference realized profit.",
        ),
        Supplement(
            "Equivalence, Conversion Risk, Pairs, and Block Facilitation",
            ("risks in conversions and reversals", "variations on equivalence arbitrage", "effects of arbitrage", "risk arbitrage using options", "pairs trading", "facilitation block positioning"),
            "Conversions, reversals, synthetics, and boxes enforce price relationships when arbitrageurs trade discrepancies. Risk arbitrage instead accepts deal-completion risk; pairs trades accept relative-value and basis risk. Block facilitation uses hedges to absorb a large customer position while controlling inventory exposure.",
            "Separate locked arbitrage from statistical or event-dependent convergence. For each structure list the convergence mechanism, horizon, hedge ratio, borrow and liquidity needs, failure event, and unwind plan. A relationship observed historically is not enforceable parity.",
            "Long one company and short a related company can be delta-dollar neutral yet lose if their relationship structurally breaks. A merger spread hedged with options can gap violently on deal failure. A dealer facilitating a block may use stock and options to neutralize delta while retaining gamma or vega inventory.",
            "Model correlation, legal outcomes, and liquidity can fail together. Arbitrage activity narrows prices but can also transmit forced flows. Label every result as theoretical, executable, or realized and never mix them in performance claims.",
        ),
    ),
    28: (
        Supplement(
            "Black-Scholes, Composite IV, and Strategy Calculations",
            ("Black-Scholes model", "computing composite implied volatility", "applying calculations to strategy decisions", "implementation"),
            "Black-Scholes maps stock price, strike, time, volatility, rate, and dividend assumptions to a theoretical European-option value and Greeks. Implied volatility reverses the model: it is the volatility input consistent with market price. Composite IV combines observations using a declared weighting method rather than casually averaging incompatible contracts.",
            "Use models for consistent comparison and sensitivity analysis, not as a promise of fair value. Clean crossed/stale quotes, choose bid/mid/ask consistently, normalize maturities, document dividend/rate inputs, and compare model output with executable prices and scenario P&L.",
            "If two comparable options have IVs of 20% and 30% weighted 70/30 by vega, composite IV is 23%, not 25%. A strategy decision should then stress price at 18%, 23%, and 30% IV and multiple dates rather than rely on one point estimate.",
            "Black-Scholes assumptions—continuous trading, stable volatility, frictionless hedging, and idealized returns—do not hold exactly. American exercise, jumps, skew, discrete dividends, and illiquidity create model error. Version inputs and preserve calculation receipts.",
        ),
        Supplement(
            "Institutional Positioning and Mathematical Follow-Up",
            ("expected return", "facilitation institutional block positioning", "aiding in follow-up action", "advanced mathematical concepts"),
            "Expected return weights every modeled outcome by probability; it is not the most likely outcome. Institutional positioning adds inventory, hedge, market-impact, and execution constraints. Follow-up math compares current expected value and risk with the cost of closing or adjusting, without pretending the original entry price remains relevant.",
            "Define the scenario distribution, estimated probabilities, payoff after slippage/fees, uncertainty range, and position limit. Recompute with current price, time, IV, and liquidity. Use sensitivity and stress tests alongside—not instead of—judgment about model error.",
            "Outcomes of +500 with 35%, +100 with 25%, and -400 with 40% have expectation 175+25-160=$40. If a later quote changes probabilities and close cost, the hold decision uses the new distribution; the original $40 estimate is historical evidence, not an anchor.",
            "Small probability errors can reverse estimated edge, especially with asymmetric tails. Do not optimize weights on the same sample used to evaluate them. Block size can move the market, making marginal fills worse than displayed prices.",
        ),
    ),
    29: (
        Supplement(
            "Index Construction, Cash Settlement, Futures, and Put-Call Ratios",
            ("indices", "cash-based options", "futures trading", "options on index futures", "standard option strategies using index options", "put-call ratio"),
            "An index is a calculated basket, not a share. Many index options settle in cash and use European exercise, while ETF options commonly settle into shares and may be American. Futures are leveraged agreements marked to market; an option on a futures contract delivers or settles against the specified futures contract. Put-call ratio compares put activity with call activity, but its meaning depends on whether volume or open interest and which market are used.",
            "Verify multiplier, settlement value, last trading time, AM/PM settlement, exercise style, tax category, and the exact futures month. Standard verticals, calendars, butterflies, straddles, and collars transfer only after those contract specifications and cash obligations are understood.",
            "A cash-settled index call finishing 5 points ITM with a $100 multiplier pays $500 rather than delivering shares. A futures option assignment can create one futures contract whose mark-to-market and margin begin immediately. Put volume 200,000 divided by call volume 160,000 gives a 1.25 volume ratio, not a directional certainty.",
            "Index, ETF, futures, and futures-option prices can diverge through dividends, rates, basis, and trading hours. Never assume SPX, SPY, and an S&P futures option are interchangeable. High put-call ratios may reflect hedging rather than bearish speculation.",
        ),
    ),
    30: (
        Supplement(
            "Market Baskets, Program Trading, Index Arbitrage, and Impact",
            ("market baskets", "program trading", "index arbitrage", "impact on the stock market"),
            "A market basket is a weighted group intended to represent an index or exposure. Program trading executes many components systematically. Index arbitrage trades differences among baskets, ETFs, futures, and theoretical fair value, transmitting price pressure between derivatives and constituent shares.",
            "Construct weights from the index methodology, estimate transaction cost and market impact, and compare executable basket value with futures/ETF value after dividends and financing. Program rules need participation limits, stale-price controls, halt handling, and a plan for partial fills.",
            "If fair-value futures imply 5,020 while futures trade 5,026 beyond costs, an arbitrageur may sell futures and buy the basket. The trade itself buys constituents and sells futures, helping close the gap but potentially moving many stocks simultaneously.",
            "A theoretical gap smaller than total spread, fees, latency, and impact is not arbitrage. Component halts, rebalance changes, closing auctions, and crowded unwinds can break synchronization. Automated execution can amplify short-term market moves without changing long-term fundamental value.",
        ),
        Supplement(
            "Simulating an Index, Tracking Error, and Hedge Follow-Up",
            ("follow-up strategies", "market basket risk", "simulating an index", "trading the tracking error"),
            "A sampled basket uses fewer holdings or proxies to imitate an index. Tracking error is the variability of portfolio return minus benchmark return, arising from weights, fees, cash, timing, dividends, liquidity, and omitted names. Trading tracking error is a relative-value position, not a riskless hedge.",
            "Measure rolling active return, beta, sector/factor weights, concentration, rebalance drift, and stressed correlation. Follow up by rebalancing, resizing index options/futures, replacing stale proxies, or closing when the basis thesis changes rather than mechanically chasing every small deviation.",
            "A portfolio returns 1.2% while its benchmark returns 1.0%, producing +0.2% active return. Repeating this calculation across periods and taking the standard deviation estimates tracking error. One positive observation is not persistent alpha.",
            "Correlations rise and fall, and a basket can miss idiosyncratic events or index reconstitutions. Frequent rebalancing adds cost. A hedge sized from yesterday's beta may over- or under-hedge after large price moves.",
        ),
    ),
    31: (
        Supplement(
            "Constructing and Managing Inter-Index Spreads",
            ("inter-index spreading",),
            "An inter-index spread takes opposing exposures in two related indexes to trade relative performance while reducing broad market direction. Exposure must be normalized for dollar value, multiplier, beta, volatility, and factor composition; equal contract counts rarely mean neutral risk.",
            "State the relative thesis, select instruments with compatible hours and liquidity, calculate hedge ratio, monitor active return and factor drift, and define convergence or invalidation. Include dividends, futures basis, settlement dates, and option Greeks when options implement the legs.",
            "If one index contract has $250,000 notional and another $150,000, one-versus-one leaves $100,000 gross directional imbalance before beta adjustment. A 3:5 ratio equalizes $750,000 notionals but may still differ in volatility and sector exposure.",
            "Relative spreads can lose even when the market direction is forecast correctly. Structural divergence, index rebalancing, different settlement prints, and legging slippage matter. Rebalance only under predefined bands so noise does not consume the expected edge.",
        ),
    ),
    32: (
        Supplement(
            "Principal-Protected Structures, Cash Value, and Embedded Calls",
            ("riskless ownership of a stock or index", "cash value", "cost of the embedded call option", "price behavior prior to maturity", "SIS"),
            "A principal-protected note can be decomposed into a discounted bond component that grows toward principal plus an embedded call providing participation. 'Riskless' is conditional on issuer solvency, holding to maturity, and contract terms. Cash value before maturity reflects rates, credit spread, remaining option value, and dealer liquidity.",
            "Decompose issue price into bond present value, option budget, fees, participation rate, cap, averaging, barriers, and issuer credit. Compare with buying Treasury securities and listed options directly. Verify what SIS means in the specific product documentation rather than relying on a marketing label.",
            "For $1,000 principal due in two years, suppose the zero-coupon component costs $920. At most $80 remains before fees to purchase index-call exposure. If the desired call costs $100, participation must be below 100% or another feature must reduce option cost.",
            "Before maturity, the note may trade below principal because protection applies only at maturity and issuer credit or rates changed. Embedded options can be difficult to value and secondary markets may be dealer-dependent. Principal protection is not FDIC insurance unless explicitly stated and eligible.",
        ),
        Supplement(
            "Discounts, Adjustment Factors, and Structured-Product Strategies",
            ("computing embedded call when underlying trades at a discount", "adjustment factor", "other constructs", "option strategies involving structured products", "lists of structured products", "other structured products"),
            "When an underlying or proxy trades at a discount, option participation must be adjusted for the actual reference level, conversion ratio, dividends, fees, and maturity payoff definition. Adjustment factors translate quoted participation into economic exposure. Other constructs include reverse convertibles, buffered notes, autocallables, capped participation notes, and barrier products.",
            "Map every product into simpler cash and option legs. Identify issuer, maturity, reference asset, observation dates, barriers, caps, coupon conditions, callability, settlement, adjustment clauses, and worst-case loss. Compare the package with a transparent self-built alternative.",
            "A note offers 150% participation up to a 12% cap: a 20% index rise still earns only 12%, not 30%. A buffered note absorbing the first 10% decline may expose the investor dollar-for-dollar beyond the buffer; at -35%, contractual loss may be 25% before issuer effects.",
            "Marketing names are not payoff definitions. Path-dependent barriers, issuer calls, dividend exclusion, caps, illiquidity, and credit risk can dominate. Never model only maturity endpoints when observation dates or autocall features change the path.",
        ),
    ),
    33: (
        Supplement(
            "Index-Product Arbitrage and Mathematical Applications",
            ("arbitrage", "mathematical applications"),
            "Index-product mathematics links constituent basket value, ETF net asset value, futures fair value, dividends, rates, time, and option parity. Authorized participants and arbitrageurs trade deviations, but retail calculations must distinguish indicative values from executable baskets.",
            "Calculate index weights, divisor effects, futures carry, ETF premium/discount, option parity, and tracking error using synchronized timestamps. Apply sensitivity tests for dividend and rate assumptions and include transaction costs for every constituent or proxy.",
            "If spot index is 5,000, annual financing 4%, dividend yield 1.5%, and time 0.25 years, simplified continuous-carry futures fair value is about `5000*exp((.04-.015)*.25)`, roughly 5,031. Apparent deviation must exceed spread, fees, and model uncertainty.",
            "An index level itself cannot be bought. Stale constituent prices, closing-auction methodology, corporate actions, tax, and creation/redemption constraints cause differences. Never label model residual as arbitrage profit without an executable replication.",
        ),
    ),
    34: (
        Supplement(
            "Futures Trading Strategies and Mispricing Controls",
            ("futures option trading strategies", "compliance mispricing strategies"),
            "Futures options support directional calls/puts, verticals, calendars, straddles, collars against futures, and volatility trades. Mispricing analysis compares options with futures parity and volatility surfaces while respecting position limits, exchange rules, reporting, and account permissions.",
            "Verify contract month, option expiration, underlying-delivery month, multiplier, tick value, settlement, trading hours, margin, daily price limits, and whether exercise creates futures. Compare synchronized executable quotes and document compliance constraints before trading a discrepancy.",
            "A call exercised into one futures contract can create notional exposure far larger than premium paid. A collar around a long futures contract buys a put and sells a call on the matching month; mismatched months introduce calendar basis risk.",
            "Futures leverage and overnight sessions create rapid margin changes. A cheap-looking option may reference a different delivery month. Mispricing is not permission to evade position limits or exchange rules, and midpoint surface differences may be unfillable.",
        ),
    ),
    35: (
        Supplement(
            "Futures Spreads and Options on the Spread",
            ("futures spreads", "using futures options in futures spreads"),
            "A futures spread trades the price difference between delivery months, commodities, or related contracts. Options can cap one leg, express a nonlinear view on a calendar relationship, or hedge the spread's tail; the risk driver is basis movement, not merely outright direction.",
            "Define spread quotation, seasonality, delivery mechanics, hedge ratio, margin offsets, liquidity by month, and roll dates. For options, verify which futures month each option delivers and scenario-test both legs through expiration and assignment.",
            "Long December futures and short March futures trades the Dec-Mar calendar spread. Buying a put on December alone limits that leg's decline but leaves March-leg movement and cross-month basis. Options on different months do not automatically create a defined-risk package.",
            "Margin offsets can disappear during stress. Delivery, limit moves, thin deferred months, and mismatched expirations can prevent a clean unwind. Model the spread and each outright leg because basis convergence is not guaranteed on the trader's timetable.",
        ),
    ),
    36: (
        Supplement(
            "Measuring Volatility: Graphs, Moving Averages, and Vol-of-Vol",
            ("definitions of volatility", "another approach graph", "moving averages", "implied volatility", "volatility of volatility"),
            "Historical volatility measures realized dispersion from returns; implied volatility is the model input backed out from option prices. Graphs reveal clustering, regime shifts, skew, and term structure. Moving averages smooth noisy observations but lag. Volatility-of-volatility measures how unstable volatility itself is.",
            "Declare return frequency, annualization, lookback, close-to-close versus intraday estimator, and treatment of missing data. Plot realized measures beside maturity-specific IV, use multiple moving-average horizons, and evaluate vol-of-vol before assuming today's IV regime persists.",
            "Twenty daily log returns with sample standard deviation 1.2% annualize near `1.2%*sqrt(252)=19.0%`. A 10-day average reacts faster than a 60-day average. If IV repeatedly jumps between 18% and 35%, its level and its own volatility both matter for sizing short-vega trades.",
            "Annualization assumes comparable independent intervals and can understate jumps. Moving averages do not forecast turning points. Mixing IVs across strikes or expirations without normalization creates false signals, and one calm window can conceal severe tail risk.",
        ),
        Supplement(
            "Trading Volatility and Understanding Extremes",
            ("volatility trading", "why volatility reaches extremes"),
            "Volatility trades seek differences between implied movement and subsequently realized movement using straddles, strangles, calendars, variance exposure, or delta-hedged options. Extremes arise from information shocks, forced hedging, liquidity withdrawal, event uncertainty, leverage unwinds, and risk-premium demand.",
            "State whether the view concerns level, direction, skew, term structure, or realized-versus-implied spread. Define hedge frequency, transaction cost, event exposure, and loss limit. Compare current readings with regime-aware history rather than a single lifetime percentile.",
            "Buying a straddle at 25% IV profits from realized movement only if gains from movement/IV overcome theta and hedging cost. Selling at 80% IV can still lose if realized volatility becomes 120%; high is not automatically overpriced.",
            "Volatility is mean-reverting in some horizons but can remain extreme and gap higher. Short-volatility losses are often convex and correlated with poor liquidity. Backtests must include realistic options, spreads, and hedging—not just an index of volatility.",
        ),
    ),
    37: (
        Supplement(
            "Position Vega, Delta, Neutrality, and Time Value",
            ("vega", "implied volatility and delta", "effects on neutrality", "position vega", "time value premium is a misnomer", "volatilizing at the put option"),
            "Position vega sums each leg's vega times quantity and multiplier; IV changes can also alter delta and destroy apparent neutrality. Extrinsic value is often called time value, but volatility and rates contribute, so time-value premium is an incomplete label. Put IV often rises at lower strikes because investors pay for crash protection.",
            "Compute net delta and vega by leg, then shock underlying and IV together. Recalculate neutrality after moves because gamma changes delta. Compare put skew and executable premium rather than assuming all strikes share one IV.",
            "Ten contracts with vega 0.08 have roughly $80 position sensitivity per one IV point (`0.08*100*10`). If IV rises five points, a first-order estimate is +$400, but delta/gamma and nonlinear effects also change the result.",
            "Greek sums are local estimates, not guaranteed P&L. Offsetting delta can hide large gamma or vega. Calling all extrinsic value 'time' encourages traders to blame theta when IV contraction was the dominant loss.",
        ),
        Supplement(
            "Volatility Effects Across Straddles and Spreads",
            ("outright option purchases and sales", "straddle or strangle buying and selling", "call bull spreads", "vertical put spreads", "put bear spreads", "calendar spreads", "ratio spreads and backspreads"),
            "Long single options, straddles, and strangles are generally long vega; short versions are short vega. Verticals partially offset vega between legs. Calendars are often long back-month vega and short front-month vega. Ratios and backspreads can change vega sign by price and time.",
            "For each strategy, chart net vega and scenario P&L across underlying price, IV shifts, and dates. Do not assign one permanent label when strikes/quantities make exposure state-dependent. Include skew changes, not only parallel IV shifts.",
            "A long 100 call with vega .10 and short 105 call with vega .07 leaves about +.03 vega per share. A 10-point IV fall therefore has a first-order -$30 effect per spread, far less than the -$100 estimate for the naked long call.",
            "Vega can collapse near expiration while gamma explodes. Calendars can lose when both IV level and term structure move adversely. Short straddles and ratio spreads have tail risks that a small opening vega number does not reveal.",
        ),
    ),
    38: (
        Supplement(
            "Price Distributions, Probability, Pricing, and Expected Return",
            ("misconceptions about volatility", "volatility buyers rule", "distribution of stock prices", "what this means for option traders", "pricing of options", "probability of stock price movement", "expected return"),
            "A price distribution assigns probabilities to future outcomes; it is not a promise that returns are normal or that volatility is constant. Option prices reflect a risk-neutral pricing distribution plus market frictions and risk premia, while a trader's expected-return distribution can differ. A volatility buyer needs realized movement large and timely enough to overcome implied premium and decay.",
            "Define horizon, return convention, volatility/skew assumptions, jumps, and scenario probabilities. Distinguish probability of finishing ITM, probability of touching, and probability of profit after premium. Compute expected return from net payoffs, not from moneyness alone.",
            "A call might have 40% probability of a $600 gain and 60% probability of a $300 loss: expectation is `0.4*600-0.6*300=$60`. A 40% ITM probability does not itself produce that expectation because payoff size and entry price are essential.",
            "Fat tails, volatility clustering, skew, and estimation error make simple distributions fragile. Delta is not an exact probability. A strategy can win frequently and have negative expectation, or lose frequently and remain positive if payoff asymmetry compensates.",
        ),
    ),
    39: (
        Supplement(
            "Volatility Forecast Errors and Trading the Forecast",
            ("two ways volatility prediction can be wrong", "trading the volatility prediction", "trading the volatility skew", "summary of volatility trading"),
            "A forecast can be wrong in level—realized volatility differs from prediction—or wrong in timing/path—the expected movement occurs after decay, outside the chosen expiration, or through a skew/term-structure change. Trading the forecast requires selecting an instrument whose actual Greeks match the predicted dimension.",
            "Write a numeric forecast with horizon and uncertainty, compare it with implied volatility and break-even movement, choose long/short vega or relative skew/term exposure, and predefine hedge, cost, and invalidation. Evaluate forecast quality separately from execution quality.",
            "Forecast 30% realized volatility while one-month options imply 22%. A long straddle expresses the gap but can still lose if movement arrives after expiration or transaction costs consume gamma gains. A skew trade might buy relatively cheap calls and sell puts while remaining exposed to direction and crash repricing.",
            "A correct volatility direction is insufficient when magnitude, timing, skew, or hedge execution is wrong. Do not grade forecasts from trade P&L alone, and do not infer skill from one event. Preserve inputs and compare repeated out-of-sample forecasts.",
        ),
    ),
    40: (
        Supplement(
            "Neutrality and the Greeks as a Position System",
            ("neutrality", "the Greeks", "strategy considerations using the Greeks"),
            "Neutrality can refer to delta, beta, dollar, vega, theta, gamma, or factor exposure; neutral in one dimension leaves others. Delta, gamma, theta, vega, and rho describe local sensitivities, while cross-Greeks explain interactions. Strategy Greeks are sums of legs but change with price, time, and volatility.",
            "Declare which exposure is neutral and why, calculate position Greeks with multipliers, shock correlated inputs, establish rebalance bands, and include transaction costs. Choose strategies by the Greek profile required by the thesis rather than by payoff name.",
            "A delta-neutral long straddle can have positive gamma, negative theta, and positive vega. A stock move creates delta that hedging may monetize, but repeated hedges must earn more than theta and trading cost. Zero opening delta does not mean zero risk.",
            "Greeks are derivatives of a model, not independent guarantees. Large jumps invalidate small-change approximations. Hedging one Greek can increase another, and continuous neutrality is impossible in discrete, costly markets.",
        ),
        Supplement(
            "Advanced Option Mathematics and Cross-Greeks",
            ("advanced mathematical concepts",),
            "Advanced analysis uses convexity, Taylor approximations, probability distributions, stochastic volatility, local volatility, correlation, and cross-Greeks such as vanna and charm. These tools explain why delta changes with both price, time, and IV and why portfolios behave nonlinearly.",
            "Use the simplest model adequate for the decision, record assumptions, and compare first-order Greek estimates with full repricing under large scenarios. Validate calibration out of sample and distinguish descriptive fit from predictive edge.",
            "A second-order approximation is `dV ≈ delta*dS + 0.5*gamma*dS² + vega*dIV + theta*dt`. For a large move, omitted cross-terms and changing Greeks can make this estimate poor, so full repricing is required.",
            "More mathematics can create false precision. Parameter instability, sparse tail data, discretization, and calibration overfit are material. A model that reproduces today's surface may have no forecasting power for tomorrow.",
        ),
    ),
    41: (
        Supplement(
            "VIX Calculation, Futures, Options, and Directional Information",
            ("historical and implied volatility", "calculation of VIX", "listed volatility futures", "other listed volatility products", "listed VIX options", "trading strategies directional signals", "using VIX futures information"),
            "VIX estimates a 30-day forward variance expectation from a strip of SPX option prices, interpolating nearby maturities; it is not today's realized volatility. VIX futures price future settlement expectations and can differ from spot. VIX options reference the corresponding forward settlement ecosystem, not a directly tradable spot index.",
            "Inspect futures curve, contract month, settlement calculation, option expiration, bid/ask, and exposure of ETPs that roll futures. Treat VIX changes as contextual information about expected variance and hedging demand, not a standalone equity direction signal.",
            "Spot VIX at 18 and three-month futures at 22 describe contango, but buying a VIX product may lose from roll even if spot is unchanged. A VIX call must be evaluated against its matching futures level and settlement date, not solely against displayed spot VIX.",
            "VIX cannot be bought directly, products can decay or rebalance, and settlement can diverge from prior closes. Historical inverse stock/VIX correlation can break. Leveraged volatility ETPs have path dependence and are not long-term spot trackers.",
        ),
        Supplement(
            "Term Structure, Portfolio Protection, Macro, and Hedged VIX Trades",
            ("using and trading the term structure", "protecting a stock portfolio with volatility derivatives", "other macro strategies", "hedged strategies using volatility derivatives", "ratio spreads with VIX options"),
            "Volatility term structure compares expectations across maturities; calendar spreads and futures spreads trade its shape. VIX calls or call spreads can provide convex crisis exposure, while macro and hedged strategies combine volatility instruments with equity, rate, or credit exposure. VIX ratio spreads finance protection by selling more upside calls and can reintroduce extreme-tail risk.",
            "Match hedge maturity and notional to the risk window, stress spot/futures basis and correlation, price roll cost, and cap short-option tails. For macro trades, state the transmission mechanism rather than assuming every risk-off event lifts every volatility product equally.",
            "Buy one 25 VIX call and sell two 35 calls to reduce debit. Protection grows between strikes but can decline above the ratio's upper breakeven, precisely during an extreme volatility event. Adding a farther call can define that tail.",
            "Volatility protection often loses carry during calm periods and may not respond on schedule. Term structure can invert, correlations can shift, and settlement is specialized. Never finance disaster insurance with an uncapped short tail without explicitly accepting that failure mode.",
        ),
    ),
    42: (
        Supplement(
            "Tax History, Exercise, Assignment, and Special Problems",
            ("history", "exercise and assignment", "special tax problems"),
            "Options tax rules evolved around realization, holding periods, constructive sales, straddles, wash sales, and special treatment for certain broad-based contracts. Exercise commonly folds option basis or proceeds into acquired/delivered stock; assignment changes stock sale or purchase economics. Exact treatment depends on jurisdiction, product, account, and current law.",
            "Keep trade confirmations, fees, opening/closing designation, exercise/assignment notices, adjusted contract records, and lot elections. Identify equity versus qualifying index/futures products and consult current IRS guidance and a qualified tax professional before relying on a strategy.",
            "A call purchased for $300 and exercised may add $300 to stock basis rather than create a separate option gain at that moment. A covered call assignment may change stock proceeds and holding-period analysis. This example is conceptual, not a tax return instruction.",
            "Wash-sale, straddle, constructive-sale, mixed-straddle, Section 1256, retirement-account, and state rules can interact. Broker forms may not capture every adjustment. Never choose a trade solely for tax treatment or rely on an educational example for filing.",
        ),
        Supplement(
            "Tax Planning for Equity Options",
            ("tax planning strategies for equity options",),
            "Tax planning coordinates investment intent, timing, lots, exercises, assignments, hedges, and recordkeeping without allowing tax goals to override risk. Closing, rolling, exercising, or allowing assignment can produce different realization dates and basis treatment even when market exposure looks similar.",
            "Before year-end or a major adjustment, inventory open legs, stock lots, holding periods, prior losses, potential wash-sale windows, straddle relationships, and expected assignments. Ask a tax professional to evaluate alternatives under current law before execution.",
            "Rolling a call is a close plus a new opening trade; the realized result on the old call remains. Closing a loss and promptly opening a substantially identical exposure may require wash-sale analysis. Waiting for a tax date can expose the account to greater market loss than the tax benefit.",
            "Tax optimization based on uncertain future prices can backfire. Laws and broker reporting change, and multi-leg allocations can be complex. Preserve a complete audit trail and distinguish estimated after-tax scenarios from filed outcomes.",
        ),
    ),
    43: (
        Supplement(
            "Market Attitude, Equivalent Positions, and Mathematical Ranking",
            ("general concepts market attitude and equivalent positions", "what is best for me might not be best for you", "mathematical ranking"),
            "Strategy choice begins with market attitude—direction, magnitude, timing, volatility, and confidence—then compares economically equivalent positions. Personal constraints such as capital, approval level, assignment capacity, tax, liquidity, drawdown tolerance, and monitoring time make the best feasible structure trader-specific.",
            "Create a common scenario grid and rank candidates by expected value, worst-case loss, drawdown, probability of loss, capital, liquidity, Greek fit, operational burden, and sensitivity to estimation error. Reject any candidate that violates a hard constraint before combining scores.",
            "A long call, bull call spread, and cash-secured put can all express bullish views, but their outcomes differ if price is flat, rallies sharply, or collapses. A trader unable to accept assignment must reject the put regardless of its estimated expected value; another willing to own shares may rank it differently.",
            "A weighted score is only as sound as its inputs and weights. Do not conceal unlimited risk behind a high expected-return estimate or optimize rankings on past winners. The final choice remains conditional, documented, and revisable—not universally best.",
        ),
    ),
}
