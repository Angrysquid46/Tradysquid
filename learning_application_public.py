"""Public natural-language extensions for live educational application mode."""

from __future__ import annotations

from typing import Any, Callable

import learning_application as base


# The core parser already handles explicit verbs such as "apply" and
# "walk me through". Add common lesson-oriented wording without duplicating the
# live-data implementation.
EXTRA_APPLICATION_WORDS = (
    "use the lesson",
    "apply the lesson",
    "use the valuation",
    "use the chart",
    "use the technical",
    "use the options",
    "use the option",
    "use the risk",
    "use the volatility",
    "use the fundamental",
)
base.APPLICATION_WORDS = tuple(
    dict.fromkeys((*base.APPLICATION_WORDS, *EXTRA_APPLICATION_WORDS))
)

ApplicationRequest = base.ApplicationRequest
is_application_request = base.is_application_request
parse_application_request = base.parse_application_request
apply_to_ticker = base.apply_to_ticker
answer = base.answer


def validate_parser(
    verifier: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    return base.validate_parser(verifier)


if __name__ == "__main__":
    result = validate_parser(lambda symbol: bool(symbol))
    print(
        f"Validated {result['probes']} natural-language educational "
        "application requests."
    )
