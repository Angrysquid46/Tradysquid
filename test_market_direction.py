from market_direction import assess_market_direction, trade_direction_permission


def bars(values):
    return [
        {"close": value, "high": value + .04, "low": value - .04, "volume": 1000 + index * 10}
        for index, value in enumerate(values)
    ]


def test_persistent_downtrend_blocks_calls_and_allows_puts():
    context = assess_market_direction(bars([500 - index * .15 for index in range(80)]))
    assert context.direction == "DOWN"
    assert context.confidence > .60
    assert not trade_direction_permission(context, "call").allowed
    assert trade_direction_permission(context, "put").allowed


def test_persistent_uptrend_blocks_puts_and_allows_calls():
    context = assess_market_direction(bars([500 + index * .15 for index in range(80)]))
    assert context.direction == "UP"
    assert not trade_direction_permission(context, "put").allowed
    assert trade_direction_permission(context, "call").allowed


def test_small_bounce_does_not_overrule_larger_downtrend():
    values = [510 - index * .12 for index in range(75)] + [501.05, 501.10, 501.16, 501.22, 501.28]
    context = assess_market_direction(bars(values))
    assert context.direction == "DOWN"
    assert not context.up_reversal_confirmed
    assert not trade_direction_permission(context, "call", countertrend_setup=True).allowed


def test_mixed_market_reduces_size_instead_of_inventing_direction():
    values = [500 + ((index % 2) * .20) for index in range(80)]
    context = assess_market_direction(bars(values))
    permission = trade_direction_permission(context, "call")
    assert context.direction in {"FLAT", "MIXED"}
    assert permission.allowed
    assert permission.size_multiplier <= .35


def test_insufficient_evidence_fails_closed():
    context = assess_market_direction(bars([500 + index * .1 for index in range(10)]))
    assert context.direction == "INSUFFICIENT"
    assert not trade_direction_permission(context, "call").allowed
