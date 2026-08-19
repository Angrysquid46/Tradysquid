"""scan_candidates() used to fetch spot_price once at the top of a scan
cycle and reuse that same, increasingly stale value through 2 SPY_0DTE
its own sequential network round-trip. _refresh_spot_price() re-fetches a
so strike selection and the journaled spot_at_entry aren't built off a
value that's tens of seconds behind the real market by the time those
later groups run.
"""

from __future__ import annotations
from unittest import mock

import spy_scanner


def test_refresh_spot_price_uses_the_fresh_quote_when_available():
    with mock.patch.object(spy_scanner, "get_quote", return_value={"last": "601.25"}):
        assert spy_scanner._refresh_spot_price(600.0) == 601.25


def test_refresh_spot_price_falls_back_when_quote_is_missing():
    with mock.patch.object(spy_scanner, "get_quote", return_value=None):
        assert spy_scanner._refresh_spot_price(600.0) == 600.0


def test_refresh_spot_price_falls_back_when_quote_has_no_last():
    with mock.patch.object(spy_scanner, "get_quote", return_value={"last": None}):
        assert spy_scanner._refresh_spot_price(600.0) == 600.0


def test_refresh_spot_price_fails_open_on_provider_error():
    with mock.patch.object(spy_scanner, "get_quote", side_effect=spy_scanner.TradierError("down")):
        assert spy_scanner._refresh_spot_price(600.0) == 600.0
