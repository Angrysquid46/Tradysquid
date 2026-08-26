"""Chapter 32: Structured Products."""

from __future__ import annotations

from learning_center_publish import Lesson, Section

CHAPTER = 32

LESSONS: list[Lesson] = [
    Lesson(
        lesson_number=1,
        title="What Structured Products Are",
        topics=("structured products", "principal protection"),
        keywords=("structured products", "structured notes"),
        related_concepts=("LC-26-01", "LC-23-02"),
        sections=(
            Section(
                "Definition",
                "**Structured products** are packaged financial "
                "instruments, often issued by a bank, that combine a "
                "bond-like component with an options-like payoff - for "
                "example a note that returns principal at maturity plus a "
                "capped or leveraged participation in an index's gain, "
                "conceptually similar to the options-and-T-bills approach "
                "in Chapter 26 or the collar in Chapter 23, but packaged "
                "and sold as a single instrument rather than assembled "
                "from separately-traded legs.",
            ),
            Section(
                "What to Check Before Using One",
                "Because a structured product bundles multiple economic "
                "exposures into one instrument, it is worth explicitly "
                "identifying the components - what is the bond/principal-"
                "protection piece worth on its own, what is the "
                "options-like piece actually paying for, what fees are "
                "embedded, and is there issuer credit risk (principal "
                "protection is only as good as the issuer's ability to pay "
                "it back) - rather than evaluating only the advertised "
                "headline payoff.",
            ),
        ),
    ),
]
