"""One trade's Discord failure must not block cleanup for every other trade.

Real incident, reported live: /close-profitable and /force-sell both
closed genuinely profitable positions - the CSV was written correctly -
but the closed trades "still exist in held positions even though they are
closed."

sync_closed_result_channels loops over closed trades deleting their
held/entry/exit cards. It had no per-row isolation, so the FIRST row whose
Discord call hit an exhausted rate limit raised and aborted the whole
loop. Every closed trade sorted after it kept its stale held card that
cycle - which is why the report was plural. It self-healed only when a
later 5-minute cleanup cycle happened to get through without a 429.
"""

from __future__ import annotations

import spy_scanner


class _FlakyDiscord:
    """Fails on one specific trade, succeeds on the rest."""

    ready = True

    def __init__(self, fail_trade_id: str):
        self.fail_trade_id = fail_trade_id
        self.deleted: list[tuple[str, str]] = []
        self.results: list[str] = []

    def upsert_trade_result(self, channel, state, trade_id, content):
        if trade_id == self.fail_trade_id:
            raise spy_scanner.DiscordError(
                f"Discord rate limit retries exhausted for /channels/x/{trade_id}"
            )
        self.results.append(trade_id)
        return "msg-1", 0

    def delete_trade_message(self, logical, state, kind, trade_id):
        if trade_id == self.fail_trade_id:
            raise spy_scanner.DiscordError(
                f"Discord rate limit retries exhausted for /channels/x/{trade_id}"
            )
        self.deleted.append((kind, trade_id))
        return True


def _closed_row(trade_id: str, closed_at: str, outcome: str = "WIN"):
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({
        "trade_id": trade_id, "ticker": "SPY", "outcome": outcome,
        "closed_at": closed_at, "timestamp": closed_at,
        "play_type": "SPY_GAP_CONT_50", "option_symbol": f"OPT{trade_id}",
        "entry_price": "1.00", "exit_price": "1.50",
    })
    return row


def test_one_failing_trade_does_not_block_cleanup_for_the_others(monkeypatch):
    """The bug: the first failure aborted the loop, so every later closed
    trade kept its stale held card."""
    rows = [
        _closed_row("T-A", "2026-08-18T09:00:00-05:00"),
        _closed_row("T-B", "2026-08-18T09:01:00-05:00"),   # <- fails
        _closed_row("T-C", "2026-08-18T09:02:00-05:00"),
        _closed_row("T-D", "2026-08-18T09:03:00-05:00"),
    ]
    discord = _FlakyDiscord(fail_trade_id="T-B")
    monkeypatch.setattr(spy_scanner.trade_intelligence, "acknowledge",
                        lambda *a, **k: None)

    updated = spy_scanner.sync_closed_result_channels(rows, discord, {})

    cleaned = {tid for _kind, tid in discord.deleted}
    assert "T-C" in cleaned, "T-C never got cleaned because T-B raised first"
    assert "T-D" in cleaned, "T-D never got cleaned because T-B raised first"
    assert "T-A" in cleaned
    assert updated >= 3


def test_the_failing_trade_is_left_unrouted_so_it_retries(monkeypatch):
    """A trade whose cleanup failed must NOT be marked routed, or the next
    cycle would skip it and its stale card would never be removed."""
    rows = [_closed_row("T-A", "2026-08-18T09:00:00-05:00"),
            _closed_row("T-B", "2026-08-18T09:01:00-05:00")]
    discord = _FlakyDiscord(fail_trade_id="T-B")
    monkeypatch.setattr(spy_scanner.trade_intelligence, "acknowledge",
                        lambda *a, **k: None)

    state: dict = {}
    spy_scanner.sync_closed_result_channels(rows, discord, state)

    routed = set(state.get("routed_closed_trade_ids") or [])
    assert "T-A" in routed
    assert "T-B" not in routed, (
        "the failed trade was marked routed, so its stale held card would "
        "never be retried"
    )


def test_a_healthy_batch_still_routes_everything(monkeypatch):
    rows = [_closed_row(f"T-{i}", f"2026-08-18T09:0{i}:00-05:00") for i in range(4)]

    class _Fine(_FlakyDiscord):
        def __init__(self):
            super().__init__(fail_trade_id="__none__")

    discord = _Fine()
    monkeypatch.setattr(spy_scanner.trade_intelligence, "acknowledge",
                        lambda *a, **k: None)
    state: dict = {}
    updated = spy_scanner.sync_closed_result_channels(rows, discord, state)
    assert updated == 4
    assert len(set(state.get("routed_closed_trade_ids") or [])) == 4
