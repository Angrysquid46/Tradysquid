"""Run TradeBot with public educational commands.

Sensitive scanner controls remain owner-only. `/ask` and `/explain` answer
from discord_command_bot.py's own built-in canned library - the old
Learning Center system this file used to route through was retired.
"""

from __future__ import annotations

import discord_command_bot as bot

ORIGINAL_PROCESS_COMMAND = bot.process_command


def card_patch_original(
    application_id: str,
    token: str,
    *,
    content: str,
    file_path=None,
) -> None:
    """Allow full Discord embed-length answers instead of 2,000-char truncation."""
    url = (
        f"https://discord.com/api/v10/webhooks/{application_id}/{token}"
        "/messages/@original"
    )
    payload = {
        "content": str(content or "")[:3900],
        "allowed_mentions": {"parse": []},
    }
    if file_path and file_path.exists():
        payload["attachments"] = [{"id": 0, "filename": file_path.name}]
        with file_path.open("rb") as handle:
            response = bot.requests.patch(
                url,
                data={"payload_json": bot.json.dumps(payload)},
                files={"files[0]": (file_path.name, handle, "image/png")},
                timeout=30,
            )
    else:
        response = bot.requests.patch(url, json=payload, timeout=20)
    response.raise_for_status()


def public_process_command(interaction: dict) -> None:
    """Preserve all commands while giving `/ask` full interaction context."""
    name = str(interaction.get("data", {}).get("name") or "")
    if name != "ask":
        ORIGINAL_PROCESS_COMMAND(interaction)
        return

    application_id = str(interaction.get("application_id") or "")
    token = str(interaction.get("token") or "")
    try:
        question = str(bot.option_value(interaction, "question", ""))
        bot.patch_original(
            application_id,
            token,
            content=bot.ask_reply(question),
        )
    except Exception as exc:
        safe_error = f"{type(exc).__name__}: {exc}"[:1200]
        try:
            bot.patch_original(
                application_id,
                token,
                content=f"⚠️ Command failed safely.\n```{safe_error}```",
            )
        except bot.requests.RequestException:
            pass


bot.patch_original = card_patch_original
bot.process_command = public_process_command


if __name__ == "__main__":
    if not bot.PUBLIC_KEY:
        raise SystemExit("DISCORD_PUBLIC_KEY is required")
    try:
        instance_lock = bot.acquire_instance_lock()
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc
    with instance_lock:
        bot.APP.run(host=bot.HOST, port=bot.PORT, debug=False, threaded=True)
