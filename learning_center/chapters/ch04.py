"""Chapter 4: Other Call Buying Strategies."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 4

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="Protective Call: Insuring a Short Stock Position",
        topics=("protective call", "short stock protection"),
        keywords=("protective call", "short stock", "hedge"),
        related_concepts=("LC-01-01", "LC-10-01"),
        sections=(
            Section(
                "The Position",
                "A trader who is short stock has unlimited theoretical risk "
                "to the upside - the stock can rise without any ceiling. "
                "Buying a call against that short position caps that risk: "
                "above the call's strike, any further loss on the short stock "
                "is offset dollar-for-dollar by gains on the call. This is "
                "the mirror image of a protective put on long stock, which "
                "appears later in Chapter 17.",
            ),
            Section(
                "What It Costs and What It Buys",
                "The call's premium is the cost of capping the short "
                "position's upside risk at a known maximum - similar in "
                "spirit to insurance. Below the strike, the trader keeps the "
                "full benefit of the short stock's decline, reduced only by "
                "the premium paid. This does not eliminate risk between the "
                "current price and the strike - only the risk above the "
                "strike is capped.",
            ),
            Section(
                "Worked Example",
                "A trader shorts SPY at $500.00 and buys the $510 call for "
                "$4.00 as protection. If SPY rallies to $540: the short "
                "stock loses $40.00 per share, but the call is worth $30.00 "
                "of intrinsic value, for a net loss capped at $500 - $510 - "
                "$4.00 = -$14.00 per share, no matter how much further SPY "
                "rises. Without the call, that same rally would have cost "
                "$40.00 per share with no ceiling at all.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="Ratio Call Buying",
        topics=("ratio call buying", "position sizing", "conviction sizing"),
        keywords=("ratio buying", "sizing by conviction"),
        related_concepts=("LC-03-01", "LC-10-01"),
        sections=(
            Section(
                "The Idea",
                "Ratio call buying means deliberately sizing a call purchase "
                "as a multiple of what a standard, fixed-risk position would "
                "be - for example buying 3 contracts where a base plan called "
                "for 1 - to scale exposure to a specific, unusually high-"
                "conviction thesis. It is not a distinct options structure "
                "the way a spread is; it is a sizing decision layered on top "
                "of ordinary call buying (Chapter 3), and it is included here "
                "because it changes the position's risk profile enough to "
                "deserve separate treatment.",
            ),
            Section(
                "Risk Scales Linearly, Not Just Reward",
                "Because maximum loss on a long call is the premium paid per "
                "contract, buying 3x the contracts multiplies maximum loss by "
                "3x just as directly as it multiplies potential profit. Ratio "
                "buying is a bet-sizing decision with real, proportionally "
                "larger downside - it should be governed by the same "
                "position-sizing and account-risk discipline covered in "
                "Chapter 10, scaled to the larger size, not treated as a free "
                "way to increase upside.",
            ),
            Section(
                "Common Mistake",
                "Increasing size after a string of losses in an attempt to "
                "'make it back faster' is a recognizable and dangerous "
                "misuse of ratio sizing - conviction should come from the "
                "thesis on the current trade, never from the outcome of "
                "unrelated prior trades. See Chapter 14's psychology material "
                "for more on this pattern.",
            ),
        ),
    ),
    Lesson(
        lesson_number=3,
        title="Laddering Strikes and Expirations",
        topics=("laddering", "strike diversification", "expiration diversification"),
        keywords=("laddering", "diversifying strikes"),
        related_concepts=("LC-03-02", "LC-03-03"),
        sections=(
            Section(
                "The Idea",
                "Instead of concentrating an entire call position in one "
                "strike and one expiration, a trader can split it across "
                "several - for example buying calls at three different "
                "strikes, or the same strike across two expirations. This "
                "trades away some of the leverage concentration in exchange "
                "for a smoother, less binary P&L outcome across a range of "
                "underlying prices or timing scenarios, rather than a single "
                "strike/expiration combination that is either fully right or "
                "fully wrong.",
            ),
            Section(
                "What It Does and Does Not Solve",
                "Laddering reduces sensitivity to guessing one exact strike "
                "or one exact expiration correctly. It does not reduce "
                "directional risk - if the underlying moves against every "
                "rung of the ladder, every leg loses, just as a single "
                "concentrated position would. It is a way to diversify "
                "*which specific contract* expresses a correct directional "
                "view, not a hedge against being wrong on direction itself.",
            ),
        ),
    ),
    Lesson(
        lesson_number=4,
        title="Rolling a Long Call",
        topics=("rolling", "roll up", "roll out"),
        keywords=("rolling a long call", "roll up and out"),
        related_concepts=("LC-02-05", "LC-11-01"),
        sections=(
            Section(
                "Why Roll a Winning Long Call",
                "When a long call has moved deep in-the-money and gained "
                "significant intrinsic value, a trader who wants to keep "
                "directional exposure but reduce time-decay drag and lock in "
                "some gain can sell the current call and buy a new one at a "
                "higher strike and/or later expiration - realizing part of "
                "the gain now while re-establishing exposure further out.",
            ),
            Section(
                "Why Roll a Losing Long Call",
                "Rolling a long call that has moved against the position - "
                "typically out to a later expiration - gives the original "
                "thesis more time to play out, at the cost of paying "
                "additional premium for that extra time. This is a genuinely "
                "new decision, not a way to avoid ever being wrong: it should "
                "be evaluated as 'would I buy this new call, at this new "
                "price, right now, on its own merits' - not as an automatic "
                "reflex to avoid closing a losing position (see Chapter 14 on "
                "loss aversion).",
            ),
        ),
    ),
]
