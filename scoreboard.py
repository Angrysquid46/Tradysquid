"""Phase 8: neutral competition scorekeeper (Master Spec Section 6).

Authoritative accounting for the BLACKTIDE-vs-AXIOM competition, kept
outside both private traders. Consumes only official trade records this
module itself writes through two narrow entry points - no bot exists yet
(Phase 11+), so this waits idle until one calls record_trade_open/close.

Immutability is enforced by API design, not file permissions: this data
lives in a gitignored runtime SQLite file, so governance/OWNERSHIP.json's
commit-time write-guard (Phase 4) does not apply to it. Protection is
that the module never exposes an update/delete path for a closed trade -
the one allowed transition is open -> closed, exactly once, which is the
real-world event a trade closing represents, not an edit.

Grounding (Master Spec Section 4, already in governance/IMMUTABLE_RULES.json):
starting_bankroll_per_generation_usd=1000, max_open_trades_per_bot=1,
official_completed_trades_immutable=true, bust protocol resets bankroll
and starts a new generation without erasing history.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "state" / "scoreboard.db"

STARTING_BANKROLL_USD = 1000.0
MAX_OPEN_TRADES_PER_BOT = 1

BOTS = ("BLACKTIDE", "AXIOM")


def connect_db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS official_trades (
            trade_id TEXT PRIMARY KEY,
            bot TEXT NOT NULL,
            generation INTEGER NOT NULL,
            opened_at TEXT NOT NULL,
            closed_at TEXT,
            side TEXT NOT NULL,
            contract_symbol TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            contracts INTEGER NOT NULL,
            entry_bankroll REAL NOT NULL,
            pnl_usd REAL,
            max_favorable_pct REAL,
            max_adverse_pct REAL,
            recorded_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS official_trades_bot_generation
            ON official_trades(bot, generation);

        CREATE TABLE IF NOT EXISTS generation_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bot TEXT NOT NULL,
            generation INTEGER NOT NULL,
            event TEXT NOT NULL,
            at TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT ''
        );
        """
    )
    connection.commit()
    return connection


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# --- writes: the only sanctioned entry points into official_trades ----------

def record_trade_open(
    connection: sqlite3.Connection,
    *,
    trade_id: str,
    bot: str,
    generation: int,
    opened_at: str,
    side: str,
    contract_symbol: str,
    entry_price: float,
    contracts: int,
    entry_bankroll: float,
) -> None:
    if bot not in BOTS:
        raise ValueError(f"Unknown bot: {bot!r}")
    existing = connection.execute(
        "SELECT 1 FROM official_trades WHERE trade_id=?", (trade_id,)
    ).fetchone()
    if existing:
        raise ValueError(f"trade_id {trade_id!r} already recorded")
    authoritative_generation = current_generation(connection, bot)
    authoritative_bankroll = current_bankroll(connection, bot)
    if generation != authoritative_generation:
        raise ValueError(
            f"generation {generation} is not authoritative current generation "
            f"{authoritative_generation} for {bot}"
        )
    if abs(entry_bankroll - authoritative_bankroll) > 0.01:
        raise ValueError(
            f"entry_bankroll {entry_bankroll!r} does not match referee bankroll "
            f"{authoritative_bankroll!r}"
        )
    if entry_price <= 0 or contracts < 1:
        raise ValueError("entry_price and contracts must be positive")
    if entry_price * 100 * contracts > authoritative_bankroll + 0.01:
        raise ValueError("trade cost exceeds referee bankroll")
    # Global per bot, not per generation - IMMUTABLE_RULES.json's
    # max_open_trades_per_bot has no generation qualifier. A generation-
    # scoped check would let a bot hold an open trade in one generation
    # while opening another in the next (Phase 14 audit finding).
    open_count = connection.execute(
        "SELECT COUNT(*) FROM official_trades WHERE bot=? AND closed_at IS NULL",
        (bot,),
    ).fetchone()[0]
    if open_count >= MAX_OPEN_TRADES_PER_BOT:
        raise ValueError(
            f"{bot} already has an open trade "
            f"(max_open_trades_per_bot={MAX_OPEN_TRADES_PER_BOT})"
        )
    connection.execute(
        """
        INSERT INTO official_trades (
            trade_id, bot, generation, opened_at, closed_at, side,
            contract_symbol, entry_price, exit_price, contracts,
            entry_bankroll, pnl_usd, max_favorable_pct, max_adverse_pct,
            recorded_at
        ) VALUES (?, ?, ?, ?, NULL, ?, ?, ?, NULL, ?, ?, NULL, NULL, NULL, ?)
        """,
        (
            trade_id, bot, generation, opened_at, side, contract_symbol,
            entry_price, contracts, entry_bankroll, _now_iso(),
        ),
    )
    connection.commit()


def record_trade_close(
    connection: sqlite3.Connection,
    *,
    trade_id: str,
    closed_at: str,
    exit_price: float,
    pnl_usd: float,
    max_favorable_pct: float | None = None,
    max_adverse_pct: float | None = None,
) -> None:
    """The one allowed UPDATE - guarded by closed_at IS NULL so a trade
    can transition open -> closed exactly once. Raises if the trade
    doesn't exist or is already closed - what makes 'official completed
    trades immutable' real rather than merely documented.

    The referee computes P&L itself from the row's own stored
    entry_price/contracts and the given exit_price, rather than trusting
    the caller's pnl_usd outright (Phase 14 audit finding - a competitor
    should never get to just announce its own P&L). `pnl_usd` stays a
    required parameter for every existing caller's benefit (an honest
    caller already does this exact math before calling), but is now
    validated against the referee's own computation rather than written
    as-is; a mismatch beyond simple float rounding raises."""
    row = connection.execute(
        "SELECT closed_at, entry_price, contracts FROM official_trades WHERE trade_id=?",
        (trade_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"trade_id {trade_id!r} was never opened")
    if row["closed_at"] is not None:
        raise ValueError(f"trade_id {trade_id!r} is already closed and immutable")
    computed_pnl_usd = (exit_price - row["entry_price"]) * 100 * row["contracts"]
    if abs(computed_pnl_usd - pnl_usd) > 0.01:
        raise ValueError(
            f"trade_id {trade_id!r}: supplied pnl_usd={pnl_usd!r} does not match "
            f"entry_price/exit_price/contracts (computed {computed_pnl_usd!r})"
        )
    cursor = connection.execute(
        """
        UPDATE official_trades
        SET closed_at=?, exit_price=?, pnl_usd=?, max_favorable_pct=?, max_adverse_pct=?
        WHERE trade_id=? AND closed_at IS NULL
        """,
        (closed_at, exit_price, computed_pnl_usd, max_favorable_pct, max_adverse_pct, trade_id),
    )
    if cursor.rowcount == 0:
        raise ValueError(f"trade_id {trade_id!r} closed concurrently; refusing to overwrite")
    connection.commit()


def record_generation_event(
    connection: sqlite3.Connection,
    *,
    bot: str,
    generation: int,
    event: str,
    detail: str = "",
    minimum_qualifying_cost: float | None = None,
) -> None:
    if bot not in BOTS:
        raise ValueError(f"Unknown bot: {bot!r}")
    if event not in ("STARTED", "BUSTED"):
        raise ValueError(f"Unknown generation event: {event!r}")
    current = current_generation(connection, bot)
    open_position = current_position_status(connection, bot)
    if open_position is not None:
        raise ValueError("generation transition impossible while a position is open")
    existing = connection.execute(
        "SELECT event FROM generation_events WHERE bot=? AND generation=?",
        (bot, generation),
    ).fetchall()
    existing_events = {row["event"] for row in existing}
    if event == "BUSTED":
        if generation != current or "BUSTED" in existing_events:
            raise ValueError("invalid or duplicate BUSTED transition")
        bankroll = current_bankroll(connection, bot)
        if minimum_qualifying_cost is None:
            if bankroll > 0.01:
                raise ValueError("positive-bankroll bust requires minimum_qualifying_cost evidence")
        elif minimum_qualifying_cost <= bankroll + 0.01:
            raise ValueError("referee bankroll can still afford the qualifying trade")
    else:
        if generation != current + 1 or "STARTED" in existing_events:
            raise ValueError("STARTED must advance exactly one generation and cannot duplicate")
        prior = connection.execute(
            "SELECT 1 FROM generation_events WHERE bot=? AND generation=? AND event='BUSTED'",
            (bot, current),
        ).fetchone()
        if prior is None:
            raise ValueError("STARTED requires the current generation to be BUSTED first")
    connection.execute(
        "INSERT INTO generation_events (bot, generation, event, at, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        (bot, generation, event, _now_iso(), detail[:500]),
    )
    connection.commit()


# --- reads: metrics, all derived from official_trades/generation_events -----

def current_generation(connection: sqlite3.Connection, bot: str) -> int:
    values = []
    row = connection.execute(
        "SELECT MAX(generation) AS g FROM official_trades WHERE bot=?", (bot,)
    ).fetchone()
    if row and row["g"] is not None:
        values.append(row["g"])
    row = connection.execute(
        "SELECT MAX(generation) AS g FROM generation_events WHERE bot=?", (bot,)
    ).fetchone()
    if row and row["g"] is not None:
        values.append(row["g"])
    return max(values) if values else 1


def _closed_trades(
    connection: sqlite3.Connection, bot: str, generation: int | None
) -> list[sqlite3.Row]:
    if generation is None:
        return connection.execute(
            "SELECT * FROM official_trades WHERE bot=? AND closed_at IS NOT NULL "
            "ORDER BY closed_at ASC",
            (bot,),
        ).fetchall()
    return connection.execute(
        "SELECT * FROM official_trades WHERE bot=? AND generation=? "
        "AND closed_at IS NOT NULL ORDER BY closed_at ASC",
        (bot, generation),
    ).fetchall()


def trade_count(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> int:
    return len(_closed_trades(connection, bot, generation))


def total_pnl(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float:
    return sum(row["pnl_usd"] for row in _closed_trades(connection, bot, generation))


def current_bankroll(connection: sqlite3.Connection, bot: str) -> float:
    generation = current_generation(connection, bot)
    return STARTING_BANKROLL_USD + total_pnl(connection, bot, generation)


def win_rate(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    trades = _closed_trades(connection, bot, generation)
    if not trades:
        return None
    wins = sum(1 for row in trades if row["pnl_usd"] > 0)
    return wins / len(trades)


def profit_factor(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    trades = _closed_trades(connection, bot, generation)
    gross_win = sum(row["pnl_usd"] for row in trades if row["pnl_usd"] > 0)
    gross_loss = sum(row["pnl_usd"] for row in trades if row["pnl_usd"] < 0)
    if gross_loss == 0:
        return None
    return gross_win / abs(gross_loss)


def expectancy(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    trades = _closed_trades(connection, bot, generation)
    if not trades:
        return None
    return sum(row["pnl_usd"] for row in trades) / len(trades)


def average_winner(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    wins = [row["pnl_usd"] for row in _closed_trades(connection, bot, generation) if row["pnl_usd"] > 0]
    return sum(wins) / len(wins) if wins else None


def average_loser(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    losses = [row["pnl_usd"] for row in _closed_trades(connection, bot, generation) if row["pnl_usd"] < 0]
    return sum(losses) / len(losses) if losses else None


def largest_winner(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    wins = [row["pnl_usd"] for row in _closed_trades(connection, bot, generation) if row["pnl_usd"] > 0]
    return max(wins) if wins else None


def largest_loser(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    losses = [row["pnl_usd"] for row in _closed_trades(connection, bot, generation) if row["pnl_usd"] < 0]
    return min(losses) if losses else None


def _equity_curve(connection: sqlite3.Connection, bot: str, generation: int | None) -> list[float]:
    trades = _closed_trades(connection, bot, generation)
    if not trades:
        return []
    equity = trades[0]["entry_bankroll"]
    curve = [equity]
    for row in trades:
        equity += row["pnl_usd"]
        curve.append(equity)
    return curve


def max_drawdown(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    curve = _equity_curve(connection, bot, generation)
    if not curve:
        return None
    peak = curve[0]
    worst = 0.0
    for value in curve:
        peak = max(peak, value)
        worst = min(worst, value - peak)
    return worst


def current_drawdown(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> float | None:
    curve = _equity_curve(connection, bot, generation)
    if not curve:
        return None
    peak = max(curve)
    return curve[-1] - peak


def current_streak(connection: sqlite3.Connection, bot: str, generation: int | None = None) -> dict[str, Any] | None:
    trades = _closed_trades(connection, bot, generation)
    if not trades:
        return None
    kind = "WIN" if trades[-1]["pnl_usd"] > 0 else "LOSS"
    length = 0
    for row in reversed(trades):
        row_kind = "WIN" if row["pnl_usd"] > 0 else "LOSS"
        if row_kind != kind:
            break
        length += 1
    return {"type": kind, "length": length}


def bust_count(connection: sqlite3.Connection, bot: str) -> int:
    row = connection.execute(
        "SELECT COUNT(*) AS n FROM generation_events WHERE bot=? AND event='BUSTED'",
        (bot,),
    ).fetchone()
    return row["n"]


def generation_pnl_table(connection: sqlite3.Connection, bot: str) -> dict[int, float]:
    rows = connection.execute(
        "SELECT generation, SUM(pnl_usd) AS pnl FROM official_trades "
        "WHERE bot=? AND closed_at IS NOT NULL GROUP BY generation",
        (bot,),
    ).fetchall()
    return {row["generation"]: row["pnl"] for row in rows}


def best_generation(connection: sqlite3.Connection, bot: str) -> int | None:
    table = generation_pnl_table(connection, bot)
    return max(table, key=table.get) if table else None


def worst_generation(connection: sqlite3.Connection, bot: str) -> int | None:
    table = generation_pnl_table(connection, bot)
    return min(table, key=table.get) if table else None


def generation_over_generation_improvement(connection: sqlite3.Connection, bot: str) -> float | None:
    table = generation_pnl_table(connection, bot)
    if len(table) < 2:
        return None
    generations = sorted(table)
    latest, previous = generations[-1], generations[-2]
    return table[latest] - table[previous]


def current_position_status(connection: sqlite3.Connection, bot: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT * FROM official_trades WHERE bot=? AND closed_at IS NULL "
        "ORDER BY opened_at DESC LIMIT 1",
        (bot,),
    ).fetchone()
    return dict(row) if row else None


def lifetime_pnl(connection: sqlite3.Connection, bot: str) -> float:
    return total_pnl(connection, bot, generation=None)


def recent_closed_trades(
    connection: sqlite3.Connection, bot: str, *, limit: int = 20
) -> list[dict[str, Any]]:
    """Public, privacy-safe closed-trade feed for a winners/losers channel:
    outcome and P/L only, never contract/side/fill - the private-strategy
    signals current_position_status()'s raw row exposes for internal use
    only. Newest first."""
    rows = connection.execute(
        "SELECT trade_id, generation, closed_at, pnl_usd FROM official_trades "
        "WHERE bot=? AND closed_at IS NOT NULL ORDER BY closed_at DESC LIMIT ?",
        (bot, limit),
    ).fetchall()
    return [
        {
            "trade_id": row["trade_id"],
            "generation": row["generation"],
            "closed_at": row["closed_at"],
            "pnl_usd": row["pnl_usd"],
            "outcome": "WIN" if row["pnl_usd"] > 0 else "LOSS" if row["pnl_usd"] < 0 else "SCRATCH",
        }
        for row in rows
    ]


# The exact key set scoreboard_snapshot() returns - exported so other
# modules (rivalry.py's public_score_snapshot schema check) can validate
# against the real public shape instead of duplicating/guessing it.
SCOREBOARD_SNAPSHOT_KEYS = frozenset({
    "bot", "generation", "current_bankroll", "generation_pnl", "lifetime_pnl",
    "trade_count_generation", "trade_count_lifetime", "win_rate", "profit_factor",
    "expectancy", "average_winner", "average_loser", "largest_winner", "largest_loser",
    "max_drawdown", "current_drawdown", "bust_count", "current_streak",
    "best_generation", "worst_generation", "generation_over_generation_improvement",
    "current_position_status",
})


def scoreboard_snapshot(connection: sqlite3.Connection, bot: str) -> dict[str, Any]:
    """The public metrics payload Section 6 describes.

    Live positions are deliberately represented only as OPEN/FLAT.  The
    referee and bot-recovery path use current_position_status() directly;
    contract, direction, fill, size and timing never enter public state.
    """
    generation = current_generation(connection, bot)
    public_position_status = "OPEN" if current_position_status(connection, bot) else "FLAT"
    return {
        "bot": bot,
        "generation": generation,
        "current_bankroll": current_bankroll(connection, bot),
        "generation_pnl": total_pnl(connection, bot, generation),
        "lifetime_pnl": lifetime_pnl(connection, bot),
        "trade_count_generation": trade_count(connection, bot, generation),
        "trade_count_lifetime": trade_count(connection, bot, None),
        "win_rate": win_rate(connection, bot, None),
        "profit_factor": profit_factor(connection, bot, None),
        "expectancy": expectancy(connection, bot, None),
        "average_winner": average_winner(connection, bot, None),
        "average_loser": average_loser(connection, bot, None),
        "largest_winner": largest_winner(connection, bot, None),
        "largest_loser": largest_loser(connection, bot, None),
        "max_drawdown": max_drawdown(connection, bot, None),
        "current_drawdown": current_drawdown(connection, bot, None),
        "bust_count": bust_count(connection, bot),
        "current_streak": current_streak(connection, bot, None),
        "best_generation": best_generation(connection, bot),
        "worst_generation": worst_generation(connection, bot),
        "generation_over_generation_improvement": generation_over_generation_improvement(connection, bot),
        "current_position_status": public_position_status,
    }


def current_leader(connection: sqlite3.Connection) -> str | None:
    totals = {bot: lifetime_pnl(connection, bot) for bot in BOTS}
    if all(value == 0 for value in totals.values()):
        return None
    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    if ordered[0][1] == ordered[1][1]:
        return None
    return ordered[0][0]
