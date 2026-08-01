# Tradysquids Complete Options Learning Curriculum

Educational information only. This curriculum does not provide personalized
financial, legal, tax, or brokerage advice. Options can lose 100% of premium.
Short options and multi-leg positions can create assignment, exercise,
expiration, settlement, liquidity, margin, and gap risks.

Each `CHANNEL` section below is synchronized into the matching Discord Learning
Center channel. Keep the markers intact so the deployment tool can update the
lesson without duplicating messages.

<!-- CHANNEL:01-market-basics -->
# 01 · Market and Stock Basics

## What this topic should teach you
Before options, understand the thing underneath the option. Options amplify mistakes made at the stock, ETF, or index level. A trader who cannot explain the underlying, its liquidity, its trend, and its event risk is not ready to choose a contract.

## Stocks, ETFs, and indexes
- **Stock:** ownership in one company. Its price can react to earnings, guidance, debt, management, lawsuits, products, regulation, dividends, and industry conditions.
- **ETF:** a tradable fund that may hold stocks, bonds, commodities, futures, or a rules-based strategy. Read what it actually owns. Two ETFs with similar names can have very different risks.
- **Index:** a calculated market measure. Index options may use different settlement, exercise, tax, and trading-hour rules than ordinary equity options.
- **ADR or foreign-linked security:** may add currency, country, holiday, and political risk.

Always confirm the contract multiplier, deliverable, settlement method, exercise style, trading hours, and corporate-action history. “It has options” is not a complete product description.

## How markets trade
Regular trading hours usually have the best liquidity. Premarket and after-hours sessions often have wider spreads, lower volume, and more violent reactions to news. Options themselves may not trade during every extended session even when the underlying does.

The market is an auction:
- Buyers display bids.
- Sellers display asks.
- Trades occur when prices meet.
- The **last price** may be old and may not be available now.
- The **midpoint** is a reference, not a promised fill.
- Displayed size can disappear or change.

## Quote fields
Know these before reading any setup:
- **Bid / ask:** current displayed buying and selling prices.
- **Spread:** ask minus bid. Wider spreads create more friction.
- **Volume:** shares traded during the current session.
- **Average volume:** typical activity used for comparison.
- **Relative volume:** current activity compared with normal activity.
- **Float:** shares generally available for public trading.
- **Market capitalization:** share price multiplied by shares outstanding.
- **52-week range:** context, not a forecast.
- **Short interest:** can affect volatility but does not guarantee a squeeze.

## Order types
- **Market order:** prioritizes execution, not price. Dangerous in wide option spreads.
- **Limit order:** sets the worst acceptable price. It may not fill.
- **Stop order:** becomes a market order after triggering and can fill far from the stop.
- **Stop-limit order:** controls price but may not fill during a gap.
- **Multi-leg limit order:** sends a spread as one net debit or credit and is usually safer than legging into it.

## Liquidity and slippage
Liquidity determines whether a theoretical trade can be entered and exited at reasonable prices. A chart can look perfect while the option chain is unusable. Watch:
- Underlying share volume
- Option bid/ask width
- Contract volume and open interest
- Displayed size
- Fill quality at entry and exit
- Whether prices move when only a few contracts trade

Slippage belongs in risk calculations. A planned $20 loss can become larger when the spread widens or the market gaps.

## Corporate actions and events
Track earnings, dividends, splits, reverse splits, mergers, spin-offs, symbol changes, bankruptcies, tender offers, and trading halts. These can change option deliverables or create adjusted contracts that no longer represent a standard 100-share package.

## Worked example
A $12 stock is not automatically safer than a $400 ETF. The $12 stock may have weak liquidity, a small float, wide option spreads, and earnings tomorrow. The higher-priced ETF may have millions of shares traded and penny-wide option markets. Risk comes from position structure and liquidity, not the number printed beside the ticker.

## Common beginner mistakes
- Buying an option because the stock price looks cheap
- Using the last option trade as the current price
- Ignoring earnings or dividends
- Trading a ticker without understanding what it represents
- Treating support or resistance as guaranteed
- Entering multiple correlated positions and calling them diversified
- Using market orders in thin contracts

## Before moving on
You should be able to explain:
1. What the underlying is.
2. Why it moves.
3. When it trades.
4. Whether it is liquid.
5. Its next major event.
6. The level that invalidates your idea.
7. Why an option is better than simply trading shares for this setup.
<!-- END:01-market-basics -->

<!-- CHANNEL:02-options-basics -->
# 02 · Options Contract Basics

## The contract
An option is a contract tied to an underlying asset. It has a call-or-put type, strike price, expiration date, premium, multiplier, exercise style, and settlement method.

- A **call buyer** receives the right, but not the obligation, to buy under the contract terms.
- A **put buyer** receives the right, but not the obligation, to sell under the contract terms.
- An option **seller** accepts the corresponding obligation if assigned.

For a standard U.S. equity option, one contract usually represents 100 shares. A quoted premium of $0.45 normally means $45 per contract before fees. Adjusted contracts can have different deliverables, so always verify the contract details.

## Long versus short
**Long option**
- You paid premium.
- Maximum loss is generally the premium paid.
- You need the move, timing, and volatility behavior to cooperate.
- The option can expire worthless.

**Short option**
- You received premium.
- You accepted an obligation.
- Loss can exceed the credit and may be substantial or unlimited depending on the structure.
- Assignment can occur before expiration for many equity options.

“Buying” and “selling” do not by themselves describe risk. Buying to close reduces a short position. Selling to close exits a long position. The opening or closing instruction matters.

## Contract anatomy
- **Underlying:** the stock, ETF, or index tied to the contract.
- **Strike:** the contract price used for exercise or settlement.
- **Expiration:** the date the contract ends.
- **DTE:** days to expiration.
- **Premium:** the option’s quoted price per share.
- **Multiplier:** commonly 100, but verify.
- **OCC symbol:** encodes underlying, expiration, call or put, and strike.
- **Exercise style:** American-style contracts may generally be exercised before expiration; European-style contracts generally exercise only at expiration.
- **Settlement:** may deliver shares or settle in cash.

## Moneyness
For calls:
- ITM when underlying price is above the strike.
- ATM when price is near the strike.
- OTM when price is below the strike.

For puts:
- ITM when underlying price is below the strike.
- ATM when price is near the strike.
- OTM when price is above the strike.

Moneyness is not profitability. A call can be ITM and still lose money if too much premium was paid.

## Intrinsic and extrinsic value
**Intrinsic value** is immediate exercise value.
- Call intrinsic value = max(underlying price − strike, 0)
- Put intrinsic value = max(strike − underlying price, 0)

**Extrinsic value** is premium beyond intrinsic value. It reflects time, implied volatility, rates, dividends, and supply and demand. Extrinsic value approaches zero by expiration, but the path is not smooth.

## Expiration breakeven
For one long call:
- Breakeven at expiration = strike + premium paid.

For one long put:
- Breakeven at expiration = strike − premium paid.

These are expiration calculations. Before expiration, remaining time and volatility can make the position profitable or unprofitable away from that breakeven.

## Worked example: long call
Stock: $20  
Call strike: $20  
Premium: $0.80  
Contract cost: $80

At expiration:
- Stock at $18: option expires worthless, loss = $80.
- Stock at $20.50: intrinsic value = $0.50, contract value = $50, loss = $30.
- Stock at $20.80: expiration breakeven.
- Stock at $22: intrinsic value = $2, contract value = $200, profit = $120 before fees.

Before expiration, the option’s value can differ because time and IV remain.

## Exercise versus selling
Most traders exit a profitable long option by selling it to close rather than exercising it. Exercise can require enough capital to buy or short 100 shares per contract and may surrender remaining extrinsic value. Always understand the broker’s exercise and assignment procedures.

## Common beginner mistakes
- Confusing selling to close with selling naked
- Assuming an ITM option must be profitable
- Ignoring the 100-share multiplier
- Choosing expiration only because it is cheapest
- Holding through expiration without understanding assignment
- Believing defined premium risk means high probability
- Forgetting that the option can lose despite correct direction

## Before moving on
You should be able to identify every field in an option symbol, state the rights and obligations of each side, calculate long-option maximum loss and expiration breakeven, and explain why time and IV matter before expiration.
<!-- END:02-options-basics -->

<!-- CHANNEL:03-option-chain -->
# 03 · Reading an Option Chain

## Why the chain matters
The chart tells you about the underlying. The option chain tells you whether a tradeable contract exists. A strong stock setup can become a poor options trade when the contract is illiquid, overpriced, too short-dated, or badly matched to the expected move.

## Start with expiration
Expiration should match the thesis and expected holding period.
- Very short DTE is cheaper but usually carries faster theta and higher gamma.
- More DTE costs more but gives the thesis more time.
- Event dates can make one expiration unusually expensive.
- A spread’s short and long legs must use the intended expiration or expirations.

Ask:
1. How long should the underlying move take?
2. Is there earnings, a dividend, or a macro event before expiration?
3. How much time remains if the entry is early or late?
4. Will the position be closed before expiration?

## Strike selection
Strike affects:
- Intrinsic versus extrinsic value
- Delta and gamma
- Cost
- Probability of expiring ITM
- Liquidity
- Breakeven
- Maximum profit or loss for spreads

Do not select a strike only because it is cheap. Far-OTM options often require a large move and can have weak liquidity.

## Price columns
- **Bid:** best displayed price buyers currently offer.
- **Ask:** best displayed price sellers currently request.
- **Midpoint:** average of bid and ask, useful as a starting reference.
- **Last:** most recent trade, which may be stale.
- **Bid/ask size:** displayed contract quantities at those prices.
- **Net change:** change from prior close, which can be distorted by stale marks.

For a long option, the ask approximates the cost of immediate execution and the bid approximates immediate exit value. This is why a contract can show an instant paper loss after purchase.

## Liquidity fields
- **Volume:** contracts traded today.
- **Open interest:** contracts that remained open after the prior clearing cycle.
- **Spread width:** ask minus bid.
- **Spread percentage:** width divided by midpoint.

Volume and open interest are not directional signals. They are evidence about activity and potential liquidity. A contract with high OI can still have a wide spread.

## Greeks and IV
The chain may show delta, gamma, theta, vega, rho, and implied volatility. These are model estimates and may vary by provider. Use them to compare contracts, not as promises.

Compare:
- Delta across strikes
- Theta across expirations
- IV around events
- Skew between puts and calls
- Whether the chosen contract has enough sensitivity for the expected move

## Option symbols
Before ordering, verify:
- Underlying
- Expiration year, month, and day
- Call or put
- Strike
- Quantity
- Buy or sell
- Open or close

A one-character mistake can create a completely different position.

## Multi-leg chains
For spreads, evaluate the structure as one position:
- Net debit or credit
- Width between strikes
- Maximum profit
- Maximum loss
- Breakeven
- Combined Greeks
- Liquidity of every leg
- Assignment and expiration risk

The individual leg marks can look attractive while the executable net price is poor.

## Worked contract comparison
Underlying: $50 with a bullish swing thesis expected to take two weeks.

Contract A:
- 5 DTE
- $52 strike
- Delta 0.22
- Bid $0.18 / ask $0.40
- OI 20

Contract B:
- 30 DTE
- $50 strike
- Delta 0.53
- Bid $2.10 / ask $2.18
- OI 3,000

Contract A is cheaper, but it needs a fast move, has a 22-cent spread on a low-priced option, and weak OI. Contract B costs more but better matches the holding period and has far better liquidity. “Cheaper” did not mean “better.”

## A practical liquidity checklist
Prefer contracts where:
- Bid is greater than zero.
- Ask is not absurdly far from bid.
- Spread percentage is reasonable for the strategy.
- Volume or OI is meaningful.
- Multiple nearby strikes are active.
- The underlying itself is liquid.
- The exit can likely be executed without giving up most of the expected gain.

## Common beginner mistakes
- Buying the cheapest OTM strike
- Using last price instead of bid and ask
- Ignoring expiration date
- Treating OI as bullish or bearish
- Assuming midpoint fills are guaranteed
- Focusing on delta while ignoring theta and IV
- Entering one spread leg at a time without understanding leg risk

## Before moving on
You should be able to compare two contracts and explain which better fits the expected move, time horizon, liquidity requirement, and risk limit.
<!-- END:03-option-chain -->

<!-- CHANNEL:04-pricing-and-greeks -->
# 04 · Option Pricing and the Greeks

## What creates option value
Option premium is not merely “stock direction.” It reflects:
- Underlying price
- Strike
- Time to expiration
- Implied volatility
- Interest rates
- Dividends
- Supply and demand
- Contract specifications

Premium = intrinsic value + extrinsic value.

A trader can predict direction correctly and still lose because the move was too small, too slow, or accompanied by an IV decline.

## Delta
Delta estimates the option’s price change for a $1 move in the underlying, all else equal.
- Calls generally have positive delta.
- Puts generally have negative delta.
- A 0.50 call delta suggests roughly $0.50 of option movement for a $1 stock move at that instant.
- Delta changes continuously.

Delta is sometimes used as a rough probability proxy, but it is not an exact probability of profit, exercise, or expiring ITM.

**Share-equivalent exposure:** one standard contract with 0.50 delta has roughly 50 shares of directional exposure at that moment.

## Gamma
Gamma estimates how much delta changes for a $1 underlying move.
- Gamma is usually highest near the money.
- Gamma tends to become more intense close to expiration.
- Long options are generally long gamma.
- Short options are generally short gamma.

High gamma makes position behavior accelerate. A contract can move from low delta to high delta quickly, which helps when the move is favorable and hurts when it is not.

## Theta
Theta estimates the effect of one day passing, all else equal.
- Long options generally have negative theta.
- Short options generally have positive theta.
- Decay is not constant.
- ATM options often carry significant time value.
- Near expiration, time can become a brutal opponent for long premium.

Theta is an estimate, not a daily fee charged at midnight. Price, IV, and other inputs change simultaneously.

## Vega
Vega estimates the premium change for a one-percentage-point change in IV.
- Long options are generally long vega.
- Short options are generally short vega.
- Longer-dated options usually have more vega than very short-dated options.

A long call can lose after bullish earnings if the stock rise is smaller than expected and IV collapses.

## Rho
Rho estimates sensitivity to interest-rate changes. It is often smaller than the other major Greeks for short-dated equity options but can matter more for long-dated contracts and rate-sensitive products.

## Advanced Greeks
Advanced traders may track:
- **Charm:** change in delta as time passes.
- **Vanna:** interaction between delta and IV.
- **Vomma:** change in vega as IV changes.
- **Speed:** change in gamma as price changes.
- **Color:** change in gamma as time passes.

These are useful for deeper risk analysis, but they do not replace the basic question: what happens if price, time, and IV move against you?

## Greeks for spreads
A spread’s Greeks are the sum of its legs.
- A bull call debit spread is positive delta but has capped upside.
- A bull put credit spread is also positive delta, often positive theta, and may be short vega.
- An iron condor may begin near delta-neutral but can acquire strong directional exposure as price approaches a short strike.
- A calendar may be long vega and positive theta near one price but behave differently after a move.

The opening Greeks are not permanent.

## Scenario analysis
Suppose a call is priced at $2.00 with:
- Delta 0.50
- Gamma 0.08
- Theta −0.06
- Vega 0.10

Approximate one-step effects, treated separately:
- Underlying rises $1: option gains about $0.50 initially.
- One day passes: option loses about $0.06.
- IV drops 3 points: option loses about $0.30.
- After the price rise, delta may increase by about 0.08 because of gamma.

These estimates are not perfectly additive because the inputs interact and the Greeks change.

## Portfolio Greeks
Multiple positions can create hidden exposure:
- Five bullish calls may create far more delta than expected.
- Several short-premium spreads may create large short-vega and short-gamma risk.
- Different tickers in the same sector may move together.
- A “neutral” portfolio can become directional after a market move.

Track total delta, gamma, theta, vega, maximum loss, and correlation.

## Common beginner mistakes
- Treating delta as a guaranteed probability
- Ignoring gamma in 0DTE or near-expiration contracts
- Assuming theta helps every credit spread equally
- Buying high IV without considering crush
- Looking at each leg instead of net Greeks
- Believing Greeks remain fixed
- Using one Greek to justify a trade while ignoring maximum loss

## Before moving on
You should be able to describe how price, time, and IV affect a long option and a credit spread, and explain why the same directional view can be expressed with different Greek profiles.
<!-- END:04-pricing-and-greeks -->

<!-- CHANNEL:05-volatility -->
# 05 · Volatility and Implied Volatility

## Realized versus implied volatility
**Historical or realized volatility** describes how much the underlying actually moved over a past period.

**Implied volatility (IV)** is the volatility input backed out from option prices. It reflects the movement currently priced by the options market, not a forecast of direction.

IV can rise before uncertain events and fall after uncertainty is resolved. It can also remain elevated when risk persists.

## Why IV changes premium
Higher IV generally increases the value of both calls and puts because a wider range of future outcomes is being priced. Lower IV generally reduces extrinsic value.

This creates a second contest beyond direction:
- Long premium usually benefits from IV expansion and suffers from IV contraction.
- Short premium usually benefits from IV contraction but can suffer badly when IV and realized movement expand.

## Expected move
Traders often estimate an expected move using an at-the-money straddle, provider model, or an IV-based formula. These methods estimate magnitude, not direction, and are not boundaries.

A stock can move beyond the expected range. It can also move less than expected, causing long event premium to lose despite the correct directional guess.

## IV rank and IV percentile
**IV rank** compares current IV with the highest and lowest IV over a chosen lookback.

A common form is:
(current IV − period low) / (period high − period low)

**IV percentile** estimates the percentage of lookback observations below current IV.

Both depend heavily on:
- Lookback period
- Data source
- Whether a brief spike dominates the range
- Which IV measurement is used

High rank does not mean IV must fall. Low rank does not mean IV must rise.

## Skew, smile, and smirk
IV differs across strikes.
- Downside puts often carry higher IV because investors pay for protection.
- Individual stocks may show event-driven call demand.
- Deep ITM and OTM options can have different model behavior.

This strike-by-strike shape is volatility skew or smile. Compare the actual legs of a strategy rather than relying on one headline IV number.

## Term structure
IV also differs across expirations.
- An earnings expiration may be expensive while later expirations are calmer.
- A known court ruling, product launch, or macro event can create a hump in the curve.
- Front-month IV can collapse after an event while back-month IV remains elevated.

Calendars and diagonals depend heavily on this relationship.

## IV crush
IV crush is a sharp post-event decline in implied volatility. It commonly follows earnings or major announcements when uncertainty is removed.

Example:
- Stock rises 3%.
- The options market had priced a 6% move.
- Near-term IV collapses.
- A long call can lose because the move was smaller than priced and vega/theta losses offset delta gains.

The market did not “cheat.” The option was priced for more movement than occurred.

## Volatility risk premium
Option sellers often seek the difference between implied and realized volatility. That edge is not free:
- Losses can be infrequent but large.
- Gaps can bypass stops.
- Short gamma causes exposure to worsen as price moves.
- Correlation can spike during market stress.

A high win rate can coexist with poor expectancy.

## Strategy fit
Potential long-volatility structures:
- Long calls or puts
- Long straddles or strangles
- Some calendars or diagonals

Potential short-volatility structures:
- Credit spreads
- Iron condors
- Short straddles or strangles
- Covered calls and cash-secured puts

Every structure also has delta, gamma, theta, assignment, and liquidity risk.

## Practical volatility checklist
Before entry:
1. Compare IV with its own history.
2. Compare the chosen strike with nearby strikes.
3. Compare the chosen expiration with nearby expirations.
4. Identify scheduled events.
5. Estimate what move is already priced.
6. Decide whether you are long or short vega.
7. Model IV up, IV down, price up, price down, and time passing.
8. Plan the exit if the event move is smaller than expected.

## Common beginner mistakes
- Thinking IV predicts direction
- Buying options before earnings because “a big move is coming”
- Selling premium because IV is high without defining max loss
- Comparing IV across unrelated tickers as if identical
- Ignoring skew and term structure
- Assuming IV crush affects every expiration equally
- Treating expected move as support and resistance

## Before moving on
You should be able to explain why a correct directional trade can lose after an event and identify whether a position is long or short volatility.
<!-- END:05-volatility -->

<!-- CHANNEL:06-charts -->
# 06 · Charts, Candles, and Timeframes

## What a chart is
A chart is a compressed record of transactions. It describes what happened; it does not guarantee what happens next. Charts are useful when they convert price behavior into a clear thesis, invalidation, target, and time horizon.

## Candles
Each candle shows:
- Open
- High
- Low
- Close

The body shows the distance between open and close. Wicks show prices reached during the period. A long wick can show rejection, but context matters. One candle without trend, level, volume, and follow-through is weak evidence.

## Timeframes
Use timeframes that match the trade:
- Seconds or 1-minute charts: execution detail and heavy noise.
- 2- to 15-minute charts: intraday structure.
- Hourly charts: multi-day context.
- Daily charts: swing and broader trend.
- Weekly charts: long-term structure.

A bullish 2-minute chart can be a tiny bounce inside a bearish daily trend. Use a higher timeframe for context and a lower timeframe for entry only when their roles are defined.

## Market structure
Bullish structure often includes higher highs and higher lows.
Bearish structure often includes lower highs and lower lows.
A range has repeated rejection near boundaries without sustained progress.

Learn:
- Trend
- Pullback
- Consolidation
- Breakout
- Failed breakout
- Reversal
- Gap
- Retest
- Compression and expansion

Do not label every pause a reversal.

## Support and resistance
Support and resistance are zones where behavior previously changed. They can come from:
- Prior highs and lows
- Gap boundaries
- High-volume areas
- VWAP or anchored VWAP
- Moving averages
- Trendlines
- Round numbers
- Previous day or week levels

A useful level includes:
1. Why it matters.
2. What confirms it.
3. What invalidates it.
4. Where risk is placed.
5. Where the next opposing level sits.

## Volume
Volume helps judge participation.
- Breakout with increasing relative volume may have stronger participation.
- Low-volume moves can fail, though not always.
- Climax volume may accompany exhaustion or continuation.
- Volume must be compared with normal activity for that ticker and time of day.

Option volume does not replace underlying volume analysis.

## Gaps
A gap is a price area skipped between sessions or during a halt.
Types include:
- Common gap
- Breakaway gap
- Continuation gap
- Exhaustion gap

These labels are only useful after evidence develops. “All gaps fill” is a myth.

## Chart indicators
Indicators should answer specific questions:
- Moving averages: trend and slope
- VWAP: session positioning
- RSI/MACD: momentum
- ATR/Bollinger Bands: volatility
- Volume profile: traded volume by price

Too many indicators derived from the same price data create the illusion of confirmation.

## Chart construction
A clean chart usually needs:
- Price and volume
- A small number of relevant levels
- One or two indicators with defined jobs
- Visible session boundaries
- Consistent timeframe and data adjustments
- No labels covering current price

A chart should help make a decision, not resemble the cockpit of a submarine designed by a committee.

## Worked example
Daily chart:
- Uptrend above rising 20- and 50-day averages.
- Pullback reaches prior breakout zone.
- Earnings are three weeks away.

15-minute chart:
- Price holds the daily support zone.
- Higher low forms.
- Volume increases on reclaim of VWAP.

This supports a bullish thesis. Invalidation is a sustained break below the daily support zone. Contract selection should then match the expected swing duration and event date.

## Common beginner mistakes
- Using a timeframe too short for the intended hold
- Drawing levels after the move and claiming prediction
- Treating a single candle as a setup
- Ignoring extended-hours gaps
- Confusing a pullback with a reversal
- Adding indicators until one agrees
- Moving the invalidation level after entry

## Before moving on
You should be able to describe trend, range, key levels, volume behavior, timeframe alignment, and a specific invalidation without mentioning an option contract.
<!-- END:06-charts -->

<!-- CHANNEL:07-technical-analysis -->
# 07 · Technical Analysis

## Purpose
Technical analysis organizes price, volume, momentum, and volatility into repeatable observations. It does not provide certainty. A useful indicator changes an action: entry, avoidance, sizing, stop placement, target, or exit.

## Trend tools
### Simple moving average
An SMA averages closing prices over a chosen period. It is stable but lagging.

### Exponential moving average
An EMA weights recent prices more heavily and reacts faster, which also makes it more sensitive to noise.

### Slope and structure
A moving average crossing another average matters less than:
- Price location
- Average slope
- Higher highs or lower lows
- Distance from the average
- Market regime

In a strong trend, “overextended” can remain overextended.

## VWAP
VWAP is the volume-weighted average price for a session or anchor.
- Above VWAP can suggest buyers control the session.
- Below VWAP can suggest sellers control it.
- Repeated crosses can signal a choppy market.
- Anchored VWAP can measure positioning from an event, low, high, or earnings gap.

VWAP is not a magical support line.

## RSI
RSI measures recent momentum on a 0–100 scale.
- High RSI may mean strong momentum, not an automatic sell.
- Low RSI may mean strong selling, not an automatic buy.
- Divergence can warn of weakening momentum but may persist for a long time.

Use RSI with trend and structure.

## MACD
MACD compares moving-average relationships.
- The MACD line, signal line, and histogram describe momentum changes.
- It lags price.
- Crosses in ranges can create repeated false signals.
- A histogram turn is not enough without price confirmation.

## ATR
Average True Range estimates recent movement size.
Uses:
- Comparing volatility across time
- Building stops that respect normal noise
- Estimating realistic targets
- Identifying expansion or contraction

ATR does not predict direction.

## Bollinger Bands
Bands are commonly built around a moving average using standard deviation.
- Narrow bands show contraction.
- Wide bands show expansion.
- Price touching a band is not automatically a reversal.
- “Walking the band” can occur in strong trends.

## Volume and relative volume
Volume indicates participation. Relative volume compares current volume with normal activity.
- A breakout with strong relative volume can be more credible.
- A reversal on heavy volume may signal transfer of control.
- Volume patterns differ by time of day.

## Divergence
Divergence occurs when price and an indicator move differently.
- Bullish divergence: price makes a lower low while momentum does not.
- Bearish divergence: price makes a higher high while momentum does not.

Divergence is a warning, not an entry. Wait for structure and confirmation.

## Confluence
Confluence means independent evidence supports the same thesis:
- Higher-timeframe trend
- Key level
- Volume behavior
- Momentum
- Catalyst
- Reasonable option pricing

Three indicators based on the same closing prices are not independent evidence.

## Regimes
Strategies behave differently in:
- Trending markets
- Ranges
- High volatility
- Low volatility
- Event-driven markets
- Broad risk-on or risk-off conditions

A system should identify when it has no edge and produce **NO TRADE**.

## Multi-timeframe workflow
1. Weekly or daily: broad trend and major levels.
2. Hourly: intermediate structure.
3. Intraday: setup and timing.
4. Execution timeframe: precise entry and risk.

Do not let a tiny timeframe overrule the larger thesis without a defined reason.

## Building an indicator rule
A rule should specify:
- Exact inputs
- Timeframe
- Required condition
- Confirmation
- Invalidation
- Session restrictions
- Event restrictions
- Exit logic
- How it is tested

“RSI looks good” is not a rule.

## Common beginner mistakes
- Using overbought as an automatic short signal
- Chasing a crossover after price already moved
- Optimizing settings until history looks perfect
- Ignoring regime and volume
- Counting correlated indicators as separate confirmation
- Changing rules during a losing trade
- Treating indicator labels as financial advice

## Before moving on
You should be able to explain what each indicator measures, what it fails to measure, and how it changes a specific decision.
<!-- END:07-technical-analysis -->

<!-- CHANNEL:08-strategies -->
# 08 · Core Options Strategies

## Choose the structure after the thesis
Start with:
1. Direction: bullish, bearish, neutral, or uncertain.
2. Magnitude: small, moderate, or large expected move.
3. Timing: hours, days, weeks, or months.
4. Volatility view: IV likely to rise, fall, or remain stable.
5. Risk limit and assignment tolerance.
6. Event policy.
7. Liquidity.

Then choose a structure. Starting with “I want to sell a put” and searching for a justification is backward.

## Long call
View: bullish.  
Risk: premium paid.  
Needs: sufficient upward move before time and IV work against it.  
Watch: delta, theta, vega, DTE, liquidity, event risk.

A long call is not simply leveraged stock. Its sensitivity changes and it can lose when the stock rises too slowly.

## Long put
View: bearish or protective.  
Risk: premium paid.  
Needs: sufficient decline before expiration.  
Watch: elevated put IV, skew, theta, and rebound risk.

## Covered call
Position: 100 shares plus one short call.
- Collects premium.
- Caps upside above the strike.
- Retains most stock downside.
- Can be assigned early, especially around dividends.

It is not free income. The largest risk usually remains the shares.

## Cash-secured put
Position: short put with cash reserved to buy shares.
- Profit is limited to premium.
- Loss can be substantial if shares fall far below strike.
- Assignment means buying shares at the strike.

Only use it when willing and able to own the shares at the effective cost basis. “I would not mind owning it” should survive a 30% decline, not just sound pleasant at entry.

## Protective put
Position: long shares plus long put.
- Limits downside below the put strike during its life.
- Costs premium.
- Protection expires.
- Repeated hedging can reduce long-term returns.

## Collar
Position: shares plus long put plus short call.
- Put defines downside protection.
- Short call helps finance the put.
- Upside is capped.
- Strike and expiration selection determine the trade-off.

## Long straddle
Buy call and put at the same strike and expiration.
- Long volatility and long gamma.
- Needs a large move or IV expansion.
- Suffers theta.
- Two premiums create wide breakevens.

## Long strangle
Buy OTM call and OTM put.
- Cheaper than a straddle.
- Requires a larger move to reach profitability.
- Sensitive to IV and time decay.

Short straddles and strangles reverse these exposures and can carry substantial or unlimited risk. They are inappropriate without advanced risk controls.

## Synthetic stock
A long call plus short put at the same strike and expiration can approximate long-share exposure. It includes short-option assignment and margin risk. Synthetic positions are not “cheap stock”; they reproduce leverage and obligations in another form.

## LEAPS and stock replacement
Long-dated calls can provide long exposure with less capital than shares, but:
- They expire.
- They have vega and theta.
- Deep ITM liquidity can be uneven.
- Dividends are not received.
- Delta is less than or near one, not guaranteed one.

## Strategy comparison
| Structure | Typical view | Max loss | Main hidden risk |
|---|---|---:|---|
| Long call | Bullish | Premium | Time and IV |
| Long put | Bearish | Premium | Time and rebound |
| Covered call | Mild bullish/neutral | Large stock loss | Capped upside |
| Cash-secured put | Mild bullish | Large share loss | Assignment |
| Protective put | Bullish with hedge | Stock loss above floor + premium | Hedge cost |
| Long straddle | Large move | Both premiums | Move smaller than priced |

## Trade-selection example
Bullish thesis, expected two-week move, IV elevated before earnings in three days:
- Long call: exposed to IV crush.
- Bull call debit spread: lowers cost and vega but caps upside.
- Bull put credit spread: can benefit if price holds above support, but adds short-option and assignment risk.
- Wait until after earnings: eliminates event gap risk but may miss the move.

The best structure depends on the actual thesis, not a universal ranking.

## Common beginner mistakes
- Using covered calls on shares they cannot tolerate falling
- Selling puts only because premium is high
- Buying straddles without checking priced expected move
- Treating LEAPS as permanent
- Ignoring assignment
- Choosing a strategy before defining the market view
- Comparing strategies only by maximum profit

## Before moving on
For every strategy, state maximum profit, maximum loss, breakeven, directional bias, Greek exposure, capital requirement, assignment risk, event policy, and exit plan.
<!-- END:08-strategies -->

<!-- CHANNEL:09-spreads -->
# 09 · Spreads and Multi-Leg Positions

## What a spread does
A spread combines options to reshape cost, maximum loss, maximum profit, and Greek exposure. Defined risk is not the same as small risk. A $5-wide spread can still lose nearly $500 per contract.

Use a single multi-leg limit order whenever possible. Legging in creates execution and directional risk.

## Vertical debit spreads
Same expiration, different strikes, net premium paid.

### Bull call debit spread
Buy lower-strike call, sell higher-strike call.
- Bullish
- Max loss = debit paid × 100
- Max profit = (width − debit) × 100
- Expiration breakeven = long call strike + debit

### Bear put debit spread
Buy higher-strike put, sell lower-strike put.
- Bearish
- Max loss = debit
- Max profit = width − debit
- Breakeven = long put strike − debit

Debit spreads reduce cost and vega compared with a naked long option but cap profit.

## Vertical credit spreads
Same expiration, different strikes, net premium received.

### Bull put credit spread
Sell higher-strike put, buy lower-strike put.
- Bullish or neutral
- Max profit = credit × 100
- Max loss = (width − credit) × 100
- Breakeven = short put strike − credit

### Bear call credit spread
Sell lower-strike call, buy higher-strike call.
- Bearish or neutral
- Max profit = credit
- Max loss = width − credit
- Breakeven = short call strike + credit

Credit received is not the amount at risk. The short leg can be assigned.

## Worked example
Sell 45 put, buy 44 put for $0.20 credit:
- Width = $1
- Max profit = $20
- Max loss = $80
- Breakeven = $44.80

A 90% “probability-looking” setup can still have poor expectancy when the occasional $80 loss overwhelms repeated $20 wins.

## Calendars
Same strike, different expirations. Typically buy later expiration and sell nearer expiration.
- Sensitive to price location at front expiration
- Often long vega
- Front option decays faster
- Term structure matters
- Short leg can be assigned

The long option does not guarantee protection against every short-leg outcome.

## Diagonals
Different strikes and expirations.
Examples include the so-called poor man’s covered call.
- Mixes directional, volatility, and time-spread exposure
- Requires management of the front short option
- Can suffer if the underlying moves too far or IV relationships change
- Assignment can create shares or a short-share position

## Iron condor
Sell OTM put spread and OTM call spread.
- Range-focused
- Limited credit
- Defined but real maximum loss
- Short gamma and often short vega
- Four-leg liquidity and commissions matter

A condor can begin delta-neutral and become strongly directional near a short strike.

## Butterfly
Three strikes, usually 1:2:1 quantity.
- Narrow target zone
- Low debit or defined credit depending on structure
- High sensitivity near expiration
- Can be difficult to fill and exit

Broken-wing butterflies alter wing widths to shift risk and credit.

## Ratio and backspreads
Unequal quantities create nonlinear risk.
- Ratio spreads can contain uncovered short-option risk.
- Backspreads may be long gamma but can have a loss valley.
- Margin and assignment can be complex.

These require exact payoff modeling.

## Leg risk
If one leg fills and another does not:
- The position can become naked.
- Delta and maximum loss can change dramatically.
- Margin requirements can increase.
- The market can move before completion.

Avoid manually legging into spreads unless the temporary position is fully understood and acceptable.

## Expiration risk
Holding spreads into expiration can create:
- One leg assigned while another expires
- Pin risk near the short strike
- After-hours price changes
- Broker liquidation
- Temporary share exposure larger than account value

Closing before expiration can reduce, but not eliminate, these risks.

## Rolling
Rolling means closing one position and opening another.
- It realizes the first trade’s gain or loss.
- It changes strikes, expiration, or both.
- It can add risk or capital.
- A net credit does not erase the original loss.

Record both trades separately.

## Spread checklist
Before entry:
1. Verify every leg.
2. Calculate executable net debit or credit.
3. Calculate max profit, max loss, and breakeven.
4. Check liquidity of every leg.
5. Review combined Greeks.
6. Define profit target, stop, time stop, and close-by date.
7. Understand assignment and settlement.
8. Confirm buying-power effect.

## Common beginner mistakes
- Calling credit “profit”
- Ignoring spread width
- Holding through expiration without a plan
- Assuming the protective leg prevents assignment
- Entering legs separately
- Rolling repeatedly to avoid admitting a loss
- Using four-leg strategies in illiquid chains
<!-- END:09-spreads -->

<!-- CHANNEL:10-risk-management -->
# 10 · Risk Management and Position Sizing

## The purpose of risk management
A strategy does not survive because every trade wins. It survives because losses are bounded, correlated exposure is controlled, and the trader remains financially and emotionally able to continue.

Risk rules must be decided before entry, not invented while the position is red.

## Maximum loss versus planned loss
**Maximum loss** is the worst contractual outcome under the structure, excluding unusual operational complications.

**Planned loss** is the amount expected if the stop or invalidation works.

They are not the same. Stops can gap, options can widen, and brokers can liquidate. Position size should remain survivable even when planned exits fail.

## Position-size formula
A simple starting framework:

contracts = floor(maximum dollars willing to lose / planned loss per contract)

For a long option:
planned loss per contract ≈ (entry premium − stop premium) × 100 + estimated costs

For a defined-risk spread:
also compare with contractual maximum loss. Never size only from the planned stop.

## Risk layers
Set limits for:
- One trade
- One ticker
- One sector
- One strategy
- One day
- One week
- Total open portfolio
- Maximum drawdown
- Event exposure

A portfolio with ten bullish technology positions is one concentrated market bet wearing ten ticker symbols.

## Correlation
Correlations often rise during market stress. Positions that appeared diversified may fall together.
Check:
- Same sector
- Same index exposure
- Same macro sensitivity
- Same event date
- Same volatility exposure
- Same directional Greeks

## Portfolio Greeks
Track aggregate:
- Delta
- Gamma
- Theta
- Vega
- Maximum loss
- Buying power
- Assignment obligations

A portfolio can be positive theta but dangerously short gamma and vega.

## Drawdown mathematics
Losses require larger percentage gains to recover:
- 10% loss needs about 11.1% gain.
- 20% loss needs 25% gain.
- 50% loss needs 100% gain.

This is why avoiding catastrophic loss matters more than chasing one spectacular trade.

## Stops
Possible stop types:
- Underlying-price invalidation
- Option-premium stop
- Spread-value stop
- Time stop
- Volatility stop
- Event stop
- Daily portfolio stop

Option-premium stops can trigger from spread noise or IV changes even when the chart thesis remains intact. Underlying-based stops can better match the thesis but still suffer execution gaps.

## Targets
Targets may use:
- Prior level
- Risk multiple
- ATR
- Percentage of premium
- Percentage of credit captured
- Time remaining
- Change in thesis

A target should reflect realistic liquidity and the structure’s payoff, not merely a round number.

## Event risk
Earnings, economic reports, court decisions, and overnight news can gap beyond stops. Reduce size, hedge, close, or intentionally accept the event. Do not accidentally hold through it.

## Assignment capacity
Short options can create 100-share obligations per contract. A “defined-risk” spread can still create temporary share exposure if one leg is assigned. Confirm the account can handle exercise and assignment.

## Risk-of-ruin thinking
High win rate does not guarantee safety. A strategy with many small wins and rare huge losses can fail. Examine:
- Average win and loss
- Worst historical loss
- Consecutive losses
- Tail events
- Slippage
- Correlation
- Whether losses cluster by regime

## Practical pre-trade checklist
- Thesis and invalidation are written.
- Maximum loss is known in dollars.
- Planned stop loss is known.
- Position size follows the smaller allowable size.
- Event calendar is checked.
- Total correlated exposure is acceptable.
- Liquidity supports exit.
- Assignment and expiration are understood.
- Losing this trade will not affect bills, emergency savings, or sleep.

## Common beginner mistakes
- Sizing from buying power
- Doubling down after a loss
- Treating defined risk as safe
- Ignoring open-position correlation
- Moving stops farther away
- Using the same size for every volatility regime
- Risking money needed for necessities
- Believing a paper stop guarantees a live fill

## Before moving on
You should be able to calculate planned and maximum loss, choose contract quantity, and explain how the trade changes total portfolio risk.
<!-- END:10-risk-management -->

<!-- CHANNEL:11-trade-management -->
# 11 · Trade Planning and Management

## Management begins before entry
A complete plan defines:
- Thesis
- Setup type
- Entry condition
- Contract and structure
- Maximum and planned loss
- Initial stop or invalidation
- Profit target
- Time stop
- Event policy
- Close-by date
- Conditions for scaling or rolling
- What data would cancel the trade

Without this, every price movement becomes an invitation to improvise.

## Entry
Good entry practice:
- Wait for the planned confirmation.
- Use a limit order.
- Check the option bid/ask immediately before sending.
- Confirm all contract fields.
- Avoid chasing after the expected reward has shrunk.
- Record the underlying and option prices at fill.

A setup can remain valid while the entry becomes poor.

## Stops and invalidation
An invalidation answers: what market behavior proves the thesis wrong?

Possible examples:
- Underlying closes below support.
- Breakout fails and price re-enters the range.
- Momentum reverses with volume.
- Spread reaches a defined loss multiple.
- Required catalyst fails to occur.
- Time remaining becomes insufficient.

A stop should not be moved simply because it is close to triggering.

## Profit targets
Methods include:
- Fixed premium percentage
- Fixed risk multiple
- Technical target
- Percentage of credit captured
- Trailing stop
- Scale-out plan
- Exit at a scheduled time or event

Targets should account for option liquidity. A displayed mark is not realized profit.

## Time stops
Options have a clock. Exit when:
- The expected move has not begun by the planned date.
- Theta is becoming too costly.
- DTE enters an unacceptable range.
- A catalyst has passed.
- The strategy no longer fits the market regime.

A flat underlying can still be a losing long-option trade.

## Scaling
Scaling in:
- Must be preplanned.
- Should not turn a small loss into an oversized hope trade.
- Requires a new risk calculation.

Scaling out:
- Realizes partial profit.
- Reduces exposure.
- Can leave a runner.
- May increase the effective cost of commissions and spreads.

Record each fill.

## Trailing stops
A trailing stop can protect gains but can also exit on normal volatility.
Possible anchors:
- Underlying swing lows/highs
- Moving average
- ATR multiple
- Option premium
- Percentage from peak

Use a method suited to timeframe and liquidity.

## Managing credit spreads
Common management rules:
- Profit target based on percentage of credit captured
- Loss limit based on spread value or underlying invalidation
- Close before a chosen DTE
- Avoid holding near short strike into expiration
- Watch assignment and dividend risk

Do not wait to earn the final few dollars when remaining risk is much larger.

## Rolling
A roll is:
1. Closing the existing position.
2. Opening a new position.

Evaluate the new trade independently:
- New maximum loss
- New buying power
- New DTE and strikes
- New event exposure
- Realized old loss
- Whether the original thesis still exists

Rolling can be useful. It can also postpone discipline.

## Overnight decisions
Hold overnight only when the plan accepts:
- Gap risk
- News risk
- Reduced ability to exit
- Next-day IV change
- Event calendar
- Full maximum loss possibility

An intraday trade should not become a swing because it is losing.

## Worked example
Plan:
- Bullish breakout above $50.
- Buy 30-DTE call only after a 15-minute close above $50 with volume.
- Invalidation: underlying below $49.20.
- Target: prior high at $53.
- Time stop: exit after five sessions if price remains below $51.
- No hold through earnings.

After entry, price reaches $51.80 then closes below $50 on heavy volume. The original breakout failed. The trade exits even if the option has not reached a fixed percentage stop.

## Post-trade review
Record:
- Planned versus actual entry
- Slippage
- Whether rules were followed
- MAE and MFE
- Exit reason
- P/L
- Screenshot
- Emotional state
- One lesson

Judge process separately from outcome.

## Common beginner mistakes
- Chasing entries
- Turning day trades into overnight holds
- Taking profits early and letting losses reach maximum
- Moving stops
- Rolling without calculating new risk
- Averaging down because premium is cheaper
- Managing from P/L instead of thesis
- Treating an unfilled midpoint as available profit
<!-- END:11-trade-management -->

<!-- CHANNEL:12-expiration-assignment -->
# 12 · Expiration, Exercise, and Assignment

## Why this topic matters
Expiration can transform a small option position into a large share obligation. Many disasters occur because the trader understood the chart but not the contract process.

## Exercise
Exercise occurs when an option holder uses the contract right.
- Call exercise generally buys shares at the strike.
- Put exercise generally sells shares at the strike.
- Exercise can require substantial cash or margin.
- Exercising can surrender remaining extrinsic value.

Selling the option to close is often operationally simpler, but the best action depends on liquidity and contract terms.

## Assignment
Assignment occurs when a short-option seller is selected to fulfill the contract.
- Short call assignment can create a short-share position or sell owned shares.
- Short put assignment can create a long-share position.
- Many American-style equity options can be assigned before expiration.
- Assignment notices may arrive after the market closes.

The protective leg of a spread does not prevent the short leg from being assigned.

## Automatic exercise
Brokers and clearing organizations may automatically exercise options that finish sufficiently ITM, subject to procedures and contrary instructions. Do not rely on a vague memory of a threshold. Verify current broker and OCC procedures.

An option can move ITM or OTM after the regular close while exercise decisions are still relevant.

## Early assignment
Common drivers include:
- Short option is deep ITM.
- Extrinsic value is very small.
- Dividend economics make call exercise attractive.
- Borrowing or rate considerations.
- Holder-specific decisions.

Assignment may occur even when it seems economically unusual.

## Ex-dividend risk
A short call can face early assignment before the ex-dividend date when the dividend exceeds remaining extrinsic value or other exercise economics favor the holder.

Covered-call traders may lose the shares and the dividend. Spread traders may receive an unexpected short-share position.

## Pin risk
Pin risk occurs when the underlying finishes near a strike and it is uncertain which options will be exercised.
Potential result:
- Some contracts exercise and others do not.
- One spread leg becomes shares while the other expires.
- Weekend news changes the share value before markets reopen.
- The account receives exposure much larger than planned.

## Settlement
Contracts may be:
- Physically settled into shares
- Cash settled
- American or European style
- AM or PM settled
- Subject to special trading hours

Index options often differ from equity options. Verify the exact product.

## Spread expiration example
Bull put spread:
- Short 50 put
- Long 49 put

Underlying closes at $49.90.
- Short 50 put may be exercised/assigned.
- Long 49 put may expire OTM.
- Trader can become long 100 shares at $50 per spread.
- Weekend price risk now exists.

The spread’s chart showed “defined risk,” but operational exposure still appeared.

## Broker actions
Brokers may:
- Close positions before expiration
- Restrict opening trades
- Submit do-not-exercise instructions
- Liquidate shares
- Charge exercise or assignment fees
- Use risk procedures that differ by account

Read the broker’s policies before expiration day, not while customer support is overloaded.

## Expiration checklist
Several days before expiration:
1. Identify every open option.
2. Mark ITM, ATM, and OTM status.
3. Review dividends and events.
4. Confirm cash, margin, and share obligations.
5. Decide close, roll, exercise, or allow expiration.
6. Check liquidity and spreads.
7. Avoid waiting for the last minutes.
8. Confirm the broker’s cutoff and procedures.

## Common beginner mistakes
- Assuming a spread can be ignored because risk is defined
- Believing OTM at 3:59 p.m. guarantees no exercise
- Forgetting dividends
- Exercising a long option with extrinsic value
- Holding cheap contracts because “there is nothing left to lose”
- Not having capital for assignment
- Confusing cash-settled index options with equity options

## Before moving on
You should be able to describe what shares or cash can appear after exercise or assignment for every leg in your position.
<!-- END:12-expiration-assignment -->

<!-- CHANNEL:13-events-and-catalysts -->
# 13 · Events and Catalysts

## Why events matter
Events can change price, liquidity, and implied volatility faster than ordinary technical signals. Stops may not protect against gaps. Every trade needs an event policy: intentionally hold, reduce, hedge, or close.

## Company events
Track:
- Earnings and guidance
- Investor days
- Product launches
- Regulatory decisions
- Lawsuits and court rulings
- Analyst upgrades or downgrades
- Management changes
- Mergers and acquisitions
- Buybacks
- Dividends
- Splits and reverse splits
- Debt offerings
- Bankruptcy or restructuring news

Confirm whether the event occurs before open, during market, or after close.

## Macro events
Examples:
- Central-bank decisions
- Inflation reports
- Employment data
- GDP
- Retail sales
- Treasury auctions
- Major political or geopolitical developments
- Industry inventory reports

A single macro event can move many correlated positions at once.

## Earnings
Earnings trades involve:
- Directional surprise
- Revenue and profit
- Guidance
- Margins
- Conference-call language
- Positioning
- Expected move
- IV crush

A company can beat estimates and fall because expectations were higher. Headlines alone do not explain price.

## Dividends
Dividends affect:
- Stock price around ex-date
- Put/call pricing
- Early call assignment
- Covered-call outcomes
- Synthetic positions

Check dividend amount and dates before holding short calls.

## Mergers and corporate actions
Deals can:
- Cap price near an offer
- Break and cause violent repricing
- Change option deliverables
- Produce adjusted contracts
- Create uncertain timing

Do not assume ordinary option behavior after a corporate action.

## Trading halts
Halts can occur for news, volatility, or regulatory reasons.
During a halt:
- Orders may not execute.
- Options can become untradeable.
- Reopening prices can gap.
- Stops provide no guaranteed protection.

## Expected move and event pricing
The option market may already price a large move. Compare:
- ATM straddle
- Provider expected move
- Historical event moves
- Current IV versus normal IV
- Skew and term structure

Historical average is not a cap.

## Holding through an event
Questions:
1. Is the trade specifically designed for the event?
2. What move is already priced?
3. What is the maximum loss if price gaps?
4. What happens if direction is correct but move is small?
5. How will IV change?
6. Can the position be exited after the event?
7. Is assignment possible?
8. Is the position size small enough for the worst case?

## Worked example
A stock trades at $100 before earnings. The nearest straddle costs $8, suggesting the market prices a large move.

Trader buys a $105 call for $3.
After earnings:
- Stock rises to $106.
- Call has $1 intrinsic value.
- IV collapses.
- The option may be worth less than the $3 paid.

The bullish direction was correct, but the move did not overcome the priced event premium.

## Event calendar routine
Daily:
- Check earnings and dividends for open positions.
- Check major macro releases.
- Review company news.
- Confirm market holidays and shortened sessions.
- Mark expiration dates.
- Decide whether new entries are allowed before events.

## Common beginner mistakes
- Treating earnings as a coin flip with favorable payoff
- Using stops as protection from overnight gaps
- Forgetting the ex-dividend date
- Reading only the headline
- Holding through events accidentally
- Assuming a high expected move means price will move that far
- Ignoring correlated macro exposure
<!-- END:13-events-and-catalysts -->

<!-- CHANNEL:14-psychology-journaling -->
# 14 · Trading Psychology and Journaling

## Psychology is operational risk
Emotions are not removed by knowing their names. They are controlled with position limits, checklists, cooldowns, and review. The goal is not to feel nothing. The goal is to prevent feelings from changing risk without permission.

## Common biases
- **FOMO:** entering because price moved without you.
- **Revenge trading:** increasing activity or size after a loss.
- **Loss aversion:** refusing to exit because realizing the loss feels worse.
- **Anchoring:** fixating on entry price or a prior high.
- **Confirmation bias:** seeking only evidence that supports the position.
- **Recency bias:** assuming the latest wins or losses will continue.
- **Overconfidence:** increasing size after a small sample of success.
- **Outcome bias:** calling a bad process good because it won.
- **Sunk-cost fallacy:** adding risk because time or money was already spent.
- **Boredom trading:** entering without an edge because the market is open.

## Process controls
Use:
- Maximum trades per day
- Maximum daily loss
- Waiting period after a rule violation
- No-trade windows around events
- Pre-entry checklist
- Written invalidation
- Fixed review time
- Removal of P/L display when it causes poor decisions
- Smaller size during learning

Discipline is easier when the platform enforces limits.

## Pre-trade journal
Record before entry:
- Date and time
- Ticker
- Market regime
- Thesis
- Setup type
- Chart timeframe
- Entry trigger
- Invalidation
- Target
- DTE and strike
- Bid/ask and liquidity
- Delta, theta, IV
- Event risk
- Maximum and planned loss
- Position size
- Confidence based on evidence, not emotion

## During-trade journal
Record:
- Actual fill and slippage
- Management changes
- New information
- Whether rules were followed
- Emotional state
- Any urge to move the stop or add size

Do not rewrite the original thesis after the fact.

## Post-trade journal
Record:
- Exit price and reason
- P/L
- MAE and MFE
- Holding time
- Screenshot
- Process grade
- One mistake
- One thing done well
- Whether the setup should remain in the playbook

## Process grading
Example:
- A: all rules followed, regardless of P/L.
- B: minor execution issue without added risk.
- C: rule deviation or poor preparation.
- D: major risk violation.
- F: uncontrolled trade, hidden loss, or failure to document.

A winning F-grade trade is dangerous because it rewards bad behavior.

## Review cadence
Daily:
- Check rule violations.
- Review largest loss and best process.

Weekly:
- Group trades by setup.
- Count impulsive trades.
- Review slippage and event mistakes.
- Identify one behavior to change.

Monthly:
- Evaluate expectancy and drawdown.
- Compare paper and live execution if applicable.
- Remove setups with no evidence.
- Update checklists, not rules mid-sample.

## Handling losses
After a large or emotional loss:
1. Stop trading.
2. Record facts before explanations.
3. Confirm account and open risk.
4. Identify whether it was market loss, model loss, execution loss, or rule violation.
5. Reduce size when returning.
6. Do not attempt to win it back immediately.

## Handling wins
After a large win:
- Do not immediately increase size.
- Check whether the trade followed rules.
- Separate skill, market regime, and luck.
- Record favorable slippage or unusual event behavior.
- Avoid turning one result into a universal strategy.

## Sample journal entry
**Thesis:** Bullish pullback in daily uptrend.  
**Trigger:** 15-minute higher low and VWAP reclaim.  
**Invalidation:** Underlying below prior swing low.  
**Contract:** 30-DTE call, delta 0.55, narrow spread.  
**Risk:** $45 planned, $120 maximum.  
**Outcome:** −$42.  
**Process grade:** A. Setup failed, exit followed plan.  
**Lesson:** No rule change from one loss.

## Common beginner mistakes
- Journaling only losers
- Recording P/L without context
- Changing strategy after three trades
- Hiding rule violations
- Increasing size after a winning streak
- Treating confidence as a feeling
- Using a journal as emotional storytelling instead of data
<!-- END:14-psychology-journaling -->

<!-- CHANNEL:15-backtesting-stats -->
# 15 · Backtesting, Statistics, and Learning

## Why statistics matter
Win rate alone is not enough. A strategy can win often and lose money, or win less often and remain profitable. Evaluate the full distribution of outcomes and whether the test resembles real execution.

## Core metrics
### Win rate
wins / closed trades

### Average win and average loss
Use dollar and percentage terms. Keep loss signs consistent.

### Expectancy
(win rate × average win) − (loss rate × average loss magnitude)

Example:
- 45% wins
- Average win $80
- 55% losses
- Average loss $40

Expectancy = 0.45×80 − 0.55×40 = $14 per trade before costs.

### Profit factor
gross profit / gross loss magnitude

Above 1 means gross profit exceeded gross loss in the sample. It does not prove future profitability.

### Maximum drawdown
Largest peak-to-trough decline in cumulative results.

### Consecutive losses
Important for sizing and psychological tolerance.

### MAE and MFE
- **Maximum adverse excursion:** worst unrealized movement during a trade.
- **Maximum favorable excursion:** best unrealized movement.

These help evaluate stops and targets.

### Exposure and holding time
Measure how long capital and risk are active.

## Sample size
A small sample can be dominated by luck.
Review:
- Number of trades
- Number of different market regimes
- Number of event and non-event trades
- Ticker concentration
- Time period
- Whether one outlier creates most profit

Thirty trades may provide an initial read, not a final truth.

## Backtest biases
- **Look-ahead bias:** using information unavailable at the decision time.
- **Survivorship bias:** testing only securities that survived.
- **Selection bias:** choosing favorable tickers or periods.
- **Data snooping:** trying many rules and reporting only the winner.
- **Overfitting:** fitting noise instead of durable behavior.
- **Fill bias:** assuming midpoint or perfect stop fills.
- **Corporate-action errors:** ignoring splits, dividends, or adjusted options.

## Option-specific testing problems
Historical option data can be incomplete or expensive. A valid test should consider:
- Bid and ask, not only marks
- IV and Greeks at entry
- Contract availability
- Volume and OI
- Expiration selection
- Slippage
- Assignment
- Early exercise
- Multi-leg execution
- Event dates

Testing the underlying and pretending it equals option returns is insufficient.

## In-sample and out-of-sample
- **In-sample:** data used to develop the strategy.
- **Out-of-sample:** untouched data used to evaluate it.
- **Walk-forward:** repeatedly train on past data and test on the next period.

Do not keep tuning after seeing the out-of-sample result and still call it out-of-sample.

## Paper versus live
Paper trading helps test process but often differs from live trading:
- Better fills
- No queue position
- Less emotional pressure
- Different partial fills
- No real assignment stress
- Easier exits in thin markets

Move from paper to live only with small size and continued comparison.

## Regime analysis
Break results down by:
- Bull, bear, and range
- High and low IV
- Trending and choppy
- Earnings and non-earnings
- DTE
- Delta
- Strategy
- Ticker
- Time of day
- Market breadth

A strategy may have positive expectancy only in one regime.

## Champion and challenger
A fair comparison requires:
- Fixed strategy definitions
- Same date range and universe
- Same costs and fills
- Same risk per trade
- Minimum sample
- Predefined promotion rules
- Human review

Do not replace the champion after one lucky week.

## Statistical discipline
- Keep rejected trades for analysis.
- Do not delete losses.
- Freeze rules during an evaluation window.
- Record every change with a version.
- Separate discovery data from validation data.
- Report uncertainty and sample size.
- Prefer simple rules that survive different periods.

## Common beginner mistakes
- Optimizing for win rate
- Ignoring fees and slippage
- Treating paper marks as fills
- Changing rules after each loss
- Using only one bullish period
- Promoting a strategy with too few trades
- Confusing correlation with causation
- Believing a backtest is a guarantee

## Before moving on
You should be able to calculate expectancy, identify major biases, and explain why a strategy needs out-of-sample and forward validation.
<!-- END:15-backtesting-stats -->

<!-- CHANNEL:16-taxes-and-rules -->
# 16 · Accounts, Taxes, and Trading Rules

## This topic changes
Broker policies, tax rules, settlement practices, approval requirements, and trading regulations can change. Verify current information with the broker and primary sources. Tradysquids is not legal, tax, brokerage, or accounting software.

## Account types
### Cash account
Trades use settled cash. Settlement timing and good-faith or freeriding restrictions may apply. Options approval can still limit strategies.

### Margin account
Margin can support spreads, short options, and share obligations, but it also creates:
- Buying-power changes
- Maintenance requirements
- Forced liquidation
- Interest charges
- Larger possible exposure

“Defined-risk spread” does not guarantee a broker will treat every expiration scenario gently.

### Retirement accounts
Strategy access may be limited. Tax treatment differs from taxable accounts. Assignment can create prohibited or unsupported positions.

## Options approval
Brokers commonly use approval levels based on experience, objectives, finances, and account type. Permission to trade a structure does not mean it is appropriate or understood.

Never misstate financial information to obtain approval.

## Buying power
Understand:
- Premium required
- Spread maximum loss
- Cash-secured obligations
- Naked short-option margin
- Assignment share cost
- Concentration requirements
- Intraday versus overnight buying power

Buying power can increase during volatility or near events.

## Settlement
Settlement timing depends on product and transaction. Confirm:
- When sale proceeds become available
- Whether exercise creates shares
- Whether index options cash settle
- Whether the product is AM or PM settled
- Broker cutoff times

Do not rely on an old article or a rule remembered from another account.

## Active-trading restrictions
Day-trading rules and broker controls may apply depending on account type, equity, product, and current regulation. Check the broker’s current definition of a day trade and its restrictions before frequent trading.

## Taxes and records
Keep:
- Trade confirmations
- Monthly statements
- Opening and closing dates
- Premiums
- Fees
- Exercises
- Assignments
- Expirations
- Corporate actions
- Cost basis
- Adjustments
- Strategy notes

Potentially relevant concepts include:
- Short-term versus long-term treatment
- Exercise and assignment basis adjustments
- Wash-sale rules
- Straddle rules
- Constructive sales
- Qualified covered calls
- Special treatment for certain broad-based index or futures-linked contracts
- State taxes

These rules are complex and fact-specific. Use current IRS materials and a qualified tax professional.

## Exercise and assignment records
Exercise can roll option premium into share basis or proceeds depending on the side and outcome. Assignment can change the acquisition or sale price of shares. Broker reporting may not capture every strategy-level interpretation automatically.

## Estimated taxes
Profitable trading can create tax obligations before annual filing. A large account gain is not all spendable money. Plan for taxes with professional guidance rather than discovering them through a letter written in government typography.

## Entity and business claims
Forming an LLC does not automatically create trader tax status, eliminate taxes, or make losses deductible. Tax elections and business treatment have specific requirements and consequences.

## Security and account access
- Use unique passwords and MFA.
- Never share brokerage credentials with a signal seller or bot.
- Review authorized devices and API permissions.
- Confirm withdrawal instructions independently.
- Do not install unknown remote-access software.
- Read-only data access should remain read-only.

## Current-source checklist
Before relying on a rule:
1. Check the broker’s current policy.
2. Check OCC materials for option mechanics.
3. Check FINRA and SEC materials for trading rules.
4. Check IRS guidance for federal tax treatment.
5. Check state requirements.
6. Document the date and source.
7. Ask a qualified professional when consequences are material.

## Common beginner mistakes
- Assuming all indexes settle like stocks
- Trading spreads without assignment buying power
- Relying on social-media tax advice
- Thinking an LLC fixes tax problems
- Ignoring state taxes
- Failing to save statements
- Using stale day-trading thresholds
- Sharing account access with third parties
<!-- END:16-taxes-and-rules -->

<!-- CHANNEL:17-scams-and-myths -->
# 17 · Scams, Myths, and Red Flags

## Why traders are targeted
Trading combines money, uncertainty, urgency, and hope. That combination attracts fake gurus, manipulated screenshots, pump groups, credential theft, and impossible promises.

A professional-looking Discord server proves only that someone learned how to arrange channels.

## Major red flags
- Guaranteed returns
- “No-loss” systems
- Extremely high win rates without complete audited history
- Deleted losing alerts
- Entries posted after the move
- Screenshots without broker statements
- Pressure to act immediately
- Secret indicators that cannot be explained
- Claims that risk management is unnecessary
- Requests for passwords, API keys, seed phrases, or remote access
- Payment through gift cards or irreversible crypto
- Impersonation of brokers, regulators, or public figures
- Referral pressure and recruitment commissions
- Refusal to discuss drawdown, average loss, or sample size

## Signal-room manipulation
A dishonest room may:
- Post vague entries and claim whichever interpretation worked.
- Count partial winners but hide full losses.
- Use midpoint marks that were never fillable.
- Alert illiquid contracts, buy first, then sell into followers.
- Edit messages after the fact.
- Reset performance after drawdowns.
- Show gross profit without position size or losses.

Require timestamps, exact contracts, executable prices, complete results, and preserved history.

## Common myths
### “High win rate means profitable”
False. Expectancy depends on average win and loss.

### “Cheap options are safer”
False. Cheap contracts may be far OTM, near expiration, or illiquid.

### “Selling premium is always safer”
False. Short options can have limited gains and large losses.

### “Defined risk means small risk”
False. The defined maximum may still be too large for the account.

### “Delta is the probability of winning”
False. Delta is a sensitivity estimate and only a rough probability proxy in some contexts.

### “Overbought means sell”
False. Strong trends can remain overbought.

### “All gaps fill”
False. Some do; some begin lasting repricing.

### “Rolling avoids a loss”
False. Rolling closes one trade and opens another.

### “Paper profit proves live profit”
False. Live fills, pressure, and assignment differ.

### “More indicators mean more confirmation”
False. Many indicators measure the same price data.

### “A stop guarantees the loss amount”
False. Gaps and illiquidity can produce worse fills.

## Verifying performance
Ask for:
- Complete trade list
- Exact timestamps
- Exact contracts
- Entry and exit method
- Bid/ask at the time
- Fees and slippage
- Open losses
- Maximum drawdown
- Average win and loss
- Sample size
- Rule changes
- Independent verification

A single screenshot is advertising, not evidence.

## Pump-and-dump risk
Thin stocks and options can be manipulated.
Warning signs:
- Sudden coordinated social posts
- Low float
- Weak filings
- Promotional language
- Huge percentage targets
- Illiquid options
- Insiders or promoters selling
- No credible catalyst

Do not help coordinate manipulation or trade on nonpublic material information.

## Credential and malware safety
Never provide:
- Brokerage login
- MFA code
- API secret with trading or withdrawal permissions
- Crypto seed phrase
- Remote desktop access
- Identity documents to an unverified person

Check links and bot permissions. A “trading tool” can be malware with a candlestick icon.

## What to do after suspected fraud
1. Stop sending money.
2. Preserve messages, receipts, wallet addresses, and usernames.
3. Change passwords and revoke sessions.
4. Contact the broker or bank.
5. Review account activity.
6. Report through appropriate official channels.
7. Do not pay a “recovery service” demanding more money.

## Healthy skepticism checklist
- Can the claim be measured?
- Is risk stated as clearly as reward?
- Is the complete history preserved?
- Are results net of costs?
- Is the seller compensated by subscriptions or referrals?
- Can the strategy be explained without secrecy?
- Does the claim survive basic expectancy math?
- Would the promoter still profit if no one subscribed?

## Final rule
No one can remove uncertainty from markets. Anyone selling certainty is usually selling something else.
<!-- END:17-scams-and-myths -->
