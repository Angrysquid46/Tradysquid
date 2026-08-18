"""A closed trade must never be reopened by a stale writer.

Real incident: /close-profitable closed three genuinely profitable
positions and reported WIN $18/$18/$20. All three reappeared as OPEN, and
a fresh HOLD card was posted for one of them a minute after the close
message. Realized profit was reverted and the positions re-exposed.

Cause: discord_command_bot.py (Flask) and local_information_engine.py are
SEPARATE OS PROCESSES and both blind-overwrite the whole trade CSV.
POSITION_FILE_LOCK is a threading.RLock - it serialises threads inside one
process and gives no protection across them. The engine had read every row
BEFORE the close, then wrote its stale copy back over it.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import spy_scanner


def _row(trade_id, outcome="OPEN", **extra):
    row = {field: "" for field in spy_scanner.LOG_HEADER}
    row.update({"trade_id": trade_id, "ticker": "SPY", "outcome": outcome,
                "play_type": "SPY_MTF_4OF4", "entry_price": "0.95"})
    row.update(extra)
    return row


def test_a_stale_writer_cannot_reopen_a_closed_trade(monkeypatch):
    """The exact incident: engine writes its pre-close copy back."""
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(spy_scanner, "LOG_PATH", Path(temp) / "plays.csv")

        # The command bot closes the trade.
        spy_scanner.write_log([
            _row("T-1", outcome="WIN", exit_price="1.15",
                 realized_pl_dollars="20", closed_at="2026-08-18T12:47:00-05:00"),
        ])

        # The engine writes back the copy it read BEFORE the close.
        spy_scanner.write_log([_row("T-1", outcome="OPEN")])

        rows = spy_scanner.read_log()
        assert rows[0]["outcome"] == "WIN", "the close was silently reverted"
        assert rows[0]["realized_pl_dollars"] == "20", "realized P/L was lost"


def test_the_whole_batch_survives_not_just_the_closed_row(monkeypatch):
    """Other trades in the same stale write must still update normally."""
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(spy_scanner, "LOG_PATH", Path(temp) / "plays.csv")
        spy_scanner.write_log([
            _row("T-1", outcome="WIN", realized_pl_dollars="20"),
            _row("T-2", outcome="OPEN", current_pl_dollars="5"),
        ])
        spy_scanner.write_log([
            _row("T-1", outcome="OPEN"),                       # stale
            _row("T-2", outcome="OPEN", current_pl_dollars="9"),  # legitimate
        ])
        rows = {r["trade_id"]: r for r in spy_scanner.read_log()}
        assert rows["T-1"]["outcome"] == "WIN"
        assert rows["T-2"]["current_pl_dollars"] == "9", (
            "a normal open-position update was blocked"
        )


def test_a_closed_trade_can_still_be_updated_while_staying_closed(monkeypatch):
    """The guard only blocks reopening - it must not freeze closed rows."""
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(spy_scanner, "LOG_PATH", Path(temp) / "plays.csv")
        spy_scanner.write_log([_row("T-1", outcome="WIN", realized_pl_dollars="20")])
        spy_scanner.write_log([
            _row("T-1", outcome="WIN", realized_pl_dollars="20",
                 discord_thread_id="123"),
        ])
        rows = spy_scanner.read_log()
        assert rows[0]["discord_thread_id"] == "123"


def test_a_deliberate_purge_still_clears_everything(monkeypatch):
    """reset_all_trade_data writes an empty log - a trade absent from the
    incoming rows must NOT be resurrected, or reset would stop working."""
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(spy_scanner, "LOG_PATH", Path(temp) / "plays.csv")
        spy_scanner.write_log([_row("T-1", outcome="WIN")])
        spy_scanner.write_log([])
        assert spy_scanner.read_log() == []


def test_an_open_trade_is_untouched_by_the_guard(monkeypatch):
    with tempfile.TemporaryDirectory() as temp:
        monkeypatch.setattr(spy_scanner, "LOG_PATH", Path(temp) / "plays.csv")
        spy_scanner.write_log([_row("T-1", outcome="OPEN", current_pl_dollars="3")])
        spy_scanner.write_log([_row("T-1", outcome="OPEN", current_pl_dollars="7")])
        assert spy_scanner.read_log()[0]["current_pl_dollars"] == "7"
