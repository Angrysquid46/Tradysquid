"""Regression contract for the owner-requested Phase 16 remediation."""

from __future__ import annotations

import learning_center_publish as pub
from learning_center.expanded_curriculum import SUPPLEMENTS, supplement_lessons


# Topics the first 110-lesson pass omitted or reduced below lesson depth.
# These names are transcribed from the owner's contents-page audit and are
# deliberately independent of the implementation's lesson titles.
REQUIRED_REMEDIATION_TOPICS = {
    topic.strip()
    for topic in """
factors influencing option price|option markets|option symbology|details of option trading|order entry|profits and profit graphs|
total return concept of covered writing|computing return on investment|execution of the covered write order|selecting a covered writing position|writing against stock already owned|diversifying return and protection in a covered write|follow-up action|partial extraction strategy|special writing situations|
advanced selection criteria|ranking prospective call purchases|comment on spreads|
protected short sale or synthetic put|portfolio margin|synthetic straddle reverse hedge|altering the ratio of long calls to short stock|
investment required|philosophy of selling naked options|selection criteria|variable ratio write synthetic short strangle|
degrees of aggressiveness|ranking bull spreads|other uses of bull spreads|selecting a bear spread|
neutral calendar spread|bullish calendar spread|using all three expiration series|selecting the spread|differing philosophies|choosing the spread|delta-neutral calendar spreads|reverse calendar spread|diagonal bull spread|owning a call for free|diagonal backspreads|
pricing put options|effect of dividends on put option premiums|exercise and assignment|conversion|ranking prospective put purchases|loss-limiting actions|equivalent positions|which put to buy|tax considerations|put buying as protection for the covered call writer|no-cost collars|adjusting the collar|
straddle buying|selecting a straddle buy|buying a strangle|evaluating a naked put write|buying stock below its market price|covered put sale|ratio put writing|covered straddle write|uncovered straddle write|selecting a straddle write|equivalent stock position follow-up|starting with protection in place|strangle combination writing|
splitting the strikes|calendar spread using puts|butterfly spread|condor spreads|combining an option purchase and a spread|follow-up action for bull or bear spreads|useful bull complex strategies|selecting the spreads|using deltas|ratio put calendar spread|ratio calendar combination|
pricing LEAPS|comparing LEAPS and short-term options|LEAPS strategies|speculative option buying with LEAPS|selling LEAPS|spreads using LEAPS|
basic put and call arbitrage discounting|dividend arbitrage|carrying costs|box spread|interest play|risks in conversions and reversals|variations on equivalence arbitrage|effects of arbitrage|risk arbitrage using options|pairs trading|facilitation block positioning|
Black-Scholes model|computing composite implied volatility|applying calculations to strategy decisions|implementation|expected return|facilitation institutional block positioning|aiding in follow-up action|advanced mathematical concepts|
indices|cash-based options|futures trading|options on index futures|standard option strategies using index options|put-call ratio|market baskets|program trading|index arbitrage|impact on the stock market|follow-up strategies|market basket risk|simulating an index|trading the tracking error|inter-index spreading|
riskless ownership of a stock or index|cash value|cost of the embedded call option|price behavior prior to maturity|SIS|computing embedded call when underlying trades at a discount|adjustment factor|other constructs|option strategies involving structured products|lists of structured products|other structured products|arbitrage|mathematical applications|
futures option trading strategies|compliance mispricing strategies|futures spreads|using futures options in futures spreads|
definitions of volatility|another approach graph|moving averages|implied volatility|volatility of volatility|volatility trading|why volatility reaches extremes|vega|implied volatility and delta|effects on neutrality|position vega|time value premium is a misnomer|volatilizing at the put option|outright option purchases and sales|straddle or strangle buying and selling|call bull spreads|vertical put spreads|put bear spreads|calendar spreads|ratio spreads and backspreads|
misconceptions about volatility|volatility buyers rule|distribution of stock prices|what this means for option traders|pricing of options|probability of stock price movement|two ways volatility prediction can be wrong|trading the volatility prediction|trading the volatility skew|summary of volatility trading|
neutrality|the Greeks|strategy considerations using the Greeks|historical and implied volatility|calculation of VIX|listed volatility futures|other listed volatility products|listed VIX options|trading strategies directional signals|using VIX futures information|using and trading the term structure|protecting a stock portfolio with volatility derivatives|other macro strategies|hedged strategies using volatility derivatives|ratio spreads with VIX options|
history|special tax problems|tax planning strategies for equity options|general concepts market attitude and equivalent positions|what is best for me might not be best for you|mathematical ranking
""".replace("\n", "").split("|")
    if topic.strip()
}


def _all_lessons():
    for chapter in range(1, 44):
        for lesson in pub.load_chapter(chapter).LESSONS:
            yield chapter, lesson


def test_every_audited_gap_is_declared_as_a_searchable_topic():
    actual = {topic for _, lesson in _all_lessons() for topic in lesson.topics}
    missing = sorted(REQUIRED_REMEDIATION_TOPICS - actual)
    assert not missing, f"Phase 16 topics still missing: {missing}"


def test_remediation_is_lesson_depth_not_summary_cards():
    remediation = [
        lesson
        for chapter, specs in SUPPLEMENTS.items()
        for lesson in supplement_lessons(chapter, 1)
    ]
    assert len(remediation) >= 53
    for lesson in remediation:
        headings = [section.heading for section in lesson.sections]
        assert headings == [
            "Mechanics and purpose",
            "Selection and decision process",
            "Worked application",
            "Risks, follow-up, and common mistakes",
        ]
        words = sum(len(section.body.split()) for section in lesson.sections)
        # Four distinct teaching sections plus a worked application is the
        # structural guard; this floor rejects captions and glossary blurbs.
        assert words >= 125, f"{lesson.title!r} is still summary-depth ({words} words)"


def test_curriculum_depth_increased_without_renumbering_existing_lessons():
    lesson_count = card_count = 0
    for chapter in range(1, 44):
        lessons = pub.load_chapter(chapter).LESSONS
        numbers = [lesson.lesson_number for lesson in lessons]
        assert numbers == list(range(1, len(numbers) + 1))
        lesson_count += len(lessons)
        card_count += sum(len(lesson.sections) for lesson in lessons)
    assert lesson_count == 163
    assert card_count == 435


def test_every_rendered_card_fits_discord_message_limit():
    for chapter, lesson in _all_lessons():
        for section in lesson.sections:
            rendered = pub._lesson_card_text(chapter, lesson, section)
            assert len(rendered) <= 2000, (
                f"{chapter}/{lesson.lesson_number} {section.heading!r} exceeds Discord's limit"
            )
