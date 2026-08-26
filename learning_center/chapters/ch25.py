"""Chapter 25: LEAPS / Long-Term Option Strategies."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 25

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="What LEAPS Are",
        topics=("LEAPS", "long-term options"),
        keywords=("LEAPS", "long-dated options"),
        related_concepts=("LC-01-02", "LC-03-03"),
        sections=(
            Section(
                "Definition",
                "**LEAPS** (Long-term Equity AnticiPation Securities) are "
                "listed options with expirations more than a year out - "
                "the same call and put mechanics from Chapters 1-22 apply "
                "identically, just with materially more time to "
                "expiration than the shorter-dated examples used "
                "throughout this curriculum so far.",
            ),
            Section(
                "How More Time Changes the Trade-Offs",
                "Per Chapter 3's time trade-off (Lesson LC-03-03), more "
                "time costs more in premium but decays more slowly on any "
                "given day (time decay accelerates as expiration nears) - "
                "a LEAPS option's daily theta is a much smaller fraction of "
                "its total premium than a near-term option's, at the cost "
                "of tying up more capital for longer.",
            ),
        ),
    ),
    Lesson(
        lesson_number=2,
        title="LEAPS as a Stock Substitute",
        topics=("stock replacement", "capital efficiency"),
        keywords=("LEAPS stock replacement", "deep ITM LEAPS"),
        related_concepts=("LC-03-02", "LC-25-01"),
        sections=(
            Section(
                "The Strategy",
                "A deep in-the-money LEAPS call (Chapter 3, Lesson "
                "LC-03-02's ITM discussion, extended to a long horizon) "
                "behaves closely like owning the underlying shares - high "
                "delta, mostly intrinsic value - while requiring "
                "significantly less capital than buying the shares "
                "outright. The freed-up capital can be held in cash, "
                "earning interest, or deployed elsewhere, at the cost of "
                "the LEAPS' extrinsic value and its eventual expiration, "
                "unlike shares, which never expire.",
            ),
            Section(
                "LEAPS Covered Calls",
                "A LEAPS call can substitute for owned shares in a covered "
                "call (Chapter 2), selling shorter-dated calls against the "
                "long-term LEAPS position repeatedly over its life - "
                "sometimes called a 'poor man's covered call.' This "
                "combines LEAPS' capital efficiency with the covered call's "
                "income generation, at the cost of the LEAPS' own limited "
                "life and the need to manage two different expirations at "
                "once.",
            ),
        ),
    ),
]
