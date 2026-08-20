"""A stale writer must not be able to delete an open trade.

2026-08-20: SPY-20260820-004 through -007 were opened by the entry scan,
their cards posted to Discord, and then they vanished from the CSV
entirely - the log read 001, then 007, then back to 002.
#s06-momentum-adx25-held was left showing a frozen HOLD card for -007, a
trade that existed nowhere on disk.

Cause: discord_command_bot and local_information_engine are separate OS
processes, so POSITION_FILE_LOCK (a threading.RLock) does not reach across
them. closed_position_cleanup_job reads the log, syncs journals over the
network for seconds, then writes its now-stale copy back - and the entry
scan runs every minute inside that window.

The existing guard only stopped a CLOSED trade being reopened. An OPEN
trade the stale writer had never seen was silently deleted instead.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import spy_scanner as s


@pytest.fixture
def log_path(monkeypatch):
    # tempfile, not tmp_path: pytest's shared pytest-of-<user> base raises
    # PermissionError on this checkout (see conftest.py).
    path = Path(tempfile.mkdtemp(prefix="trade-log-")) / "spy-plays-log.csv"
    monkeypatch.setattr(s, "LOG_PATH", path)
    return path


def _row(trade_id: str, outcome: str = "", play: str = "SPY_MOMENTUM_ADX25") -> dict:
    return {
        "trade_id": trade_id,
        "timestamp": "2026-08-20T11:45:00-05:00",
        "action": "BUY open",
        "play_type": play,
        "ticker": "SPY",
        "option_symbol": "SPY260820C00766000",
        "entry_price": "1.00",
        "exit_price": "",
        "outcome": outcome,
    }


def test_a_stale_writer_cannot_delete_an_open_trade(log_path) -> None:
    """The exact 2026-08-20 loss."""
    s.write_log([_row("SPY-20260820-001")])
    stale = s.read_log()                      # cleanup job's snapshot

    # entry scan opens four more while the cleanup job is on the network
    s.write_log(stale + [_row(f"SPY-20260820-00{n}") for n in (4, 5, 6, 7)])

    s.write_log(stale)                        # cleanup writes its stale copy

    ids = {row["trade_id"] for row in s.read_log()}
    assert ids == {f"SPY-20260820-00{n}" for n in (1, 4, 5, 6, 7)}


def test_the_restored_rows_keep_their_data(log_path) -> None:
    s.write_log([_row("SPY-20260820-001")])
    stale = s.read_log()
    s.write_log(stale + [_row("SPY-20260820-007")])
    s.write_log(stale)

    restored = next(r for r in s.read_log() if r["trade_id"] == "SPY-20260820-007")
    # migrate_row normalises numeric strings, so 1.00 comes back as 1.0.
    assert float(restored["entry_price"]) == 1.00
    assert restored["option_symbol"] == "SPY260820C00766000"


def test_a_deliberate_purge_still_clears_everything(log_path) -> None:
    """reset_all_trade_data writes an empty list and must still work."""
    s.write_log([_row("SPY-20260820-001"), _row("SPY-20260820-002")])
    s.write_log([])
    assert s.read_log() == []


def test_a_closed_trade_still_cannot_be_reopened(log_path) -> None:
    """The original invariant must survive the new one."""
    s.write_log([_row("SPY-20260820-001")])
    open_snapshot = s.read_log()

    closed = [dict(row, outcome="WIN", exit_price="1.50") for row in open_snapshot]
    s.write_log(closed)

    s.write_log(open_snapshot)                # stale writer tries to reopen
    row = s.read_log()[0]
    assert row["outcome"] == "WIN"
    assert row["exit_price"] == "1.50"


def test_normal_updates_are_not_blocked(log_path) -> None:
    """Mutating a row in place must still take effect."""
    s.write_log([_row("SPY-20260820-001")])
    rows = s.read_log()
    rows[0]["last_mark"] = "1.23"
    s.write_log(rows)
    assert s.read_log()[0]["last_mark"] == "1.23"


def test_restoring_does_not_duplicate_rows(log_path) -> None:
    s.write_log([_row("SPY-20260820-001"), _row("SPY-20260820-002")])
    rows = s.read_log()
    s.write_log(rows)
    s.write_log(rows)
    ids = [row["trade_id"] for row in s.read_log()]
    assert ids == sorted(set(ids))
    assert len(ids) == 2
