"""Phase 6: neutral point-in-time backtest laboratory (Master Spec Section
10). A shared, strategy-neutral read interface over Phase 5's Parquet
market data - no strategy or bot exists yet (Phase 11+); this is the
laboratory itself, not a specific strategy's backtest.

No-lookahead is structural, not a runtime check: every query filters
captured_at/bar_timestamp <= the requested instant, so there is no code
path that can read a row from after that moment.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import market_data
import market_data_store as store
import market_memory

ROOT = Path(__file__).resolve().parent
BACKTEST_DIR = ROOT / "data" / "backtests"

ENGINE_VERSION = "backtest-lab-v1"
FEATURE_VERSION = "backtest-lab-features-v1"

TIER_A = "A"
TIER_B = "B"
TIER_C = "C"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"

DEFAULT_TOLERANCE_MINUTES = 5


def _iso(value: datetime) -> str:
    return value.isoformat()


class MarketView:
    """Point-in-time read access to Phase 5's Parquet market data for one
    symbol."""

    def __init__(
        self,
        symbol: str = market_data.TICKER,
        tolerance_minutes: int = DEFAULT_TOLERANCE_MINUTES,
    ):
        self.symbol = symbol
        self.tolerance_minutes = tolerance_minutes

    def market_as_of(self, timestamp: datetime) -> dict[str, Any]:
        trading_day = timestamp.date()
        glob = store.dataset_glob(store.QUOTES_DATASET, self.symbol, trading_day)
        if not store.partition_dir(store.QUOTES_DATASET, self.symbol, trading_day).exists():
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": "no quotes captured for this trading day", "quote": None,
            }
        rows = store.query(
            f"SELECT * FROM read_parquet('{glob}') WHERE captured_at <= ? "
            "ORDER BY captured_at DESC LIMIT 1",
            [_iso(timestamp)],
        )
        if not rows:
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": "no quote captured at or before this timestamp", "quote": None,
            }
        quote = rows[0]
        age_minutes = (
            timestamp - datetime.fromisoformat(quote["captured_at"])
        ).total_seconds() / 60
        if age_minutes > self.tolerance_minutes:
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": f"latest quote is {age_minutes:.1f} minutes stale, beyond "
                          f"{self.tolerance_minutes}-minute tolerance",
                "quote": quote,
            }
        tier = TIER_A if quote["data_class"] == store.VERIFIED_REAL else TIER_C
        return {
            "tier": tier,
            "reason": None if tier == TIER_A else INSUFFICIENT_DATA,
            "quote": quote,
        }

    def options_as_of(self, timestamp: datetime) -> dict[str, Any]:
        trading_day = timestamp.date()
        glob = store.dataset_glob(store.CHAIN_DATASET, self.symbol, trading_day)
        if not store.partition_dir(store.CHAIN_DATASET, self.symbol, trading_day).exists():
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": "no chain snapshots for this trading day", "contracts": [],
            }
        latest = store.query(
            f"SELECT MAX(captured_at) AS captured_at FROM read_parquet('{glob}') "
            "WHERE captured_at <= ?",
            [_iso(timestamp)],
        )
        captured_at = latest[0]["captured_at"] if latest else None
        if not captured_at:
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": "no chain snapshot at or before this timestamp", "contracts": [],
            }
        # Selecting only the rows from THIS one snapshot is what makes
        # "only contracts that existed at that point" automatic - a
        # snapshot's rows are exactly what Tradier returned at that
        # capture moment, nothing captured later ever appears here.
        contracts = store.query(
            f"SELECT * FROM read_parquet('{glob}') WHERE captured_at = ?",
            [captured_at],
        )
        age_minutes = (
            timestamp - datetime.fromisoformat(captured_at)
        ).total_seconds() / 60
        if age_minutes > self.tolerance_minutes:
            return {
                "tier": TIER_C, "reason": INSUFFICIENT_DATA,
                "detail": f"latest chain snapshot is {age_minutes:.1f} minutes stale",
                "captured_at": captured_at, "contracts": contracts,
            }
        clean = [c for c in contracts if c["data_class"] == store.VERIFIED_REAL]
        limited = [c for c in contracts if c["data_class"] == store.REAL_WITH_LIMITATIONS]
        if clean and len(clean) == len(contracts):
            tier = TIER_A
        elif clean or limited:
            # Real chain data exists but every contract is flagged
            # REAL_WITH_LIMITATIONS - Tier B's classification without a
            # modeled-pricing fallback (not implemented; see module docs).
            tier = TIER_B
        else:
            tier = TIER_C
        return {
            "tier": tier,
            "reason": None if tier != TIER_C else INSUFFICIENT_DATA,
            "captured_at": captured_at,
            "contracts": contracts,
        }

    def events_as_of(self, timestamp: datetime) -> dict[str, Any]:
        """No events/economic-calendar dataset exists yet - honestly
        reports INSUFFICIENT_DATA rather than fabricating a source."""
        return {
            "tier": TIER_C, "reason": INSUFFICIENT_DATA,
            "detail": "no events dataset exists yet", "events": [],
        }

    def bars_as_of(
        self, timestamp: datetime, lookback_minutes: int = 120
    ) -> list[dict[str, Any]]:
        trading_day = timestamp.date()
        if not store.partition_dir(store.BARS_DATASET, self.symbol, trading_day).exists():
            return []
        glob = store.dataset_glob(store.BARS_DATASET, self.symbol, trading_day)
        cutoff = int(timestamp.timestamp())
        earliest = cutoff - lookback_minutes * 60
        # captured_at <= timestamp too, not just bar_timestamp - a bar
        # FOR an in-window time that was only captured/backfilled later
        # must not appear "as of" a moment before it was actually known
        # (Phase 14 audit finding: only bar_timestamp was checked, unlike
        # market_as_of/options_as_of which both already enforce this).
        return store.query(
            f"SELECT * FROM read_parquet('{glob}') "
            "WHERE bar_timestamp <= ? AND bar_timestamp >= ? AND captured_at <= ? "
            "ORDER BY bar_timestamp ASC",
            [cutoff, earliest, _iso(timestamp)],
        )


def compute_features(bars: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Adapts market_data_store bar rows into market_memory's expected
    shape and calls its proven-causal compute_features_for_window
    directly, rather than reimplementing ATR/RSI/Bollinger/etc."""
    if not bars:
        return None
    ordered = sorted(bars, key=lambda row: row["bar_timestamp"])
    features = market_memory.compute_features_for_window(ordered, len(ordered) - 1)
    features["feature_version"] = FEATURE_VERSION
    return features


_LATEST_COLUMN = {
    store.QUOTES_DATASET: "captured_at",
    store.CHAIN_DATASET: "captured_at",
    store.BARS_DATASET: "bar_timestamp",
}


def dataset_fingerprint(symbol: str, start_date: date, end_date: date) -> str:
    """Content-address every immutable parquet input in the requested range."""
    digest = hashlib.sha256()
    digest.update(f"{ENGINE_VERSION}|{symbol}|{start_date}|{end_date}".encode())
    day = start_date
    while day <= end_date:
        for dataset_name in (store.QUOTES_DATASET, store.CHAIN_DATASET, store.BARS_DATASET):
            partition = store.partition_dir(dataset_name, symbol, day)
            for path in sorted(partition.glob("*.parquet")) if partition.exists() else ():
                digest.update(str(path.relative_to(store.DATA_ROOT)).replace("\\", "/").encode())
                with path.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
        day = date.fromordinal(day.toordinal() + 1)
    return digest.hexdigest()


def record_backtest(
    *,
    bot_version: str,
    dataset_fingerprint: str,
    date_range: tuple[str, str],
    evidence_tier: str,
    data_quality: dict[str, Any],
    feature_versions: dict[str, str],
    execution_assumptions: dict[str, Any],
    parameters: dict[str, Any],
    random_seed: int | None,
    results: dict[str, Any],
    engine_version: str = ENGINE_VERSION,
) -> dict[str, Any]:
    """Appends one reproducibility record - never overwrites, matching
    every other event-log convention in this codebase (CHANGELOG.jsonl,
    daily_data_manifest's own bookkeeping)."""
    record = {
        "bot_version": bot_version,
        "engine_version": engine_version,
        "dataset_fingerprint": dataset_fingerprint,
        "date_range": list(date_range),
        "evidence_tier": evidence_tier,
        "data_quality": data_quality,
        "feature_versions": feature_versions,
        "execution_assumptions": execution_assumptions,
        "parameters": parameters,
        "random_seed": random_seed,
        "results": results,
        "recorded_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)
    path = BACKTEST_DIR / f"{date.today().isoformat()}.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
    return record


def load_backtest_records(day: date) -> list[dict[str, Any]]:
    path = BACKTEST_DIR / f"{day.isoformat()}.jsonl"
    if not path.exists():
        return []
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records
