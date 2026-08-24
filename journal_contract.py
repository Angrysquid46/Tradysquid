"""Trade journal format version constant.

Phase 3 purge: this module used to validate/patch spy_scanner's trade-
journal card rendering (entry_alert_text, close_alert_text,
sync_all_trade_journals, etc.) - all removed along with spy_scanner.py
itself. Reduced to just the version constant, which upgrade_batch_44.py
and upgrade_batch_44_live_acceptance.py (both still UNKNOWN-classified,
not resolved by this purge pass) still reference.
"""

from __future__ import annotations

JOURNAL_FORMAT_VERSION = "15"
