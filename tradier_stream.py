"""One reconnecting, read-only Tradier market-data stream."""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

import requests

try:
    import websocket
except ImportError:  # The REST safety poll remains available.
    websocket = None


class TradierPositionStream:
    """Stream quotes for the exact symbols required by open paper positions."""

    def __init__(
        self,
        token: str,
        base_url: str,
        symbols_provider: Callable[[], list[str]],
        event_callback: Callable[[dict[str, Any]], None],
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.symbols_provider = symbols_provider
        self.event_callback = event_callback
        self.stop_event = threading.Event()
        self.connected = False
        self.last_event_at = 0.0
        self.last_error = ""
        self.subscribed_symbols: list[str] = []

    @property
    def available(self) -> bool:
        return websocket is not None and bool(self.token)

    def stop(self) -> None:
        self.stop_event.set()

    def _session_id(self) -> str:
        response = requests.post(
            f"{self.base_url}/markets/events/session",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/json",
            },
            timeout=20,
        )
        response.raise_for_status()
        session_id = response.json().get("stream", {}).get("sessionid")
        if not session_id:
            raise RuntimeError("Tradier did not return a market stream session.")
        return str(session_id)

    @staticmethod
    def _payload(session_id: str, symbols: list[str]) -> str:
        return json.dumps(
            {
                "symbols": symbols,
                "filter": ["quote"],
                "sessionid": session_id,
                "linebreak": True,
                "validOnly": True,
            },
            separators=(",", ":"),
        )

    def _consume(self) -> None:
        session_id = self._session_id()
        connection = websocket.create_connection(
            "wss://ws.tradier.com/v1/markets/events",
            timeout=10,
            enable_multithread=True,
        )
        connection.settimeout(5)
        try:
            symbols = self.symbols_provider()
            if not symbols:
                return
            connection.send(self._payload(session_id, symbols))
            self.subscribed_symbols = symbols
            self.connected = True
            while not self.stop_event.is_set():
                latest_symbols = self.symbols_provider()
                if latest_symbols != self.subscribed_symbols:
                    if not latest_symbols:
                        return
                    connection.send(self._payload(session_id, latest_symbols))
                    self.subscribed_symbols = latest_symbols
                try:
                    raw_message = connection.recv()
                except websocket.WebSocketTimeoutException:
                    continue
                if not raw_message:
                    continue
                for line in str(raw_message).splitlines():
                    try:
                        event = json.loads(line)
                    except (TypeError, ValueError):
                        continue
                    if event.get("error"):
                        raise RuntimeError(str(event["error"]))
                    if event.get("type") == "quote" and event.get("symbol"):
                        self.last_event_at = time.time()
                        try:
                            self.event_callback(event)
                        except Exception as exc:
                            # Real incident: the callback posts Discord cards
                            # as a side effect of evaluating exits. A Discord
                            # rate limit exhausted its retries and raised,
                            # which propagated out of this loop, was caught by
                            # run_forever()'s outer handler as if the MARKET
                            # DATA connection had failed, and tore the whole
                            # websocket down for a reconnect - during which
                            # every open position fell back to the 60s REST
                            # poll instead of tick-by-tick pricing. Discord
                            # being rate-limited is not a reason SPY quotes
                            # should stop arriving. The callback's own
                            # failures are recorded without ever closing this
                            # connection over them.
                            self.last_error = (
                                f"event callback error (connection held): "
                                f"{type(exc).__name__}: {exc}"[:300]
                            )
        finally:
            self.connected = False
            self.subscribed_symbols = []
            connection.close()

    def run_forever(self) -> None:
        if not self.available:
            self.last_error = (
                "Streaming unavailable; install websocket-client. "
                "The one-minute REST safety poll remains active."
            )
            return
        delay = 2
        while not self.stop_event.is_set():
            if not self.symbols_provider():
                self.connected = False
                self.stop_event.wait(5)
                continue
            try:
                self._consume()
                self.last_error = ""
                delay = 2
            except Exception as exc:
                self.connected = False
                self.last_error = f"{type(exc).__name__}: {exc}"[:300]
                self.stop_event.wait(delay)
                delay = min(delay * 2, 60)
