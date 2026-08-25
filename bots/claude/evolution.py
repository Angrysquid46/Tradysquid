"""Phase 13 v2: AXIOM's private adaptive loop (Master Spec Section 3 lists
"private evolution logic" and "learned thresholds/weights" as expected
private-competitor resources - this is that).

Every real trade is still recorded through scoreboard.py exactly as
before - the shared, immutable, official ledger is untouched by anything
here. This module privately tags which hypothesis produced each trade
and, once a hypothesis has enough attributed closed trades, measures its
own expectancy and deterministically tightens its parameters (never
randomly - reproducible, matching Section 9/10's determinism
requirement) or disables it if tightening doesn't help. Selection among
hypotheses that fire simultaneously uses that same measured fitness, so
a hypothesis nobody has proven yet and one that's losing money are not
treated the same.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import scoreboard

from bots.claude import hypotheses
from bots.claude.decision import EntryDecision
from bots.claude.parameters import HYPOTHESIS_DEFAULTS, MIN_SAMPLE_BEFORE_EVOLVE, MUTATION_SPECS

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "state" / "axiom_evolution.db"
LOG_PATH = Path(__file__).resolve().parent / "evolution_log.jsonl"

BOT = "AXIOM"

FitnessFn = Callable[[sqlite3.Connection, str], "tuple[float | None, int]"]


@dataclass(frozen=True)
class SelectedHypothesis:
    name: str
    decision: EntryDecision
    params: dict[str, float]


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """`db_path=None` uses the live shared path (state/axiom_evolution.db).
    backtest_runner.py passes ":memory:" instead - a fresh, isolated
    evolution state per backtest run that never touches (or is
    contaminated by) live trading state."""
    path = db_path if db_path is not None else DB_PATH
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA busy_timeout=10000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS hypothesis_state (
            name TEXT PRIMARY KEY,
            params_json TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            generation INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trade_attribution (
            trade_id TEXT PRIMARY KEY,
            hypothesis_name TEXT NOT NULL,
            generation INTEGER NOT NULL,
            recorded_at TEXT NOT NULL
        );
        """
    )
    connection.commit()
    _ensure_seeded(connection)
    return connection


def _ensure_seeded(connection: sqlite3.Connection) -> None:
    for name, params in HYPOTHESIS_DEFAULTS.items():
        connection.execute(
            """
            INSERT INTO hypothesis_state (name, params_json, enabled, generation, updated_at)
            VALUES (?, ?, 1, 0, ?)
            ON CONFLICT(name) DO NOTHING
            """,
            (name, json.dumps(params), _now_iso()),
        )
    connection.commit()


def get_hypothesis_params(connection: sqlite3.Connection, name: str) -> dict[str, float]:
    row = connection.execute(
        "SELECT params_json FROM hypothesis_state WHERE name=?", (name,)
    ).fetchone()
    if row is None:
        return dict(HYPOTHESIS_DEFAULTS[name])
    return json.loads(row["params_json"])


def get_hypothesis_state(connection: sqlite3.Connection, name: str) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM hypothesis_state WHERE name=?", (name,)
    ).fetchone()
    if row is None:
        raise ValueError(f"hypothesis {name!r} was never seeded")
    return dict(row)


def get_enabled_hypotheses(connection: sqlite3.Connection) -> list[str]:
    rows = connection.execute(
        "SELECT name FROM hypothesis_state WHERE enabled=1"
    ).fetchall()
    return [row["name"] for row in rows]


def record_trade_attribution(
    connection: sqlite3.Connection, *, trade_id: str, hypothesis_name: str, generation: int
) -> None:
    connection.execute(
        "INSERT INTO trade_attribution (trade_id, hypothesis_name, generation, recorded_at) "
        "VALUES (?, ?, ?, ?)",
        (trade_id, hypothesis_name, generation, _now_iso()),
    )
    connection.commit()


def get_attribution(connection: sqlite3.Connection, trade_id: str) -> str | None:
    row = connection.execute(
        "SELECT hypothesis_name FROM trade_attribution WHERE trade_id=?", (trade_id,)
    ).fetchone()
    return row["hypothesis_name"] if row else None


def _attributed_trade_ids(connection: sqlite3.Connection, hypothesis_name: str) -> list[str]:
    rows = connection.execute(
        "SELECT trade_id FROM trade_attribution WHERE hypothesis_name=?", (hypothesis_name,)
    ).fetchall()
    return [row["trade_id"] for row in rows]


def _scoreboard_pnl_for_trades(trade_ids: list[str]) -> dict[str, float]:
    """Reads closed-trade P&L directly from scoreboard.py's own SQLite
    file - the neutral scorekeeper is an approved SHARED resource both
    competitors may read (Section 3); this reads it, never writes to it."""
    if not trade_ids:
        return {}
    connection = sqlite3.connect(scoreboard.DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        placeholders = ",".join("?" for _ in trade_ids)
        rows = connection.execute(
            f"SELECT trade_id, pnl_usd FROM official_trades "
            f"WHERE trade_id IN ({placeholders}) AND closed_at IS NOT NULL",
            trade_ids,
        ).fetchall()
        return {row["trade_id"]: row["pnl_usd"] for row in rows}
    finally:
        connection.close()


def fitness_from_pnls(pnls: list[float]) -> tuple[float | None, int]:
    """Pure: expectancy (mean pnl) and sample size, or (None, n) if n is
    below MIN_SAMPLE_BEFORE_EVOLVE. Shared by hypothesis_fitness (reads
    live scoreboard data) and backtest_runner.py's own local, in-memory
    equivalent, so both use identical judging criteria."""
    if len(pnls) < MIN_SAMPLE_BEFORE_EVOLVE:
        return None, len(pnls)
    return sum(pnls) / len(pnls), len(pnls)


def hypothesis_fitness(connection: sqlite3.Connection, hypothesis_name: str) -> tuple[float | None, int]:
    """(expectancy, sample_size), computed from OFFICIAL closed trades
    (scoreboard.py). This is the LIVE default; backtest_runner.py injects
    its own local, in-memory equivalent instead (see
    select_hypothesis's/update_fitness_and_evolve's fitness_fn param) so a
    backtest run never reads or writes live scoreboard/evolution state."""
    trade_ids = _attributed_trade_ids(connection, hypothesis_name)
    pnl_by_id = _scoreboard_pnl_for_trades(trade_ids)
    return fitness_from_pnls(list(pnl_by_id.values()))


def select_hypothesis(
    connection: sqlite3.Connection,
    current_price: float,
    features: dict[str, Any],
    fitness_fn: FitnessFn = hypothesis_fitness,
) -> SelectedHypothesis | None:
    """Evaluates every enabled hypothesis; if more than one fires, the one
    with the better currently-measured fitness wins (an unmeasured
    hypothesis - not yet at MIN_SAMPLE_BEFORE_EVOLVE - is treated as
    fitness 0.0, neutral: neither unfairly favored over a proven winner
    nor starved before it gets a real chance)."""
    candidates: list[tuple[float, SelectedHypothesis]] = []
    for name in get_enabled_hypotheses(connection):
        params = get_hypothesis_params(connection, name)
        evaluator = hypotheses.EVALUATORS[name]
        decision = evaluator(current_price, features, params)
        if decision.should_enter:
            fitness, _ = fitness_fn(connection, name)
            candidates.append((fitness if fitness is not None else 0.0, SelectedHypothesis(name, decision, params)))
    if not candidates:
        return None
    candidates.sort(key=lambda c: c[0], reverse=True)
    return candidates[0][1]


def _all_at_bound(params: dict[str, float], specs: dict[str, tuple[float, float, float]]) -> bool:
    for key, (step, lower, upper) in specs.items():
        bound = upper if step > 0 else lower
        if params.get(key) != bound:
            return False
    return True


def _tighten(params: dict[str, float], specs: dict[str, tuple[float, float, float]]) -> tuple[dict[str, float], dict[str, tuple[float, float]]]:
    """One deterministic step toward stricter for every tunable field,
    clamped to its bound. Returns (new_params, {field: (old, new)}) for
    the audit log."""
    new_params = dict(params)
    changes: dict[str, tuple[float, float]] = {}
    for key, (step, lower, upper) in specs.items():
        old_value = params[key]
        new_value = max(lower, min(upper, old_value + step))
        if new_value != old_value:
            changes[key] = (old_value, new_value)
        new_params[key] = new_value
    return new_params, changes


def _log_event(event: dict[str, Any], log_path: Path | None) -> None:
    if log_path is None:
        return
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({**event, "at": _now_iso()}, default=str) + "\n")


def update_fitness_and_evolve(
    connection: sqlite3.Connection,
    fitness_fn: FitnessFn = hypothesis_fitness,
    log_path: Path | None = LOG_PATH,
) -> list[dict[str, Any]]:
    """Re-evaluates every currently-enabled hypothesis's fitness; on
    negative fitness with enough sample, tightens its parameters one
    deterministic step, or disables it if already at every bound. Never
    re-enables a disabled hypothesis - out of scope for this pass.
    `log_path=None` (backtest_runner.py's isolated runs use this) skips
    writing to the shared audit log - a backtest's own evolution steps
    are local to its temporary in-memory state, not part of live
    history."""
    applied: list[dict[str, Any]] = []
    for name in get_enabled_hypotheses(connection):
        fitness, sample_size = fitness_fn(connection, name)
        if fitness is None or fitness >= 0:
            continue
        state = get_hypothesis_state(connection, name)
        params = json.loads(state["params_json"])
        specs = MUTATION_SPECS[name]
        if _all_at_bound(params, specs):
            connection.execute(
                "UPDATE hypothesis_state SET enabled=0, updated_at=? WHERE name=?",
                (_now_iso(), name),
            )
            connection.commit()
            event = {"event": "DISABLED", "hypothesis": name, "fitness": fitness, "sample_size": sample_size}
            _log_event(event, log_path)
            applied.append(event)
            continue

        new_params, changes = _tighten(params, specs)
        connection.execute(
            "UPDATE hypothesis_state SET params_json=?, generation=generation+1, updated_at=? WHERE name=?",
            (json.dumps(new_params), _now_iso(), name),
        )
        connection.commit()
        event = {
            "event": "TIGHTENED", "hypothesis": name, "fitness": fitness,
            "sample_size": sample_size, "changes": changes,
        }
        _log_event(event, log_path)
        applied.append(event)
    return applied
