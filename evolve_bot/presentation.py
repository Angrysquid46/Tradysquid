"""Phase 10: presentation layer - real charts and a stats card built from
real data (tradelog.py's closed live trades, weekly_review.py's
aggregated stats). NOT wired to Discord yet - deliberately deferred
until there's real trade volume worth showing, per the original design
("attach it to Discord last, not immediately"). These functions produce
real PNG artifacts from real data now, so the eventual Discord-posting
step is just "call this already-working function from a scheduled job,"
not new work.

Every function here returns None (renders nothing) rather than a
fabricated/empty chart when there isn't enough real data yet - a missing
artifact is honest; a chart with one flat line pretending to be a "curve"
is not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")  # no display backend in this environment - render to file only
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator

import weekly_review

# matplotlib treats a literal "$" in any ax.text()/title/label string as a
# mathtext delimiter (triggering inline math rendering), not a currency
# symbol - confirmed by actually looking at the rendered PNG, where every
# "$" vanished and the text after it rendered in italic math mode. Every
# dollar amount below goes through this so callers never have to
# remember to escape it themselves.
def _money(amount: float) -> str:
    return f"\\${amount:,.2f}"

ROOT = Path(__file__).resolve().parent
PRESENTATION_DIR = ROOT / "presentation_output"

# Phase 11 (rules-based self-tuning) doesn't exist yet, so this file has no
# real entries and reading it returns []. It's declared here, not in
# Phase 11's own module, because the log's shape is presentation's
# concern: Phase 11 just needs to append one JSON object per line here -
# {"timestamp": ..., "change": ..., "reasoning": ...} - no new
# presentation code required when it starts.
SELF_TUNING_LOG_PATH = ROOT / "state" / "self_tuning_log.jsonl"

# Visual identity - dark, high-contrast, deliberately chosen (not
# matplotlib defaults) to give this bot its own look, distinct from the
# other strategies' plain Discord embeds.
BACKGROUND = "#0b0e14"
PANEL = "#11151d"
GRID_COLOR = "#232a38"
TEXT_COLOR = "#d7dde5"
MUTED_TEXT = "#7c8798"
WIN_COLOR = "#39ff88"
LOSS_COLOR = "#ff4d5e"
ACCENT_COLOR = "#39ff88"
MONO_FONT = "DejaVu Sans Mono"


def equity_curve_series(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Real balance-over-time points from closed live trades, in
    chronological order - built directly from tradelog.py's own
    balance_before/balance_after bookkeeping on each row, never
    re-derived or estimated. The first point is the balance BEFORE the
    earliest closed trade, giving the curve a real starting value rather
    than an assumed one."""
    closed = sorted(
        (row for row in rows if row.get("outcome") in ("WIN", "LOSS", "SCRATCH") and row.get("closed_at")),
        key=lambda row: row["closed_at"],
    )
    if not closed:
        return []
    points = [{"timestamp": closed[0]["timestamp"], "balance": float(closed[0]["balance_before"]), "outcome": "START"}]
    for row in closed:
        points.append(
            {"timestamp": row["closed_at"], "balance": float(row["balance_after"]), "outcome": row["outcome"]}
        )
    return points


def compute_milestones(rows: list[dict[str, str]], bank_state: dict[str, Any]) -> list[dict[str, Any]]:
    """Real, checkable milestones only - each one is a plain fact about
    the actual data, never a fabricated or inferred achievement."""
    closed = [row for row in rows if row.get("outcome") in ("WIN", "LOSS", "SCRATCH")]
    wins = [row for row in closed if row["outcome"] == "WIN"]
    return [
        {
            "label": "First real trade closed",
            "achieved": bool(closed),
            "detail": f"{len(closed)} closed" if closed else "none yet",
        },
        {
            "label": "First real win",
            "achieved": bool(wins),
            "detail": f"{len(wins)} win(s)" if wins else "none yet",
        },
        {
            "label": "New all-time-high balance",
            "achieved": bank_state["all_time_high_balance"] > bank_state["starting_balance"],
            "detail": f"${bank_state['all_time_high_balance']:.2f}",
        },
        {
            "label": "Survived a bankroll reset",
            "achieved": bank_state["total_resets"] > 0,
            "detail": f"{bank_state['total_resets']} reset(s)",
        },
        {
            "label": "10 real closed trades",
            "achieved": len(closed) >= 10,
            "detail": f"{len(closed)}/10",
        },
    ]


def _style_axes(ax) -> None:
    ax.set_facecolor(PANEL)
    ax.grid(True, color=GRID_COLOR, linewidth=0.8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color(GRID_COLOR)
    ax.spines["bottom"].set_color(GRID_COLOR)
    ax.tick_params(colors=MUTED_TEXT, labelsize=9)
    for label in ax.get_xticklabels() + ax.get_yticklabels():
        label.set_fontfamily(MONO_FONT)


def render_equity_curve(rows: list[dict[str, str]], output_path: Path) -> Path | None:
    """Real matplotlib line chart of the actual balance trajectory across
    closed live trades. Returns None and writes nothing when there are
    fewer than 2 real points to plot (a single point isn't a curve)."""
    series = equity_curve_series(rows)
    if len(series) < 2:
        return None

    balances = [point["balance"] for point in series]
    x = list(range(len(series)))

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor(BACKGROUND)
    _style_axes(ax)

    ax.plot(x, balances, color=ACCENT_COLOR, linewidth=2.2, marker="o", markersize=4, zorder=3)
    ax.axhline(series[0]["balance"], color=MUTED_TEXT, linewidth=1, linestyle="--", alpha=0.6)
    for i, point in enumerate(series):
        if point["outcome"] == "LOSS":
            ax.scatter([i], [point["balance"]], color=LOSS_COLOR, s=28, zorder=4)

    # x is "closed trade #0, #1, #2..." - always whole numbers, never a
    # fractional tick like "0.4 trades" (matplotlib's default float
    # ticking on a 2-point series produced exactly that until fixed).
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

    ax.set_title(
        "SPY_EVOLVE — Live Bankroll", color=TEXT_COLOR, fontsize=14, fontfamily=MONO_FONT, loc="left", pad=14
    )
    ax.set_ylabel("Balance (USD)", color=MUTED_TEXT, fontsize=10, fontfamily=MONO_FONT)
    ax.set_xlabel(f"Closed trades (n={len(series) - 1})", color=MUTED_TEXT, fontsize=10, fontfamily=MONO_FONT)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path


def render_stats_card(data: dict[str, Any], output_path: Path) -> Path:
    """A compact real-numbers summary card - always renders (unlike the
    equity curve) since even "not enough data yet" is worth showing
    honestly rather than nothing at all."""
    live = data["live_trading"]
    shadow = data["shadow_mode"]
    backtest_data = data["backtest_training_data"]
    retraining = data["retraining"]

    # Wide enough that the longest real line ("Shadow trades: ... score
    # calibration: not enough data yet") doesn't run off the right edge -
    # found by actually viewing the rendered PNG, not by counting chars.
    fig, ax = plt.subplots(figsize=(9, 6), dpi=150)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    ax.axis("off")

    lines: list[tuple[str, str]] = [
        ("SPY_EVOLVE", ACCENT_COLOR),
        ("", TEXT_COLOR),
        (f"Bankroll: {_money(live['bankroll']['balance'])}", TEXT_COLOR),
        (
            f"  (started {_money(live['bankroll']['starting_balance'])}, "
            f"ATH {_money(live['bankroll']['all_time_high_balance'])})",
            MUTED_TEXT,
        ),
        (f"Run #{live['bankroll']['run_number']}  •  {live['bankroll']['total_resets']} reset(s)", MUTED_TEXT),
        ("", TEXT_COLOR),
        (
            f"Live trades: {live['n_closed']} closed, {live['n_open']} open"
            + (f"  •  {live['win_rate'] * 100:.0f}% win rate" if live["win_rate"] is not None else ""),
            TEXT_COLOR,
        ),
        (
            f"Shadow trades: {shadow['n_total_logged']} logged, {shadow['n_closed']} closed"
            + (
                "  •  score calibration: not enough data yet"
                if not shadow["score_calibration"]["enough_data_to_compare"]
                else f"  •  avg score W {shadow['score_calibration']['avg_score_on_wins']:.2f} / L {shadow['score_calibration']['avg_score_on_losses']:.2f}"
            ),
            TEXT_COLOR,
        ),
        ("", TEXT_COLOR),
        (
            f"Training data: {backtest_data['n_rows']} rows / {backtest_data['n_trading_days']} real days",
            TEXT_COLOR,
        ),
        (f"  ({backtest_data['n_real_priced_rows']} rows real-priced, rest synthetic)", MUTED_TEXT),
        (
            f"Retrains recorded: {retraining['n_retrains_recorded']}",
            TEXT_COLOR,
        ),
    ]
    if retraining["most_recent"]:
        metrics = retraining["most_recent"]["result"].get("metrics", {})
        auc = metrics.get("auc")
        if auc is not None:
            lines.append((f"  latest AUC: {auc:.3f} (small-sample, not validated)", MUTED_TEXT))

    y = 0.95
    for text, color in lines:
        weight = "bold" if text == "SPY_EVOLVE" else "normal"
        size = 16 if text == "SPY_EVOLVE" else 10.5
        ax.text(0.04, y, text, color=color, fontsize=size, fontfamily=MONO_FONT, fontweight=weight, transform=ax.transAxes)
        y -= 0.075

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path


def render_milestones(rows: list[dict[str, str]], bank_state: dict[str, Any], output_path: Path) -> Path:
    """A checklist card of compute_milestones()'s real, checkable
    milestones - achieved ones lit up in the win color with a filled
    marker, unachieved ones dimmed with a hollow marker and their real
    current progress shown alongside (e.g. "3/10"), never hidden. Always
    renders, same as the stats card - "0 of 5 achieved" is still a real,
    honest thing to show early on."""
    milestones = compute_milestones(rows, bank_state)

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=150)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    ax.axis("off")

    ax.text(
        0.04, 0.95, "SPY_EVOLVE — Milestones", color=ACCENT_COLOR, fontsize=16,
        fontfamily=MONO_FONT, fontweight="bold", transform=ax.transAxes,
    )

    y = 0.78
    for milestone in milestones:
        marker = "[x]" if milestone["achieved"] else "[ ]"
        color = WIN_COLOR if milestone["achieved"] else MUTED_TEXT
        ax.text(
            0.04, y, f"{marker}  {milestone['label']}", color=color, fontsize=12,
            fontfamily=MONO_FONT, transform=ax.transAxes,
        )
        ax.text(
            0.62, y, milestone["detail"], color=MUTED_TEXT, fontsize=10.5,
            fontfamily=MONO_FONT, transform=ax.transAxes,
        )
        y -= 0.16

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path


def _read_self_tuning_log() -> list[dict[str, Any]]:
    if not SELF_TUNING_LOG_PATH.exists():
        return []
    events = []
    for line in SELF_TUNING_LOG_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            events.append(json.loads(line))
    return events


def render_self_tuning_log(output_path: Path) -> Path | None:
    """Public self-tuning log card - reads Phase 11's real logged
    parameter-nudge events. Returns None and writes nothing when the log
    is missing or empty, same as the equity curve's "not enough real
    points yet" rule: Phase 11 (rules-based self-tuning) hasn't been built
    yet as of this writing, so this function is correctly inert until it
    exists and starts appending real events - a placeholder entry here
    would fabricate a tuning history that never happened."""
    events = _read_self_tuning_log()
    if not events:
        return None

    fig, ax = plt.subplots(figsize=(8, max(4.5, 0.9 + 0.35 * len(events))), dpi=150)
    fig.patch.set_facecolor(BACKGROUND)
    ax.set_facecolor(BACKGROUND)
    ax.axis("off")

    ax.text(
        0.04, 0.96, "SPY_EVOLVE — Self-Tuning Log", color=ACCENT_COLOR, fontsize=16,
        fontfamily=MONO_FONT, fontweight="bold", transform=ax.transAxes,
    )

    y = 0.86
    step = 0.9 / max(len(events), 1)
    for event in events[-20:]:
        timestamp = event.get("timestamp", "?")
        change = event.get("change", "?")
        reasoning = event.get("reasoning", "")
        ax.text(0.04, y, f"{timestamp}  {change}", color=TEXT_COLOR, fontsize=11, fontfamily=MONO_FONT, transform=ax.transAxes)
        if reasoning:
            y -= step * 0.5
            ax.text(0.06, y, reasoning, color=MUTED_TEXT, fontsize=9.5, fontfamily=MONO_FONT, transform=ax.transAxes)
        y -= step

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, facecolor=BACKGROUND)
    plt.close(fig)
    return output_path
