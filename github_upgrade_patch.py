"""Install owner-only Discord commands for free GitHub upgrade batching."""

from __future__ import annotations

from typing import Any

import discord_command_bot as bot
import github_upgrade_bridge as bridge

COMMANDS = {"upgrade-add", "upgrade-list", "upgrade-ready", "upgrade-cancel"}
_INSTALLED = False


def _status_reply() -> str:
    status = bridge.batch_status()
    if status["state"] == "NONE":
        return (
            "📭 **No GitHub upgrade batch exists yet.**\n"
            "Use `/upgrade-add request:` to create one without any OpenAI API charge."
        )
    return "\n".join(
        [
            f"📦 **Upgrade batch #{status['issue_number']} · {status['state']}**",
            f"Requests recorded: **{status['request_count']}**",
            f"GitHub: {status['issue_url']}",
            (
                "Add more with `/upgrade-add`, or lock the batch with `/upgrade-ready`."
                if status["state"] == "OPEN"
                else "This batch is ready for implementation review."
            ),
        ]
    )


def _run_command(interaction: dict[str, Any]) -> str:
    bot.require_ticker_admin(interaction)
    name = str(interaction.get("data", {}).get("name") or "")
    user_id = bot.command_user_id(interaction)

    if name == "upgrade-add":
        result = bridge.add_request(
            str(bot.option_value(interaction, "request", "")),
            discord_user_id=user_id,
        )
        return "\n".join(
            [
                f"✅ **Upgrade request {result['request_number']} uploaded**",
                f"Batch issue: **#{result['issue_number']}**",
                f"GitHub: {result['issue_url']}",
                "No OpenAI API call was used and no code was changed.",
            ]
        )
    if name == "upgrade-list":
        return _status_reply()
    if name == "upgrade-ready":
        result = bridge.ready_batch(
            str(bot.option_value(interaction, "summary", "")),
            discord_user_id=user_id,
        )
        return "\n".join(
            [
                f"✅ **Upgrade batch #{result['issue_number']} marked READY**",
                f"Requests: **{result['request_count']}**",
                f"GitHub: {result['issue_url']}",
                "Tell ChatGPT to review the latest ready Tradysquid upgrade batch.",
                "Nothing was merged or deployed automatically.",
            ]
        )
    if name == "upgrade-cancel":
        result = bridge.cancel_batch(
            str(bot.option_value(interaction, "reason", "")),
            discord_user_id=user_id,
        )
        return "\n".join(
            [
                f"🗑️ **Upgrade batch #{result['issue_number']} cancelled**",
                f"GitHub: {result['issue_url']}",
                "The issue was closed and no code was changed.",
            ]
        )
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
            content = _run_command(interaction)
        except Exception as exc:
            content = f"⚠️ Upgrade command failed safely.\n```{type(exc).__name__}: {str(exc)[:1000]}```"
        try:
            bot.patch_original(application_id, token, content=content)
        except bot.requests.RequestException:
            pass

    def help_reply() -> str:
        base = original_help_reply()
        extra = "\n".join(
            [
                "",
                "**Owner-only free upgrade batching**",
                "`/upgrade-add request:` — upload one request to the open GitHub batch",
                "`/upgrade-list` — show the current batch and request count",
                "`/upgrade-ready summary:` — lock the batch for implementation review",
                "`/upgrade-cancel reason:` — close the current batch without changes",
            ]
        )
        return f"{base}{extra}"[:3900]

    bot.OWNER_ONLY_COMMANDS.update(COMMANDS)
    bot.process_command = process_command
    bot.help_reply = help_reply
    _INSTALLED = True
