# Tradysquids Applied Decision Supplement

This supplement expands every canonical Learning Center lesson with practical evidence checks, failure modes, journal fields, and drills. It is merged into Discord lessons and TradeBot search at runtime.

<!-- CHANNEL:01-stock-market-foundations -->
# Applied Expansion · Stock and Market Foundations

## Applied decision framework
Identify the instrument, exchange, session, primary return source, liquidity, and whether the quote is live, delayed, or a closing snapshot.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Identify the instrument, exchange, session, primary return source, liquidity, and whether the quote is live, delayed, or a closing snapshot.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Confusing an ETF with a single company, treating an index as directly tradable, ignoring session liquidity, and comparing unadjusted prices across splits.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: instrument type; session; quote timestamp; spread; volume; ownership or index exposure; known data limitations.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:01-stock-market-foundations -->

<!-- CHANNEL:02-company-fundamentals -->
# Applied Expansion · Company Fundamentals and Business Quality

## Applied decision framework
Map revenue drivers, customers, suppliers, competitive advantages, cyclicality, management incentives, and the business risks that can invalidate a technical thesis.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Map revenue drivers, customers, suppliers, competitive advantages, cyclicality, management incentives, and the business risks that can invalidate a technical thesis.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Using a familiar brand as proof of quality, ignoring concentration risk, treating one strong quarter as a durable moat, and reading management guidance without checking incentives.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: business model; industry cycle; catalyst; customer concentration; competitive risk; management claim; primary-source link.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:02-company-fundamentals -->

<!-- CHANNEL:03-financial-statements -->
# Applied Expansion · Financial Statements and Accounting

## Applied decision framework
Reconcile revenue, margins, operating income, cash flow, debt, dilution, and working capital across several periods instead of reading one headline number.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Reconcile revenue, margins, operating income, cash flow, debt, dilution, and working capital across several periods instead of reading one headline number.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Treating adjusted earnings as cash, ignoring stock compensation, missing debt maturities, comparing seasonal quarters incorrectly, and overlooking deteriorating receivables.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: statement period; revenue trend; margin trend; free cash flow; debt; share count; accounting warning; source date.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:03-financial-statements -->

<!-- CHANNEL:04-valuation-and-quality -->
# Applied Expansion · Valuation, Growth, and Quality

## Applied decision framework
Separate business quality from valuation, identify what growth is already priced in, and compare multiple scenarios rather than declaring one exact fair value.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Separate business quality from valuation, identify what growth is already priced in, and compare multiple scenarios rather than declaring one exact fair value.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Using a low P/E as automatic cheapness, extrapolating peak margins, ignoring capital intensity, and comparing multiples across unrelated industries.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: valuation method; assumptions; peer set; growth case; margin case; downside scenario; uncertainty range.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:04-valuation-and-quality -->

<!-- CHANNEL:05-market-mechanics-orders -->
# Applied Expansion · Market Mechanics and Order Execution

## Applied decision framework
Check bid, ask, spread, depth, order type, session, likely slippage, and whether the displayed last trade is actually executable.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Check bid, ask, spread, depth, order type, session, likely slippage, and whether the displayed last trade is actually executable.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Using market orders in thin contracts, confusing last price with midpoint, moving a limit repeatedly without a plan, and ignoring opening or closing auction behavior.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: bid; ask; midpoint; width; order type; fill; slippage; timestamp; reason for cancellation or replacement.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:05-market-mechanics-orders -->

<!-- CHANNEL:06-charts-price-action -->
# Applied Expansion · Charts, Candles, and Price Action

## Applied decision framework
Read trend, range, swing structure, gaps, support, resistance, breakout acceptance, pullback quality, and the timeframe that actually controls the trade.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Read trend, range, swing structure, gaps, support, resistance, breakout acceptance, pullback quality, and the timeframe that actually controls the trade.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Drawing levels from one touch, calling every move a breakout, ignoring higher-timeframe conflict, and shifting levels after entry to defend a losing thesis.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: timeframes; trend state; support; resistance; gap; breakout or pullback evidence; invalidation level.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:06-charts-price-action -->

<!-- CHANNEL:07-technical-analysis -->
# Applied Expansion · Technical Analysis and Indicators

## Applied decision framework
Use indicators as measurements of trend, momentum, volatility, and participation, then require agreement with price structure rather than voting by indicator count.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Use indicators as measurements of trend, momentum, volatility, and participation, then require agreement with price structure rather than voting by indicator count.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Treating overbought as an automatic short, stacking correlated indicators, optimizing thresholds on a tiny sample, and ignoring indicator lag.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: indicator values; price relationship; divergence; confluence; conflicting evidence; threshold version; missing inputs.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:07-technical-analysis -->

<!-- CHANNEL:08-volume-breadth-internals -->
# Applied Expansion · Volume, Breadth, and Market Internals

## Applied decision framework
Compare current volume with normal volume, check whether breadth confirms the index move, and distinguish broad participation from a move driven by a few large names.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Compare current volume with normal volume, check whether breadth confirms the index move, and distinguish broad participation from a move driven by a few large names.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Using raw volume without time-of-day context, assuming high volume is bullish, ignoring ETF composition, and reading one breadth print as a persistent regime.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: relative volume; time of day; breadth measure; sector participation; volume confirmation; contradiction.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:08-volume-breadth-internals -->

<!-- CHANNEL:09-macro-sectors-catalysts -->
# Applied Expansion · Macroeconomics, Sectors, and Catalysts

## Applied decision framework
Record the economic calendar, rate and inflation context, sector leadership, earnings timing, and whether the ticker is exposed to commodities, currencies, or policy.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Record the economic calendar, rate and inflation context, sector leadership, earnings timing, and whether the ticker is exposed to commodities, currencies, or policy.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Trading through scheduled releases unknowingly, attributing every move to one headline, ignoring sector correlation, and using stale economic data.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: event name; scheduled time; consensus; actual; sector reaction; rate or currency context; source.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:09-macro-sectors-catalysts -->

<!-- CHANNEL:10-stock-trading-strategies -->
# Applied Expansion · Stock Trading Styles and Strategies

## Applied decision framework
Match holding period, entry trigger, invalidation, liquidity, and expected movement to the chosen style instead of mixing day-trade entries with investment exits.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Match holding period, entry trigger, invalidation, liquidity, and expected movement to the chosen style instead of mixing day-trade entries with investment exits.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Changing style after the trade moves against the plan, using a trend rule in a range, chasing momentum after expansion, and averaging down without a defined thesis.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: style; setup family; trigger; holding window; invalidation; target logic; regime fit.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:10-stock-trading-strategies -->

<!-- CHANNEL:11-short-selling-margin -->
# Applied Expansion · Short Selling, Leverage, and Margin

## Applied decision framework
Verify borrow availability, borrow cost, margin requirement, squeeze risk, corporate actions, and the asymmetric loss profile before treating a short as the inverse of a long.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Verify borrow availability, borrow cost, margin requirement, squeeze risk, corporate actions, and the asymmetric loss profile before treating a short as the inverse of a long.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Ignoring recalls and buy-ins, using leverage because the share price looks low, holding through a catalyst without borrow review, and assuming losses are capped.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: borrow status; fee; margin; catalyst; squeeze indicators; maximum planned loss; forced-exit risk.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:11-short-selling-margin -->

<!-- CHANNEL:12-portfolio-risk -->
# Applied Expansion · Portfolio Construction and Risk Management

## Applied decision framework
Measure total exposure, correlated positions, maximum loss, drawdown, concentration, portfolio Greeks, and whether one event can damage several trades at once.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Measure total exposure, correlated positions, maximum loss, drawdown, concentration, portfolio Greeks, and whether one event can damage several trades at once.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Sizing each trade independently, treating different tickers in one sector as diversified, increasing size after losses, and using theoretical max loss without liquidity stress.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: position risk; portfolio risk; correlation; sector exposure; delta/vega/theta exposure; drawdown limit; available capital.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:12-portfolio-risk -->

<!-- CHANNEL:13-options-basics -->
# Applied Expansion · Options Foundations

## Applied decision framework
Identify the right or obligation, contract multiplier, strike, expiration, moneyness, premium, breakeven, deliverable, and what happens if the position is held.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Identify the right or obligation, contract multiplier, strike, expiration, moneyness, premium, breakeven, deliverable, and what happens if the position is held.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Confusing buying with selling, quoting premium without multiplying by 100, assuming breakeven is required before expiration, and overlooking adjusted contracts.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: side; long or short; strike; expiration; DTE; multiplier; premium; moneyness; deliverable.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:13-options-basics -->

<!-- CHANNEL:14-option-chain-liquidity -->
# Applied Expansion · Option Chains, Symbols, and Liquidity

## Applied decision framework
Validate the contract symbol, expiration, strike, bid, ask, midpoint, open interest, daily volume, width, and whether liquidity exists on every leg.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Validate the contract symbol, expiration, strike, bid, ask, midpoint, open interest, daily volume, width, and whether liquidity exists on every leg.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Selecting by open interest alone, trusting stale last prices, ignoring multi-leg net width, and assuming a liquid stock guarantees liquid options.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: contract symbol; bid; ask; midpoint; width percent; OI; volume; expiration; liquidity pass/fail.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:14-option-chain-liquidity -->

<!-- CHANNEL:15-option-pricing-greeks -->
# Applied Expansion · Option Pricing and the Greeks

## Applied decision framework
Record delta, gamma, theta, vega, rho, intrinsic value, extrinsic value, and how those sensitivities could interact under several price and volatility scenarios.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Record delta, gamma, theta, vega, rho, intrinsic value, extrinsic value, and how those sensitivities could interact under several price and volatility scenarios.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Treating delta as a guaranteed probability, reading theta as a constant daily charge, ignoring gamma near expiration, and comparing Greeks from different timestamps.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: delta; gamma; theta; vega; IV; intrinsic; extrinsic; scenario timestamp; Greek source.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:15-option-pricing-greeks -->

<!-- CHANNEL:16-volatility -->
# Applied Expansion · Volatility, IV, Skew, and Expected Move

## Applied decision framework
Compare implied and realized volatility, IV rank or percentile, term structure, skew, event premium, expected move, and the risk of volatility contraction.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Compare implied and realized volatility, IV rank or percentile, term structure, skew, event premium, expected move, and the risk of volatility contraction.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Buying high IV without a movement requirement, using IV rank from insufficient history, ignoring skew, and assuming expected move is a hard boundary.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: IV; realized volatility; rank/percentile; skew; term structure; expected move; event date; crush risk.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:16-volatility -->

<!-- CHANNEL:17-directional-options -->
# Applied Expansion · Directional Options Strategies

## Applied decision framework
Match direction, delta, DTE, liquidity, expected move, breakeven, theta exposure, and exit logic to the strength and duration of the underlying thesis.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Match direction, delta, DTE, liquidity, expected move, breakeven, theta exposure, and exit logic to the strength and duration of the underlying thesis.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Choosing cheap far-OTM contracts, using short DTE for a slow thesis, ignoring IV contraction, and evaluating success only by stock direction.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: direction; contract; DTE; delta; premium; breakeven; expected move; target; stop; time stop.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:17-directional-options -->

<!-- CHANNEL:18-income-and-hedging -->
# Applied Expansion · Income, Yield, and Hedging Strategies

## Applied decision framework
Separate income from risk transfer, define assignment willingness, opportunity cost, downside exposure, hedge objective, and how the position behaves after a large move.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Separate income from risk transfer, define assignment willingness, opportunity cost, downside exposure, hedge objective, and how the position behaves after a large move.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Calling premium free income, selling calls on shares that cannot be surrendered, using protective puts too late, and ignoring tax or dividend effects.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: underlying shares; short strike; hedge strike; credit/debit; assignment plan; downside retained; upside capped.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:18-income-and-hedging -->

<!-- CHANNEL:19-spreads-multi-leg -->
# Applied Expansion · Spreads and Multi-Leg Strategies

## Applied decision framework
Model every leg, net debit or credit, width, maximum profit, maximum loss, breakeven, Greeks, assignment risk, expiration risk, and exit liquidity.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Model every leg, net debit or credit, width, maximum profit, maximum loss, breakeven, Greeks, assignment risk, expiration risk, and exit liquidity.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Legging into a spread accidentally, using theoretical max loss without fill stress, holding short legs through expiration, and forgetting that one leg can be assigned early.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: all leg symbols; quantities; net price; width; max profit; max loss; breakeven; assignment plan; close-by date.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:19-spreads-multi-leg -->

<!-- CHANNEL:20-trade-planning-execution -->
# Applied Expansion · Trade Planning, Execution, and Management

## Applied decision framework
Write the thesis, trigger, confirmation, invalidation, maximum loss, target, time stop, adjustment rule, and the exact evidence that would justify no trade.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Write the thesis, trigger, confirmation, invalidation, maximum loss, target, time stop, adjustment rule, and the exact evidence that would justify no trade.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Entering before confirmation, widening stops, moving targets from fear, rolling without comparing the new trade independently, and recording rationale after the outcome.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: thesis; trigger; confirmation; invalidation; risk plan; target; time stop; adjustment; no-trade condition.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:20-trade-planning-execution -->

<!-- CHANNEL:21-expiration-assignment -->
# Applied Expansion · Expiration, Exercise, Assignment, and Settlement

## Applied decision framework
Know exercise style, settlement type, automatic-exercise rules, dividend timing, pin risk, assignment capital requirement, and the broker deadline for action.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Know exercise style, settlement type, automatic-exercise rules, dividend timing, pin risk, assignment capital requirement, and the broker deadline for action.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Assuming a spread closes itself safely, ignoring after-hours price movement, forgetting cash versus physical settlement, and relying on broker intervention.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: expiration; exercise style; settlement; short-leg risk; dividend; broker deadline; close-by plan.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:21-expiration-assignment -->

<!-- CHANNEL:22-events-corporate-actions -->
# Applied Expansion · Events, Earnings, and Corporate Actions

## Applied decision framework
Track earnings, guidance, dividends, splits, mergers, tenders, spin-offs, bankruptcies, halts, and whether option deliverables will be adjusted.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Track earnings, guidance, dividends, splits, mergers, tenders, spin-offs, bankruptcies, halts, and whether option deliverables will be adjusted.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Using old strikes after an adjustment, assuming a split changes value, trading through earnings without IV analysis, and relying on social posts instead of filings.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: event; effective date; source; expected contract adjustment; halt risk; IV effect; position action.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:22-events-corporate-actions -->

<!-- CHANNEL:23-psychology-journaling -->
# Applied Expansion · Trading Psychology and Journaling

## Applied decision framework
Separate process from outcome, record emotion and rule adherence, identify FOMO or revenge behavior, and review repeated errors with evidence rather than shame.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Separate process from outcome, record emotion and rule adherence, identify FOMO or revenge behavior, and review repeated errors with evidence rather than shame.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Calling every winner good, hiding discretionary changes, increasing frequency after boredom, and using the journal only when something goes wrong.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: pre-trade state; plan adherence; emotion; impulse; rule exception; outcome; lesson; next controlled experiment.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:23-psychology-journaling -->

<!-- CHANNEL:24-backtesting-statistics -->
# Applied Expansion · Backtesting, Statistics, and System Development

## Applied decision framework
Measure sample size, expectancy, payoff ratio, profit factor, drawdown, MAE/MFE, slippage, regime dependence, in-sample versus out-of-sample results, and uncertainty.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Measure sample size, expectancy, payoff ratio, profit factor, drawdown, MAE/MFE, slippage, regime dependence, in-sample versus out-of-sample results, and uncertainty.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Optimizing many variables, selecting only favorable dates, ignoring failed fills, promoting on win rate alone, and changing several rules at once.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: test version; hypothesis; one changed variable; sample; train/test split; costs; expectancy; drawdown; promotion decision.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:24-backtesting-statistics -->

<!-- CHANNEL:25-brokers-accounts-taxes -->
# Applied Expansion · Brokers, Accounts, Taxes, and Rules

## Applied decision framework
Verify account type, options approval, settlement, buying power, day-trading restrictions, exercise handling, records, cost basis, and current tax or regulatory guidance.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Verify account type, options approval, settlement, buying power, day-trading restrictions, exercise handling, records, cost basis, and current tax or regulatory guidance.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Assuming platform labels are legal advice, confusing settled cash with buying power, overlooking assignment funding, and using outdated tax rules.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: broker rule source; account type; buying power; settlement date; approval level; recordkeeping; rule verification date.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:25-brokers-accounts-taxes -->

<!-- CHANNEL:26-research-data-tools -->
# Applied Expansion · Research, Data, Tools, and News Verification

## Applied decision framework
Prefer primary sources, record timestamps, distinguish discovery feeds from verified claims, check API limitations, and preserve the source used in each decision.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Prefer primary sources, record timestamps, distinguish discovery feeds from verified claims, check API limitations, and preserve the source used in each decision.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Treating a headline aggregator as proof, mixing delayed and live data, ignoring symbol changes, storing claims without URLs, and hiding provider failures.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: source name; URL; published time; retrieved time; data type; confidence; limitations; claim used.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:26-research-data-tools -->

<!-- CHANNEL:27-scams-security-myths -->
# Applied Expansion · Scams, Security, and Trading Myths

## Applied decision framework
Verify identities, protect credentials, reject guaranteed returns, inspect performance denominators, and distinguish a repeatable process from screenshots or cherry-picked wins.

Use a two-column review: **observed fact** versus **interpretation**. Timestamp every fact, preserve the original source, and label unavailable evidence instead of filling gaps after the result is known. A complete decision can still be “no trade.”

## Evidence checklist
- Primary task: Verify identities, protect credentials, reject guaranteed returns, inspect performance denominators, and distinguish a repeatable process from screenshots or cherry-picked wins.
- Confirm that data timestamps match the intended holding period.
- Record supporting evidence, opposing evidence, and missing evidence separately.
- Define what observation would invalidate the interpretation before entry.
- Check liquidity, execution risk, and maximum loss even when this lesson is not mainly about orders.
- Compare the setup with the current market regime and with any scheduled event risk.

## Common failure modes
Sharing API keys, trusting urgency, paying for unverifiable signals, believing high win rate alone proves profitability, and granting excessive app permissions.

A second failure mode is **outcome leakage**: rewriting the original reasoning because the trade later won or lost. The journal must preserve what was actually known at entry.

## Journal and scanner application
Record: claim; evidence; sample; conflicts; permission requested; credential exposure; report or rejection action.

TradeBot should use these fields as evidence labels and review prompts. Missing data blocks confident claims. New knowledge can improve explanations, journal completeness, and owner-reviewed experiments, but it must not silently rewrite production filters.

## Practice drill
Take one current ticker and one historical trade. Build the checklist using only timestamped evidence available at that moment. Mark each item **confirmed**, **opposed**, **neutral**, or **missing**. Then state the no-trade condition and one controlled improvement to test without changing several variables at once.

<!-- END:27-scams-security-myths -->
