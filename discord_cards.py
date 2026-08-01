"""Universal Discord card styling and evidence-based trade review enrichment.

Every bot-generated Discord message is rendered as an embed/card. The module also
upgrades the legacy examples-and-reviews template into an individualized learning
record and stores that record under state/ for later strategy analysis.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LEARNING_RECORD_PATH = ROOT / "state" / "trade-learning-records.json"
SOURCE_PREFIX = "source:"
FOOTER_PREFIX = "Tradysquids • Paper Trading"
DEFAULT_COLOR = 0x5865F2
LEARNING_COLOR = 0x9B59B6
SUCCESS_COLOR = 0x57F287
LOSS_COLOR = 0xED4245
WARNING_COLOR = 0xFEE75C
STATUS_COLOR = 0x3498DB
INFO_COLOR = 0x1ABC9C

REVIEW_PATTERN = re.compile(
    r"Rotating recorded example\s*\n"
    r"(?P<summary>[^\n]+)\n"
    r"Selected because:\s*(?P<reasons>.*?)\n"
    r"Entry\s*(?P<entry>[-+]?\$?\d+(?:\.\d+)?)\s*·\s*"
    r"exit\s*(?P<exit>[-+]?\$?\d+(?:\.\d+)?)\s*·\s*"
    r"(?P<outcome>WIN|LOSS)\s*·\s*"
    r"net\s*(?P<net>[-+]?\$?\d+(?:\.\d+)?)",
    re.IGNORECASE | re.DOTALL,
)

BULLISH_PATTERNS = (
    "above its 20-day",
    "above the 20-day",
    "intraday move is bullish",
    "above intraday vwap",
    "holding above intraday vwap",
    "momentum is above",
    "trend is above",
    "higher high",
    "bullish",
)
BEARISH_PATTERNS = (
    "below its 20-day",
    "below the 20-day",
    "intraday move is bearish",
    "below intraday vwap",
    "holding below intraday vwap",
    "momentum is below",
    "trend is below",
    "lower low",
    "bearish",
)
NEUTRAL_PATTERNS = ("balanced", "neutral", "range", "mixed", "conflict")


def source_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def _parse_number(value: str) -> float | None:
    try:
        return float(value.replace("$", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _classify_signal(reason: str) -> str:
    lowered = reason.lower()
    if any(pattern in lowered for pattern in NEUTRAL_PATTERNS):
        return "neutral"
    bullish = any(pattern in lowered for pattern in BULLISH_PATTERNS)
    bearish = any(pattern in lowered for pattern in BEARISH_PATTERNS)
    if bullish and not bearish:
        return "bullish"
    if bearish and not bullish:
        return "bearish"
    return "unknown"


def parse_trade_review(content: str) -> dict[str, Any] | None:
    normalized = content.replace("\r\n", "\n")
    match = REVIEW_PATTERN.search(normalized)
    if not match:
        return None

    summary_parts = [part.strip() for part in match.group("summary").split("·")]
    trade_id = summary_parts[0] if summary_parts else ""
    ticker = summary_parts[1] if len(summary_parts) > 1 else ""
    contract = summary_parts[2] if len(summary_parts) > 2 else ""
    expiration = (
        summary_parts[3].removeprefix("exp ").strip()
        if len(summary_parts) > 3
        else ""
    )
    reasons = [
        reason.strip(" .")
        for reason in match.group("reasons").split(";")
        if reason.strip()
    ]

    lowered = normalized.lower()
    if "requires bearish evidence" in lowered:
        bias = "bearish"
    elif "requires bullish evidence" in lowered:
        bias = "bullish"
    elif "neutral" in lowered or "range" in lowered:
        bias = "neutral"
    else:
        bias = "unknown"

    structure = (
        "credit spread"
        if "net credit" in lowered or "credit capture" in lowered
        else "long option"
    )
    aligned: list[str] = []
    opposing: list[str] = []
    neutral: list[str] = []
    unknown: list[str] = []
    for reason in reasons:
        classification = _classify_signal(reason)
        if classification == "neutral":
            neutral.append(reason)
        elif classification == "unknown":
            unknown.append(reason)
        elif bias in {"bullish", "bearish"} and classification == bias:
            aligned.append(reason)
        elif (
            bias in {"bullish", "bearish"}
            and classification in {"bullish", "bearish"}
        ):
            opposing.append(reason)
        else:
            neutral.append(reason)

    return {
        "source_text": normalized,
        "trade_id": trade_id,
        "ticker": ticker,
        "contract": contract,
        "expiration": expiration,
        "reasons": reasons,
        "bias": bias,
        "structure": structure,
        "entry": _parse_number(match.group("entry")),
        "exit": _parse_number(match.group("exit")),
        "outcome": match.group("outcome").upper(),
        "net": _parse_number(match.group("net")),
        "aligned": aligned,
        "opposing": opposing,
        "neutral": neutral,
        "unknown": unknown,
    }


def _diagnose_review(review: dict[str, Any]) -> dict[str, Any]:
    entry = review.get("entry")
    exit_value = review.get("exit")
    outcome = str(review.get("outcome") or "").upper()
    structure = str(review.get("structure") or "")
    mechanism = "The recorded summary does not contain enough price information to explain the option repricing."
    trigger = "The exact close trigger was not stored."
    cause_tags: list[str] = []
    recommendations: list[str] = []

    if structure == "credit spread" and entry and exit_value is not None:
        change_pct = (exit_value - entry) / entry * 100
        if outcome == "WIN":
            mechanism = (
                f"The spread was sold for a **{entry:.2f} credit** and bought back "
                f"for **{exit_value:.2f}**. Its cost to close fell "
                f"**{abs(change_pct):.0f}%**, so the seller retained part of the credit."
            )
            target_cost = entry * 0.50
            if exit_value <= target_cost + 1e-9:
                trigger = (
                    f"The recorded 50% credit-capture target was reached or exceeded: "
                    f"target cost **{target_cost:.2f}**, exit **{exit_value:.2f}**."
                )
                cause_tags.append("TARGET_CAPTURE")
            else:
                trigger = (
                    "The position closed profitably before the complete 50% target. "
                    "The summary does not identify the exact early-close trigger."
                )
                cause_tags.append("PROFITABLE_EARLY_CLOSE")
        else:
            mechanism = (
                f"The spread was sold for a **{entry:.2f} credit** but cost "
                f"**{exit_value:.2f}** to close. The liability expanded "
                f"**{change_pct:.0f}%**, producing the recorded loss."
            )
            stop_cost = entry * 2.0
            if exit_value >= stop_cost - 1e-9:
                trigger = (
                    f"The 2×-credit stop threshold was **{stop_cost:.2f}**; "
                    f"the **{exit_value:.2f}** exit was beyond it. The stop explains "
                    "when the trade ended, not why the spread widened."
                )
                cause_tags.append("CREDIT_STOP")
            else:
                trigger = (
                    "The trade closed at a loss, but the summary does not identify "
                    "a stop, expiration, or manual-close trigger."
                )
                cause_tags.append("LOSS_TRIGGER_UNKNOWN")
    elif entry and exit_value is not None:
        change_pct = (exit_value - entry) / entry * 100
        if outcome == "WIN":
            mechanism = (
                f"The option premium rose from **{entry:.2f}** to **{exit_value:.2f}**, "
                f"a **{change_pct:.0f}%** gain."
            )
            target = entry * 1.20
            if exit_value >= target - 1e-9:
                trigger = (
                    f"The recorded +20% target was **{target:.2f}** and the exit "
                    f"was **{exit_value:.2f}**."
                )
                cause_tags.append("TARGET_HIT")
            else:
                trigger = (
                    "The position closed profitably, but the exact exit trigger "
                    "was not stored in this summary."
                )
                cause_tags.append("PROFITABLE_EARLY_CLOSE")
        else:
            mechanism = (
                f"The option premium fell from **{entry:.2f}** to **{exit_value:.2f}**, "
                f"a **{abs(change_pct):.0f}%** decline."
            )
            stop = entry * 0.85
            if exit_value <= stop + 1e-9:
                trigger = (
                    f"The recorded -15% stop reference was **{stop:.2f}** and the "
                    f"exit was **{exit_value:.2f}**."
                )
                cause_tags.append("LONG_STOP")
            else:
                trigger = (
                    "The trade closed at a loss, but the exact exit trigger "
                    "was not stored in this summary."
                )
                cause_tags.append("LOSS_TRIGGER_UNKNOWN")

    if review.get("neutral"):
        cause_tags.append("REGIME_CONFLICT")
        recommendations.append(
            "Do not treat a balanced or neutral combined regime as strong confirmation for a directional trade."
        )
    if review.get("opposing"):
        cause_tags.append("OPPOSING_SIGNALS")
        recommendations.append(
            "Require aligned directional evidence to exceed opposing evidence by a defined score margin before entry."
        )

    recommendations.extend(
        [
            "Store underlying price, VWAP relation, trend score, IV, delta, theta, spread width, DTE, and timestamp at both entry and exit.",
            "Record the exit trigger separately from root-cause analysis; a stop says when the trade ended, not why the thesis failed.",
            "Aggregate cause tags by strategy, ticker, regime, DTE, and delta before proposing scanner-rule changes.",
        ]
    )
    return {
        "mechanism": mechanism,
        "trigger": trigger,
        "cause_tags": sorted(set(cause_tags)),
        "recommendations": recommendations,
    }


def _missing_review_evidence(review: dict[str, Any]) -> list[str]:
    lowered = str(review.get("source_text") or "").lower()
    groups = [
        ("underlying entry and exit prices", ("underlying entry", "underlying exit")),
        ("exit-time IV and Greeks", ("exit iv", "delta at exit", "theta at exit")),
        ("exit-time VWAP and trend state", ("exit vwap", "exit trend")),
        ("fill and slippage detail", ("slippage", "fill quality")),
    ]
    return [
        label
        for label, keys in groups
        if not all(key in lowered for key in keys)
    ]


def _store_learning_record(review: dict[str, Any], diagnosis: dict[str, Any]) -> None:
    trade_id = str(review.get("trade_id") or "").strip()
    if not trade_id:
        return
    try:
        payload = json.loads(LEARNING_RECORD_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {"version": 1, "records": {}}
    if not isinstance(payload, dict):
        payload = {"version": 1, "records": {}}
    records = payload.setdefault("records", {})
    if not isinstance(records, dict):
        records = {}
        payload["records"] = records
    records[trade_id] = {
        "trade_id": trade_id,
        "ticker": review.get("ticker"),
        "contract": review.get("contract"),
        "expiration": review.get("expiration"),
        "structure": review.get("structure"),
        "intended_bias": review.get("bias"),
        "outcome": review.get("outcome"),
        "entry": review.get("entry"),
        "exit": review.get("exit"),
        "net": review.get("net"),
        "aligned_evidence": review.get("aligned"),
        "opposing_evidence": review.get("opposing"),
        "neutral_evidence": review.get("neutral"),
        "unclassified_evidence": review.get("unknown"),
        "cause_tags": diagnosis.get("cause_tags"),
        "recommendations": diagnosis.get("recommendations"),
        "missing_evidence": _missing_review_evidence(review),
        "review_version": 2,
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    LEARNING_RECORD_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = LEARNING_RECORD_PATH.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(LEARNING_RECORD_PATH)


def enrich_trade_review(content: str) -> str:
    review = parse_trade_review(content)
    if not review:
        return content

    diagnosis = _diagnose_review(review)
    _store_learning_record(review, diagnosis)
    aligned = list(review.get("aligned") or [])
    opposing = list(review.get("opposing") or [])
    neutral = list(review.get("neutral") or [])
    unknown = list(review.get("unknown") or [])

    if aligned and len(aligned) >= len(opposing) + 2 and not neutral:
        quality = "strongly aligned"
    elif opposing or neutral:
        quality = "mixed"
    else:
        quality = "insufficiently recorded"

    signal_sections: list[str] = []
    for heading, values, marker in (
        ("Aligned evidence", aligned, "✅"),
        ("Opposing evidence", opposing, "⚠️"),
        ("Neutral or conflicting evidence", neutral, "➖"),
        ("Unclassified evidence", unknown, "❔"),
    ):
        if values:
            signal_sections.append(
                f"**{heading}**\n" + "\n".join(f"{marker} {value}" for value in values)
            )

    net = review.get("net")
    net_text = "unavailable"
    if isinstance(net, (int, float)):
        net_text = f"{'-' if net < 0 else '+'}${abs(net):.0f}"
    entry = review.get("entry")
    exit_value = review.get("exit")
    result_heading = (
        "Why it worked" if review.get("outcome") == "WIN" else "Why it failed"
    )

    if review.get("outcome") == "LOSS":
        if opposing or neutral:
            result_explanation = (
                "The entry contained meaningful conflicting evidence. The trade "
                f"depended on the {review.get('bias')} signals winning quickly enough, "
                "but the option position repriced against it first."
            )
        else:
            result_explanation = (
                "The option position repriced adversely. The stored summary does "
                "not contain enough exit-market evidence to prove whether direction, "
                "IV, time, liquidity, or a combination was dominant."
            )
    elif len(aligned) > len(opposing):
        result_explanation = (
            "The recorded setup evidence was directionally aligned and the option "
            "position repriced favorably. Exact attribution between underlying "
            "movement, time decay, and IV change remains limited by the missing exit snapshot."
        )
    else:
        result_explanation = (
            "The option position repriced profitably, but the entry evidence was mixed. "
            "This win should not be treated as proof that the conflicted setup was sound "
            "without complete exit-market evidence."
        )

    lines = [
        f"# {review.get('outcome')} Review · {review.get('trade_id')}",
        (
            f"**Trade:** {review.get('ticker') or 'Unknown'} · "
            f"{review.get('contract') or 'contract unavailable'} · "
            f"expires {review.get('expiration') or 'unknown'}"
        ),
        (
            f"**Result:** entry {entry:.2f} · exit {exit_value:.2f} · net {net_text}"
            if isinstance(entry, (int, float)) and isinstance(exit_value, (int, float))
            else f"**Result:** {review.get('outcome')} · net {net_text}"
        ),
        "",
        "## Why this specific trade was selected",
        (
            f"The scanner intended a **{review.get('bias')} "
            f"{review.get('structure')}**. The recorded entry evidence was "
            f"**{quality}**, rather than a generic strategy description."
        ),
        *signal_sections,
        "",
        "## What actually happened",
        diagnosis["mechanism"],
        diagnosis["trigger"],
        "",
        f"## {result_heading}",
        result_explanation,
        "",
        "## Learning record for TradeBot",
        (
            "**Cause tags:** "
            + (
                ", ".join(diagnosis["cause_tags"])
                if diagnosis["cause_tags"]
                else "RESULT_RECORDED_ONLY"
            )
        ),
        *[f"• {item}" for item in diagnosis["recommendations"]],
        "",
        "## Evidence still missing",
        *[f"• {item}" for item in _missing_review_evidence(review)],
        "",
        (
            "_This record separates the mechanical exit from the probable setup "
            "cause and does not invent data that was never stored._"
        ),
    ]
    return "\n".join(lines)


def _strip_title_markup(value: str) -> str:
    value = value.strip()
    value = re.sub(r"^#{1,6}\s*", "", value)
    value = value.strip("*_` ")
    return value[:256] or "Tradysquids Update"


def _title_and_description(content: str) -> tuple[str, str]:
    lines = content.strip().splitlines()
    if not lines:
        return "Tradysquids Update", ""

    title_index: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("# "):
            title_index = index
            break
    if title_index is None:
        for index, line in enumerate(lines):
            stripped = line.strip()
            if (
                stripped.startswith("**")
                and stripped.endswith("**")
                and len(stripped) <= 180
                and "Tradysquids curriculum" not in stripped
            ):
                title_index = index
                break
    if title_index is None:
        first = lines[0].strip()
        if len(first) <= 120 and not first.startswith(("-", "•", "`")):
            title_index = 0

    if title_index is None:
        return "Tradysquids Update", content[:4096]

    title = _strip_title_markup(lines[title_index])
    body_lines = lines[:title_index] + lines[title_index + 1 :]
    description = "\n".join(body_lines).strip()
    return title, description[:4096]


def card_color(content: str, title: str = "") -> int:
    lowered = f"{title}\n{content}".lower()
    if any(term in lowered for term in (" loss", "failed", "error", "stop hit", "❌")):
        return LOSS_COLOR
    if any(term in lowered for term in (" win", "target hit", "success", "✅")):
        return SUCCESS_COLOR
    if any(term in lowered for term in ("warning", "paused", "hold", "⚠️")):
        return WARNING_COLOR
    if any(
        term in lowered
        for term in (
            "curriculum",
            "learning",
            "explain",
            "greek",
            "options basics",
            "stock basics",
        )
    ):
        return LEARNING_COLOR
    if any(term in lowered for term in ("status", "health", "provider", "online")):
        return STATUS_COLOR
    if any(term in lowered for term in ("scanner", "quote", "chart", "market")):
        return INFO_COLOR
    return DEFAULT_COLOR


def style_message_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return payload
    if payload.get("embeds"):
        return payload
    content = str(payload.get("content") or "").strip()
    if not content:
        return payload

    enriched = enrich_trade_review(content)
    title, description = _title_and_description(enriched)
    digest = source_hash(enriched)
    embed = {
        "title": title,
        "description": description or "\u200b",
        "color": card_color(enriched, title),
        "footer": {"text": f"{FOOTER_PREFIX} • {SOURCE_PREFIX}{digest}"},
    }
    styled = dict(payload)
    styled["content"] = ""
    styled["embeds"] = [embed]
    styled.setdefault("allowed_mentions", {"parse": []})
    return styled


def message_has_source(message: dict[str, Any], content: str) -> bool:
    expected = f"{SOURCE_PREFIX}{source_hash(enrich_trade_review(content))}"
    for embed in message.get("embeds") or []:
        footer = str((embed.get("footer") or {}).get("text") or "")
        if expected in footer:
            return True
    return False


def message_is_backed(message: dict[str, Any]) -> bool:
    return bool(message.get("embeds"))
