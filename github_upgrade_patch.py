"""Install owner-only Discord commands for the shared GitHub upgrade batch."""

from __future__ import annotations

import re
from typing import Any

import discord_command_bot as bot
import github_upgrade_bridge as bridge

COMMANDS = {"upgrade-add", "upgrade-list", "upgrade-ready", "upgrade-cancel"}
_INSTALLED = False


def _safe_error(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}"
    text = re.sub(r"(?i)(token|secret|password|api[_ -]?key)\s*[:=]\s*[^\s,;]+", r"\1=[REDACTED]", text)
    text = re.sub(r"\b(?:github_pat_|gh[opusr]_)[A-Za-z0-9_]+\b", "[REDACTED]", text)
    text = re.sub(r"\bsk-(?:proj-)?[A-Za-z0-9_-]+\b", "[REDACTED]", text)
    return text[:1000]


def _status_reply() -> str:
    status = bridge.batch_status()
    if status["state"] == "NONE":
        return "\n".join(
            [
                "📭 **No GitHub upgrade batch exists.**",
                "Use `/upgrade-add request:` or wait for a persistent automatic diagnostic.",
                f"**Next action:** {status['next_action']}",
            ]
        )
    lines = [
        f"📦 **Upgrade batch #{status['issue_number']} · {status['state']}**",
        f"Requests recorded: **{status['request_count']}**",
        f"GitHub: {status['issue_url']}",
    ]
    for request in (status.get("requests") or [])[:12]:
        lines.append(
            f"• **{request.get('request_number')} · {request.get('source')} · {request.get('status')}** "
            f"· {request.get('summary')} · **Next:** {request.get('next_action')}"
        )
    if status.get("request_count", 0) > 12:
        lines.append(f"• …and {status['request_count'] - 12} more request(s) in GitHub.")
    lines.append(f"**Batch next action:** {status['next_action']}")
    return "\n".join(lines)[:3900]


def _upgrade_destination() -> tuple[Any | None, str]:
    tracker = bot.spy_scanner.DiscordTracker(
        bot.spy_scanner.DISCORD_BOT_TOKEN,
        bot.spy_scanner.DISCORD_GUILD_ID,
    )
    if not tracker.enabled:
        return None, ""
    channels = tracker._request("GET", f"/guilds/{tracker.guild_id}/channels")
    for name in ("upgrade-requests", "upgrade-review"):
        channel = next(
            (
                item
                for item in channels
                if str(item.get("name") or "").casefold() == name
                and int(item.get("type") or 0) == 0
            ),
            None,
        )
        if channel:
            return tracker, str(channel["id"])
    return tracker, ""


def _mirror_upgrade_request(
    interaction: dict[str, Any],
    result: dict[str, Any],
    request_text: str,
) -> str:
    tracker, channel_id = _upgrade_destination()
    if not tracker or not channel_id:
        raise RuntimeError("The Discord upgrade-requests channel is missing.")
    content = "\n".join(
        [
            f"## Upgrade request {result['request_number']}",
            f"**Source:** {result.get('source', 'OWNER REQUEST')}",
            f"**Status:** PENDING BATCH REVIEW",
            request_text.strip()[:1200],
            "",
            f"**GitHub batch:** #{result['issue_number']}",
            f"**Issue:** {result['issue_url']}",
            f"**Submitted by owner:** <@{bot.command_user_id(interaction)}>",
            "**Next action:** Add remaining requests or use `/upgrade-ready`.",
            "This confirms intake only. It is not implementation, deployment, or verification proof.",
        ]
    )
    response = tracker._request(
        "POST",
        f"/channels/{channel_id}/messages",
        {"content": content[:1900], "allowed_mentions": {"parse": []}},
    )
    if not isinstance(response, dict) or not response.get("id"):
        raise RuntimeError("Discord did not acknowledge the mirrored upgrade request.")
    return channel_id


def _delete_original_response(application_id: str, token: str) -> None:
    url = f"https://discord.com/api/v10/webhooks/{application_id}/{token}/messages/@original"
    response = bot.requests.delete(url, timeout=20)
    if response.status_code not in {204, 404}:
        response.raise_for_status()


def _run_command(interaction: dict[str, Any]) -> dict[str, Any]:
    bot.require_ticker_admin(interaction)
    name = str(interaction.get("data", {}).get("name") or "")
    user_id = bot.command_user_id(interaction)

    if name == "upgrade-add":
        request_text = str(bot.option_value(interaction, "request", ""))
        result = bridge.add_request(
            request_text,
            discord_user_id=user_id,
            source="OWNER REQUEST",
        )
        return {
            "content": "\n".join(
                [
                    f"✅ **Upgrade request {result['request_number']} recorded**",
                    f"Batch issue: **#{result['issue_number']}**",
                    f"Source: **{result['source']}**",
                    f"GitHub: {result['issue_url']}",
                    "Status: **PENDING BATCH REVIEW**",
                    "Next action: add remaining requests or use `/upgrade-ready`.",
                    "The confirmation is being moved to #upgrade-requests.",
                ]
            ),
            "move_request": True,
            "request_text": request_text,
            "result": result,
        }
    if name == "upgrade-list":
        return {"content": _status_reply()}
    if name == "upgrade-ready":
        result = bridge.ready_batch(
            str(bot.option_value(interaction, "summary", "")),
            discord_user_id=user_id,
        )
        return {
            "content": "\n".join(
                [
                    f"✅ **Upgrade batch #{result['issue_number']} marked UPGRADE READY**",
                    f"Requests: **{result['request_count']}**",
                    f"GitHub: {result['issue_url']}",
                    "Next action: maintainer review, implementation, CI, and merge.",
                    "READY does not mean implemented, deployed, or verified.",
                ]
            )
        }
    if name == "upgrade-cancel":
        result = bridge.cancel_batch(
            str(bot.option_value(interaction, "reason", "")),
            discord_user_id=user_id,
        )
        return {
            "content": "\n".join(
                [
                    f"🗑️ **Upgrade batch #{result['issue_number']} cancelled**",
                    f"GitHub: {result['issue_url']}",
                    "The audit history remains in GitHub and no code was changed.",
                ]
            )
        }
    raise ValueError(f"Unsupported upgrade command: {name}")


def install() -> None:
    """Wrap the base command processor before the public Discord wrapper loads."""
    global _INSTALLED
    if _INSTALLED:
        return

    original_process_command = bot.process_command
    original_help_reply = bot.help_reply

    def process_command(interaction: dict[str, Any]) -> None:
        name = str(interaction.get("data", {}).get("name") or "")
        if name not in COMMANDS:
            original_process_command(interaction)
            return

        application_id = str(interaction.get("application_id") or "")
        token = str(interaction.get("token") or "")
        try:
            outcome = _run_command(interaction)
            content = str(outcome["content"])
        except Exception as exc:
            content = "⚠️ Upgrade command failed safely.\n" f"```{_safe_error(exc)}```"
            outcome = {"content": content}
        try:
            bot.patch_original(application_id, token, content=content)
            if outcome.get("move_request"):
                destination_id = _mirror_upgrade_request(
                    interaction,
                    outcome["result"],
                    str(outcome["request_text"]),
                )
                if str(interaction.get("channel_id") or "") != destination_id:
                    _delete_original_response(application_id, token)
        except (bot.requests.RequestException, bot.spy_scanner.DiscordError):
            pass

    def help_reply() -> str:
        base = original_help_reply()
        extra = "\n".join(
            [
                "",
                "**Owner-only shared upgrade batching**",
                "`/upgrade-add request:` — add an OWNER REQUEST to the shared GitHub batch",
                "`/upgrade-list` — show request sources, states, summaries, and next actions",
                "`/upgrade-ready summary:` — mark owner and diagnostic requests ready for maintainer review",
                "`/upgrade-cancel reason:` — close the current batch while preserving audit history",
            ]
        )
        return f"{base}{extra}"[:3900]

    bot.OWNER_ONLY_COMMANDS.update(COMMANDS)
    bot.process_command = process_command
    bot.help_reply = help_reply
    _INSTALLED = True
