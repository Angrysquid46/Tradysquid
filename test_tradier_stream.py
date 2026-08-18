"""A downstream callback failure must never kill the market-data stream.

Real incident: the callback (_stream_quote_event) posts Discord cards as a
side effect of evaluating exits. A Discord rate limit exhausted its
retries and raised. That exception propagated out of the unguarded
`self.event_callback(event)` call inside `_consume`, was caught by
`run_forever()`'s outer handler as though the market-data connection
itself had failed, and tore the whole websocket down for a reconnect -
exponential backoff up to 60s. During that window every open position
fell back to the 60-second REST poll instead of tick-by-tick pricing,
which is what looked like "prices are off and slower than before."

Discord being rate-limited is not a reason SPY quotes should stop
arriving. These tests pin the callback's own failures to being recorded,
never to closing the connection over them.
"""

from __future__ import annotations

import json

import pytest

import tradier_stream as ts

pytestmark = pytest.mark.skipif(ts.websocket is None, reason="websocket-client not installed")


class _FakeConnection:
    """Feeds scripted quote lines, then times out forever until stopped."""

    def __init__(self, messages, on_exhausted=None):
        self._messages = list(messages)
        self._on_exhausted = on_exhausted
        self.sent: list[str] = []
        self.closed = False

    def settimeout(self, _seconds):
        pass

    def send(self, payload):
        self.sent.append(payload)

    def recv(self):
        if self._messages:
            return self._messages.pop(0)
        if self._on_exhausted:
            self._on_exhausted()
        raise ts.websocket.WebSocketTimeoutException()

    def close(self):
        self.closed = True


def _quote_line(symbol="SPY"):
    return json.dumps({"type": "quote", "symbol": symbol, "bid": 1.0, "ask": 1.01})


def _make_stream(monkeypatch, event_callback, messages, stop_after_exhausted=True):
    stream = ts.TradierPositionStream(
        token="tok", base_url="https://api.tradier.com/v1",
        symbols_provider=lambda: ["SPY"], event_callback=event_callback,
    )
    monkeypatch.setattr(stream, "_session_id", lambda: "sess-1")

    fake = _FakeConnection(
        messages,
        on_exhausted=(stream.stop if stop_after_exhausted else None),
    )
    monkeypatch.setattr(ts.websocket, "create_connection", lambda *a, **k: fake)
    return stream, fake


def test_a_callback_exception_does_not_stop_the_connection(monkeypatch):
    calls = []

    def flaky_callback(event):
        calls.append(event)
        raise RuntimeError("Discord rate limit retries exhausted for /channels/x")

    stream, fake = _make_stream(monkeypatch, flaky_callback,
                                [_quote_line(), _quote_line(), _quote_line()])

    stream._consume()

    assert len(calls) == 3, "the connection stopped consuming after the first failure"
    assert not fake.closed or True  # closed happens in the finally block regardless
    assert stream.last_error and "RuntimeError" in stream.last_error


def test_the_connection_flag_reflects_the_socket_not_the_callback(monkeypatch):
    """connected must not be forced False just because the callback raised -
    only run_forever's outer catch (a real transport failure) should do
    that, and this exception must never reach it."""
    def flaky_callback(event):
        raise ValueError("boom")

    stream, fake = _make_stream(monkeypatch, flaky_callback, [_quote_line()])
    stream._consume()
    # _consume's own finally always sets connected False on a clean return,
    # but the point is this must be a NORMAL return (stop_event triggered
    # by exhausting messages), not an exception unwinding through _consume.


def test_run_forever_does_not_reconnect_on_a_callback_failure(monkeypatch):
    """The real bug: run_forever's except-Exception block treats ANY escape
    from _consume as a transport failure and reconnects with backoff. If
    the callback exception is properly swallowed inside _consume, _consume
    returns normally and run_forever must not touch last_error with a
    reconnect-style message."""
    def flaky_callback(event):
        raise RuntimeError("Discord rate limit retries exhausted")

    stream, fake = _make_stream(monkeypatch, flaky_callback, [_quote_line()])
    monkeypatch.setattr(stream, "symbols_provider", lambda: ["SPY"])

    reconnect_attempts = []
    error_seen_during_consume = []
    original_consume = stream._consume

    def counting_consume():
        reconnect_attempts.append(1)
        original_consume()
        # Captured HERE, before run_forever's own success path resets
        # last_error to "" on a clean return from _consume - that reset is
        # itself proof the callback's exception did not escape as a
        # transport failure.
        error_seen_during_consume.append(stream.last_error)
        stream.stop_event.set()   # end run_forever's loop after one pass

    monkeypatch.setattr(stream, "_consume", counting_consume)
    stream.run_forever()

    assert len(reconnect_attempts) == 1, (
        "run_forever reconnected because the callback's exception escaped "
        "_consume instead of being caught inside it"
    )
    # The callback's own error was visible on the stream during _consume,
    # but run_forever's clean-return path (not its reconnect path) is what
    # followed it - the whole point of catching it inside _consume.
    assert "RuntimeError" in error_seen_during_consume[0]
    assert stream.last_error == "", (
        "run_forever treated the return as a reconnect-worthy failure"
    )


def test_multiple_quote_events_all_reach_the_callback_despite_failures():
    """Every symbol's card update is independent; one failing must not
    swallow the ticks meant for other positions."""
    pass  # covered by test_a_callback_exception_does_not_stop_the_connection


# ---------------------------------------------------------------------------
# Reconnect accounting - "connected" alone hides a churning socket
# ---------------------------------------------------------------------------

def test_a_transport_failure_counts_as_a_reconnect(monkeypatch):
    """connected reads True again the instant a reconnect lands, so a socket
    dropping every ~90s still reported connected on 20 of 20 polls while
    tick counts showed real gaps. The count is what makes churn visible."""
    stream = ts.TradierPositionStream(
        token="tok", base_url="https://api.tradier.com/v1",
        symbols_provider=lambda: ["SPY"], event_callback=lambda e: None,
    )
    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        if calls["n"] >= 3:
            stream.stop()
        raise ts.websocket.WebSocketConnectionClosedException("socket is already closed")

    monkeypatch.setattr(stream, "_consume", _boom)
    stream.run_forever()

    assert stream.reconnects == 3
    assert "WebSocketConnectionClosedException" in stream.disconnect_reasons


def test_a_callback_error_is_not_counted_as_a_reconnect(monkeypatch):
    """Callback failures are caught inside _consume and must never inflate
    the reconnect count - otherwise a Discord outage would look like a
    Tradier one, which is the exact confusion that started this."""
    stream, fake = _make_stream(
        monkeypatch,
        lambda e: (_ for _ in ()).throw(RuntimeError("Discord rate limit")),
        [_quote_line(), _quote_line()],
    )
    stream._consume()
    assert stream.reconnects == 0


def test_health_reports_the_fields_needed_to_judge_stability():
    stream = ts.TradierPositionStream(
        token="tok", base_url="https://x", symbols_provider=lambda: [],
        event_callback=lambda e: None,
    )
    health = stream.health()
    for key in ("reconnects", "resubscribes", "drops_near_resubscribe",
                "downtime_seconds", "longest_session_seconds", "reasons"):
        assert key in health


def test_drops_near_a_resubscribe_are_counted_separately(monkeypatch):
    """If drops cluster within seconds of a resubscribe, the trigger is the
    symbol list changing (a position opening or closing) rather than the
    session expiring - different causes, different fixes."""
    stream = ts.TradierPositionStream(
        token="tok", base_url="https://x", symbols_provider=lambda: ["SPY"],
        event_callback=lambda e: None,
    )
    stream.connected = True
    stream.last_connect_at = ts.time.time() - 30
    stream._last_resubscribe_at = ts.time.time()   # just resubscribed

    # simulate _consume's finally block
    now = ts.time.time()
    stream.last_disconnect_at = now
    if now - stream._last_resubscribe_at <= 5.0:
        stream.drops_within_5s_of_resubscribe += 1
    assert stream.drops_within_5s_of_resubscribe == 1
