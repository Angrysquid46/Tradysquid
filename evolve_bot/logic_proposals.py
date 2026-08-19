"""Phase 12: AI-proposed logic evolution ("evolve" v2).

This is the gated ceiling ABOVE Phase 11's self-tuning: real trading-LOGIC
changes (not just a bounded parameter nudge) get proposed here with real
supporting evidence, written to a review queue, and NEVER auto-applied -
the owner explicitly signs off before anything here ever touches a real
trading rule. That's the actual difference from self_tuning.py, not just
a bigger number: self_tuning.py is allowed to act unsupervised because its
blast radius is capped by design (one owned parameter, one small fixed
step, hard bounds); this module can only ever recommend.

v1 scope: exit-parameter proposals. backtest.py already replays every real
cached trading day through a 5x5 stop_pct/target_pct grid (25 variants) -
this module aggregates each variant's real performance and checks whether
any variant meaningfully outperforms the evolve bot's own live exit rule
(currently a direct mirror of spy_scanner's live SPY_STOP_PCT/
TARGET_PCT - see engine.evaluate_exit_for_row). If one does, by a real
margin and with enough real trading-day coverage to say something, a
structured proposal is appended to the review queue. If not, "no evidence
yet" is the correct, honest output most of the time given how few real
trading days exist as of this writing - this module is not under any
pressure to produce a proposal on a schedule.

Real statistical trap this module explicitly guards against, not just
documents: comparing 25 exit-parameter variants against the same ~27 real
trading days is a multiple-comparisons situation - by chance alone, SOME
variant will look best even with zero real edge. Every proposal states
this plainly in its own caveats field, not as a footnote a reader could
miss, and MIN_TRADING_DAYS_FOR_PROPOSAL / MIN_ROWS_PER_VARIANT /
MIN_PROFIT_FACTOR_MARGIN below exist specifically to keep this module
quiet until there's real days and real margin to work with.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

import backtest
import discord_post
import logic_state

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import spy_scanner as s  # noqa: E402 - path must be set up first

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
LOGIC_PROPOSALS_PATH = STATE_DIR / "logic_proposals.jsonl"
PROPOSAL_STATE_PATH = STATE_DIR / "logic_proposal_state.json"

# A proposal only ever fires once real coverage is close to this backtest's
# current ceiling (~27 real cached days as of 2026-08-12) - waiting for
# near-complete coverage, not a partial slice, before saying anything.
MIN_TRADING_DAYS_FOR_PROPOSAL = 20

# A candidate variant needs at least this many real backtest rows before
# its profit factor is trusted at all - a tiny-n variant can show an
# extreme profit factor purely from having almost no losses to average
# against.
MIN_ROWS_PER_VARIANT = 30

# The candidate's profit factor must beat the live baseline's by at least
# this relative margin (1.25 = 25% better) before it's worth proposing -
# a small edge over 27 noisy real days isn't a real edge, it's noise.
MIN_PROFIT_FACTOR_MARGIN = 1.25


def _profit_factor(pl_wins: list[float], pl_losses: list[float]) -> float | None:
    """None (not 0, not infinity) when there's no meaningful ratio to
    compute - zero real losses in a real sample this small is itself a
    sign there isn't enough data yet, not a genuinely riskless variant."""
    gross_loss = abs(sum(pl_losses))
    if gross_loss == 0:
        return None
    return sum(pl_wins) / gross_loss


def aggregate_variant_performance(rows: list[dict[str, str]]) -> dict[str, dict[str, Any]]:
    """Real per-exit-variant performance from backtest.py's own labeled
    rows - grouped by variant_label, the same label backtest.py's grid
    already stamps on every row it writes."""
    by_variant: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        label = row.get("variant_label")
        if label:
            by_variant.setdefault(label, []).append(row)

    stats: dict[str, dict[str, Any]] = {}
    for label, variant_rows in by_variant.items():
        wins = [r for r in variant_rows if r.get("outcome") == "WIN"]
        losses = [r for r in variant_rows if r.get("outcome") == "LOSS"]
        pl_wins = [float(r["pl_pct"]) for r in wins if r.get("pl_pct")]
        pl_losses = [float(r["pl_pct"]) for r in losses if r.get("pl_pct")]
        all_pl = [float(r["pl_pct"]) for r in variant_rows if r.get("pl_pct")]
        stats[label] = {
            "n_rows": len(variant_rows),
            "n_trading_days": len({r["trading_day"] for r in variant_rows if r.get("trading_day")}),
            "win_rate": round(len(wins) / len(variant_rows), 4) if variant_rows else None,
            "avg_pl_pct": round(sum(all_pl) / len(all_pl), 2) if all_pl else None,
            "profit_factor": _profit_factor(pl_wins, pl_losses),
        }
    return stats


def live_baseline_variant_label() -> str:
    """The variant label representing whatever is ACTUALLY the live exit
    rule right now: a previously-applied Phase 12 override if one is
    active (logic_state.load_active_override), or spy_scanner's own live
    default otherwise. Reading only the spy_scanner default (the
    original version of this function) meant an already-applied proposal
    kept getting "re-proposed" against a stale baseline forever, since
    the comparison never noticed an override was already live - found
    from LOGIC-20260813-161926 recommending stop_20_target_50 against a
    claimed "live default" of stop_50_target_50, two days after
    stop_20_target_50 had already been reviewed, approved, and applied
    (LOGIC-20260812-223833)."""
    return logic_state.active_variant_params()["variant_label"]


def evaluate_exit_parameter_proposal(rows: list[dict[str, str]]) -> dict[str, Any]:
    """The pure evaluation core - real aggregated stats in, a real
    decision out, no file I/O. Only ever returns "candidate found" when
    every gate (baseline computable, enough real day coverage, enough
    rows on the candidate, a real margin over baseline) is satisfied."""
    baseline_label = live_baseline_variant_label()
    stats = aggregate_variant_performance(rows)
    baseline = stats.get(baseline_label)
    if baseline is None or baseline["profit_factor"] is None:
        return {"status": "no baseline evidence yet", "baseline_variant": baseline_label}

    n_days_covered = max((data["n_trading_days"] for data in stats.values()), default=0)
    if n_days_covered < MIN_TRADING_DAYS_FOR_PROPOSAL:
        return {
            "status": "not enough real trading-day coverage yet",
            "n_trading_days_covered": n_days_covered,
            "n_needed": MIN_TRADING_DAYS_FOR_PROPOSAL,
        }

    candidates = [
        (label, data)
        for label, data in stats.items()
        if label != baseline_label and data["n_rows"] >= MIN_ROWS_PER_VARIANT and data["profit_factor"] is not None
    ]
    if not candidates:
        return {"status": "no candidate variant has enough rows to compare"}

    best_label, best = max(candidates, key=lambda item: item[1]["profit_factor"])
    if best["profit_factor"] < baseline["profit_factor"] * MIN_PROFIT_FACTOR_MARGIN:
        return {
            "status": "no variant meaningfully beats the live baseline",
            "baseline_variant": baseline_label,
            "baseline_profit_factor": baseline["profit_factor"],
            "best_alternative_variant": best_label,
            "best_alternative_profit_factor": best["profit_factor"],
        }

    return {
        "status": "candidate found",
        "baseline_variant": baseline_label,
        "baseline_stats": baseline,
        "proposed_variant": best_label,
        "proposed_stats": best,
    }


def _read_backtest_rows() -> list[dict[str, str]]:
    if not backtest.BACKTEST_TRADES_PATH.exists():
        return []
    with backtest.BACKTEST_TRADES_PATH.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _training_file_hash() -> str | None:
    try:
        return hashlib.sha256(backtest.BACKTEST_TRADES_PATH.read_bytes()).hexdigest()
    except OSError:
        return None


def _load_state() -> dict[str, Any] | None:
    try:
        return json.loads(PROPOSAL_STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_state(state: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    PROPOSAL_STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _append_proposal(entry: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    with LOGIC_PROPOSALS_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")


def record_resolution(proposal_id: str, new_status: str) -> None:
    """Called by apply_proposal.py once a proposal has actually been
    applied (or otherwise resolved) - keeps this module's OWN
    already-pending tracking in sync with the real record. Without this,
    run_proposal_cycle() would keep reporting "already proposed,
    awaiting owner review" forever for a proposal that's since been
    applied, since its internal state only ever tracked
    last_proposal_status at generation time and had no way to learn it
    later changed. Only touches the state if it's still about the SAME
    proposal currently tracked (last_proposal_id matches) - a newer
    proposal generated in the meantime should never have its own pending
    status clobbered by a resolution event for an older one."""
    state = _load_state()
    if state and state.get("last_proposal_id") == proposal_id:
        _save_state({**state, "last_proposal_status": new_status})


def _build_proposal(result: dict[str, Any]) -> dict[str, Any]:
    proposed = result["proposed_stats"]
    baseline = result["baseline_stats"]
    return {
        "proposal_id": f"LOGIC-{time.strftime('%Y%m%d-%H%M%S')}",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "category": "exit_parameter_change",
        "current": {"variant": result["baseline_variant"], **baseline},
        "proposed": {"variant": result["proposed_variant"], **proposed},
        "reasoning": (
            f"Across {proposed['n_trading_days']} real cached trading days, exit variant "
            f"{result['proposed_variant']} shows a profit factor of {proposed['profit_factor']:.2f} "
            f"({proposed['n_rows']} rows, {proposed['win_rate'] * 100:.0f}% win rate) vs the live "
            f"default {result['baseline_variant']}'s {baseline['profit_factor']:.2f} "
            f"({baseline['n_rows']} rows, {baseline['win_rate'] * 100:.0f}% win rate)."
        ),
        "caveats": [
            "Backtest data mixes real Robinhood option prices with Black-Scholes synthetic "
            "fallback pricing over a currently small, capped real trading-day window - not a "
            "live-verified result.",
            "This compares 25 exit-parameter variants against the same real trading days - a "
            "multiple-comparisons situation where some variant looks best by chance alone even "
            "with zero real edge. Treat this as a candidate worth tracking as more real data "
            "accumulates, not a proven edge.",
            "NOT auto-applied. Applying this would mean parameterizing engine.py's exit call "
            "(currently mirrors spy_scanner's live SPY_STOP_PCT/TARGET_PCT directly) and "
            "requires explicit owner sign-off.",
        ],
        "status": "pending_owner_review",
    }


def run_proposal_cycle() -> dict[str, Any]:
    """Safe to call on any cadence, or none - same "cheap, idempotent,
    only acts on real change" shape as retrain_loop/self_tuning. Never
    re-proposes the exact same variant while an identical proposal is
    still sitting unreviewed, so the queue doesn't fill up with
    duplicates of a proposal the owner hasn't looked at yet."""
    rows = _read_backtest_rows()
    result = evaluate_exit_parameter_proposal(rows)
    current_hash = _training_file_hash()
    state = _load_state()

    if result["status"] != "candidate found":
        _save_state({**(state or {}), "last_considered_file_hash": current_hash, "last_evaluation_status": result["status"]})
        return result

    already_pending = (
        state is not None
        and state.get("last_considered_file_hash") == current_hash
        and state.get("last_proposed_variant") == result["proposed_variant"]
        and state.get("last_proposal_status") == "pending_owner_review"
    )
    if already_pending:
        return {**result, "status": "already proposed, awaiting owner review", "proposal_id": state.get("last_proposal_id")}

    proposal = _build_proposal(result)
    _append_proposal(proposal)
    _save_state(
        {
            "last_considered_file_hash": current_hash,
            "last_proposed_variant": result["proposed_variant"],
            "last_proposal_status": "pending_owner_review",
            "last_proposal_id": proposal["proposal_id"],
        }
    )
    _post_new_proposal_to_discord(proposal)
    return {**result, "status": "proposed", "proposal_id": proposal["proposal_id"]}


def _post_new_proposal_to_discord(proposal: dict[str, Any]) -> None:
    """Posting is a side effect of a real proposal existing, never a
    precondition for it - a Discord outage must never prevent a real,
    evidence-backed proposal from landing in the review queue file,
    which is the actual source of truth (weekly_review.py reads it
    directly regardless of whether this post succeeds).

    Upserted under one stable key, not posted fresh - only one proposal
    can ever be pending at a time (see run_proposal_cycle's already_pending
    check), so a "new" proposal object appearing again after a retrain
    (which happens often now that daily data pulls are automated - see
    #194) is usually the SAME recommendation re-surfacing with a fresh
    hash, not new information. Owner: "it keeps spamming the same thing
    over and over, we just need 1." Rendered as a real embed
    (spy_scanner.discord_card) so it matches every other card's look -
    owner: "i want them to have card formats to so they are easier for
    me to read.\""""
    lines = [
        f"## New Phase 12 Proposal · {proposal['proposal_id']}",
        "### Change",
        f"`{proposal['current']['variant']}` -> `{proposal['proposed']['variant']}`",
        "### Reasoning",
        proposal["reasoning"],
        "### Caveats",
        "\n".join(f"- {caveat}" for caveat in proposal["caveats"]),
        "### Status",
        "Pending owner review - not applied.",
    ]
    content = "\n".join(lines)
    try:
        discord_post.upsert_message(
            "reviews", "pending-proposal", content,
            embed=s.discord_card(content, footer_suffix=proposal["proposal_id"]),
        )
    except discord_post.DiscordPostError:
        pass


if __name__ == "__main__":
    print(json.dumps(run_proposal_cycle(), indent=2))
