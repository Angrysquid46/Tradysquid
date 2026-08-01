"""Recover closed paper-trade rows from the durable Discord wins/losses archive.

The recovery is additive and idempotent. Existing local rows always win. Historical
facts absent from Discord are explicitly marked unavailable rather than invented.
"""

from __future__ import annotations

import re
import os
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

import run_with_env
import ford_scan


CT = ZoneInfo("America/Chicago")


def number(value: str) -> float | None:
    cleaned = re.sub(r"[^0-9.\-]", "", value.replace(",", ""))
    return ford_scan.as_float(cleaned)


def field(text: str, label: str) -> str:
    match = re.search(rf"\*\*{re.escape(label)}:\*\*\s*([^\n]+)", text)
    return match.group(1).strip() if match else ""


def archive_messages(tracker: ford_scan.DiscordTracker) -> list[dict]:
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    by_name = {
        str(item.get("name") or ""): str(item.get("id") or "")
        for item in channels
        if item.get("type") == 0
    }
    result: list[dict] = []
    for name in ("wins", "losses"):
        channel_id = by_name.get(name)
        if not channel_id:
            continue
        before = ""
        while True:
            path = f"/channels/{channel_id}/messages?limit=100"
            if before:
                path += f"&before={before}"
            page = tracker._request("GET", path)
            if not page:
                break
            result.extend(page)
            before = str(page[-1].get("id") or "")
            if len(page) < 100:
                break
    return result


def parse_closed_card(message: dict) -> dict[str, str] | None:
    text = ford_scan.message_search_text(message)
    title = re.search(
        r"\b([A-Z]{1,6})\s+#(\d{3})\s+·\s+(WIN|LOSS|FLAT|SCRATCH)\s+·\s+([^\n]+)",
        text,
    )
    if not title:
        return None
    ticker, sequence, outcome, label = title.groups()
    closed_text = field(text, "Closed")
    closed_match = re.search(r"(\d{2}/\d{2}/\d{2})\s+(\d{1,2}:\d{2}\s+[AP]M)", closed_text)
    if not closed_match:
        return None
    closed_at = datetime.strptime(
        " ".join(closed_match.groups()), "%m/%d/%y %I:%M %p"
    ).replace(tzinfo=CT)
    expiration_text = field(text, "Expiration")
    expiration = ""
    try:
        expiration = datetime.strptime(expiration_text[:8], "%m/%d/%y").date().isoformat()
    except ValueError:
        pass
    kind = "put" if "PUT" in label else "call"
    play_type = "SPREAD" if "SPREAD" in label else "REGULAR"
    if play_type != "SPREAD" and expiration:
        dte = (datetime.fromisoformat(expiration).date() - closed_at.date()).days
        play_type = "SWING" if dte > 14 else "REGULAR"
    position_lines = re.findall(r"(?:BUY|SELL)\s+1\s+[A-Z]{1,6}\s+([0-9.]+)\s+(?:CALL|PUT)", text)
    strike = "/".join(position_lines[:2]) if play_type == "SPREAD" else (position_lines[0] if position_lines else "")
    entry_label = "Entry credit" if "Entry credit" in text else "Entry debit"
    exit_label = "Exit debit" if entry_label == "Entry credit" else "Exit credit"
    entry = number(field(text, entry_label))
    exit_value = number(field(text, exit_label))
    realized = number(field(text, "Realized P/L"))
    return_pct = number(field(text, "Return"))
    mfe = number(field(text, "MFE"))
    mae = number(field(text, "MAE"))
    journal = re.search(r"discord\.com/channels/\d+/(\d+)", text)
    message_id = str(message.get("id") or "")
    row = ford_scan.blank_row()
    row.update(
        {
            "trade_id": f"{ticker}-ARCHIVE-{message_id[-9:]}",
            "timestamp": closed_at.isoformat(),
            "action": "SELL open" if play_type == "SPREAD" else "BUY open",
            "play_type": play_type,
            "ticker": ticker,
            "call_or_put": kind,
            "strike": strike,
            "expiration": expiration,
            "cost_or_credit": f"{entry or 0:.2f} {'credit' if entry_label == 'Entry credit' else 'debit'}",
            "entry_price": ford_scan.round_or_blank(entry, 2),
            "exit_price": ford_scan.round_or_blank(exit_value, 2),
            "entry_contract_value": ford_scan.round_or_blank((entry or 0) * 100, 0),
            "exit_contract_value": ford_scan.round_or_blank((exit_value or 0) * 100, 0),
            "result_price_source": "discord-closed-result-archive",
            "setup_reason": "Historical entry setup was not present in the retained closed-result card.",
            "market_regime": "Not recorded",
            "thesis": "Historical thesis unavailable; the retained closed-result card did not record it.",
            "entry_confirmation": "Not recorded in the retained historical evidence.",
            "invalidation": f"Recorded close reason: {field(text, 'Close reason') or outcome}.",
            "risk_plan": "Historical risk plan was not recorded in the retained closed-result card.",
            "learning_plan": "Apply the full Learning Center checklist during review; do not invent missing entry evidence.",
            "evidence_limitations": "Recovered from Discord closed-result evidence; absent entry facts remain unavailable.",
            "archive_sequence": sequence,
            "outcome": "LOSS" if outcome in {"LOSS", "SCRATCH"} else outcome,
            "pct_gain_loss": ford_scan.round_or_blank(return_pct, 1),
            "realized_pl_dollars": ford_scan.round_or_blank(realized, 0),
            "closed_at": closed_at.isoformat(),
            "max_favorable_pct": ford_scan.round_or_blank(mfe, 1),
            "max_adverse_pct": ford_scan.round_or_blank(mae, 1),
            "last_signal": field(text, "Close reason") or outcome,
            "last_evaluated_at": closed_at.isoformat(),
            "discord_thread_id": journal.group(1) if journal else "",
            "discord_status": outcome,
            "discord_format_version": "" if journal else ford_scan.DISCORD_FORMAT_VERSION,
        }
    )
    return row


def same_trade(existing: dict[str, str], recovered: dict[str, str]) -> bool:
    if str(existing.get("ticker") or "").upper() != recovered["ticker"]:
        return False
    if str(existing.get("outcome") or "").upper() != recovered["outcome"]:
        return False
    existing_sequence = existing.get("archive_sequence") or existing.get("trade_id", "").rsplit("-", 1)[-1]
    if existing_sequence != recovered.get("archive_sequence"):
        return False
    if str(existing.get("closed_at") or "")[:10] != str(recovered.get("closed_at") or "")[:10]:
        return False
    return True


def recover(*, dry_run: bool = False) -> dict[str, int]:
    ford_scan.DISCORD_BOT_TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    ford_scan.DISCORD_GUILD_ID = os.environ.get("DISCORD_GUILD_ID", "").strip()
    tracker = ford_scan.initialize_discord()
    if not tracker.ready:
        raise RuntimeError("Discord is unavailable")
    rows = ford_scan.read_log()
    report_state = ford_scan.read_report_state()
    generated_archive_message_ids = {
        str(message_id)
        for key, message_id in (report_state.get("messages") or {}).items()
        if str(key).startswith(("result:wins:", "result:losses:")) and "-ARCHIVE-" in str(key)
    }
    parsed_by_identity: dict[tuple[str, ...], tuple[str, dict[str, str]]] = {}
    for message in archive_messages(tracker):
        message_id = str(message.get("id") or "")
        if message_id in generated_archive_message_ids:
            continue
        recovered = parse_closed_card(message)
        if not recovered:
            continue
        identity = (
            recovered["ticker"],
            recovered["archive_sequence"],
            recovered["outcome"],
            recovered["closed_at"][:10],
        )
        existing = parsed_by_identity.get(identity)
        if not existing or message_id > existing[0]:
            if existing and not recovered.get("discord_thread_id"):
                recovered["discord_thread_id"] = existing[1].get("discord_thread_id", "")
            parsed_by_identity[identity] = (message_id, recovered)
        elif recovered.get("discord_thread_id") and not existing[1].get("discord_thread_id"):
            existing[1]["discord_thread_id"] = recovered["discord_thread_id"]
    parsed = [item[1] for item in parsed_by_identity.values()]
    added = 0
    for recovered in parsed:
        if any(same_trade(existing, recovered) for existing in rows):
            continue
        rows.append(recovered)
        added += 1
    if not dry_run:
        ford_scan.write_log(rows)
        report_state = ford_scan.read_report_state()
        routed = set(report_state.get("routed_closed_trade_ids") or [])
        routed.update(row["trade_id"] for row in rows if row.get("outcome") != "OPEN")
        report_state["routed_closed_trade_ids"] = sorted(routed)
        ford_scan.write_report_state(report_state)
    return {
        "unique_archive_cards": len(parsed),
        "added": added,
        "canonical_rows": len(rows),
        "dry_run": dry_run,
    }


def main() -> int:
    run_with_env.load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    print(recover(dry_run=args.dry_run))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
