"""full_scanner_job held POSITION_FILE_LOCK for the entire spy_scanner.main()
call - empirically 17-32s per cycle (avg ~25s), every ~15 minutes - which
blocked the separate-thread real-time stream exit path for the whole
window, no matter how tight its own staleness threshold. scan_candidates()
(the ~10+ sequential chain-fetch part that dominates that runtime) never
touches rows/the CSV, so _scan_candidates_lock_released() releases the lock
for just that call. These tests prove two things: the lock is genuinely
released (another thread can acquire it while scan_candidates is "running"),
and the release is safe - a concurrent write during the released window
survives main()'s later processing rather than being silently reverted by
main()'s own stale in-memory rows (the lost-update race the flush-before/
read-after pattern exists to prevent).
"""

from __future__ import annotations
import threading
import time
from pathlib import Path
from unittest import mock

import spy_scanner


def test_lock_released_lets_another_thread_acquire_it_during_scan_candidates():
    lock = threading.RLock()
    lock.acquire()
    acquired_by_other_thread = threading.Event()

    def try_from_other_thread():
        lock.acquire()
        acquired_by_other_thread.set()
        lock.release()

    other = threading.Thread(target=try_from_other_thread)

    def fake_scan_candidates(spot_price):
        other.start()
        assert acquired_by_other_thread.wait(timeout=2), (
            "another thread could not acquire the lock while "
            "scan_candidates was running - it was not actually released"
        )
        return [], {}, {}

    with mock.patch.object(spy_scanner, "scan_candidates", side_effect=fake_scan_candidates):
        spy_scanner._scan_candidates_lock_released(600.0, lock)

    other.join(timeout=2)
    # Reacquired by the caller after scan_candidates returns - this release
    # would raise RuntimeError ("cannot release un-acquired lock") otherwise.
    lock.release()


def test_lock_is_reacquired_by_the_caller_after_scan_candidates_returns():
    lock = threading.RLock()
    lock.acquire()
    with mock.patch.object(spy_scanner, "scan_candidates", return_value=([], {}, {})):
        spy_scanner._scan_candidates_lock_released(600.0, lock)
    # If the lock weren't reacquired, this release would raise RuntimeError
    # ("cannot release un-acquired lock").
    lock.release()


def test_lock_is_reacquired_even_when_scan_candidates_raises():
    lock = threading.RLock()
    lock.acquire()
    with mock.patch.object(spy_scanner, "scan_candidates", side_effect=RuntimeError("boom")):
        try:
            spy_scanner._scan_candidates_lock_released(600.0, lock)
        except RuntimeError:
            pass
    lock.release()


def test_none_lock_runs_scan_candidates_directly_with_no_locking_behavior():
    with mock.patch.object(spy_scanner, "scan_candidates", return_value=(["c"], {"q": 1}, {"s": 1})) as fake:
        result = spy_scanner._scan_candidates_lock_released(600.0, None)
    fake.assert_called_once_with(600.0)
    assert result == (["c"], {"q": 1}, {"s": 1})


def test_a_concurrent_close_during_the_released_window_survives_mains_later_write():
    """The actual bug this whole design prevents: without the flush-before/
    read-after around the release, a position closed by another lock
    holder during the released window would be silently reverted when
    main() later writes its own stale in-memory rows back to the CSV."""
    original_log = spy_scanner.LOG_PATH
    import tempfile
    with tempfile.TemporaryDirectory() as temp:
        spy_scanner.LOG_PATH = Path(temp) / "plays.csv"
        row = {field: "" for field in spy_scanner.LOG_HEADER}
        row.update({"trade_id": "SPY-LOCK-001", "ticker": "SPY", "outcome": "OPEN"})
        spy_scanner.write_log([row])

        lock = threading.RLock()
        lock.acquire()
        rows = spy_scanner.read_log()  # main()'s in-memory snapshot, taken before the release

        def fake_scan_candidates(spot_price):
            # Simulate the stream thread: acquires the (now-released) lock,
            # closes the position, writes it back, releases.
            lock.acquire()
            concurrent_rows = spy_scanner.read_log()
            concurrent_rows[0]["outcome"] = "WIN"
            spy_scanner.write_log(concurrent_rows)
            lock.release()
            return [], {}, {}

        spy_scanner.write_log(rows)  # main()'s flush-before-release
        with mock.patch.object(spy_scanner, "scan_candidates", side_effect=fake_scan_candidates):
            spy_scanner._scan_candidates_lock_released(600.0, lock)
        rows = spy_scanner.read_log()  # main()'s read-after-reacquire

        # main() would go on to mutate/write `rows` further; the point here
        # is that its post-reacquire view already reflects the concurrent
        # close, so a later write_log(rows) cannot revert it.
        assert rows[0]["outcome"] == "WIN"
        lock.release()
    spy_scanner.LOG_PATH = original_log
