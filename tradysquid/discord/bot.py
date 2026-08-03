from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import discord
    from discord import app_commands
except ImportError:  # pragma: no cover - production dependency check handles this
    discord = None
    app_commands = None

from .commands import CommandDispatcher
from .contracts import split_text
from .structure import DiscordStructureService


REQUIRED_COMMANDS = [
    "status",
    "diagnostics",
    "version",
    "restart",
    "update-status",
    "universe",
    "universe-refresh",
    "universe-pin",
    "universe-unpin",
    "universe-add",
    "universe-remove",
    "universe-exclude",
    "universe-include",
    "scan",
    "scan-all",
    "scan-status",
    "candidate",
    "rejections",
    "shadow-results",
    "paper-open",
    "paper-close",
    "paper-position",
    "open-positions",
    "closed-positions",
    "strategies",
    "strategy-show",
    "strategy-enable",
    "strategy-disable",
    "strategy-preset",
    "strategy-setting",
    "strategy-version",
    "strategy-rollback",
    "strategy-recommendations",
    "strategy-approve",
    "strategy-reject",
    "daily-report",
    "weekly-report",
    "monthly-report",
    "ticker-report",
    "strategy-report",
    "learning-results",
    "learn",
    "learning-search",
    "why",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def format_command_response(result: Any) -> list[str]:
    if isinstance(result, str):
        text = result
    else:
        text = json.dumps(result, indent=2, sort_keys=True, default=str)
    return split_text(text, 1900)


class DiscordBotService:
    def __init__(
        self,
        services: dict[str, Any],
        owner_id: int,
        guild_id: int | None,
        schema: dict[str, Any],
        *,
        root: Path,
        publishing=None,
    ) -> None:
        self.dispatcher = CommandDispatcher(services, owner_id)
        self.guild_id = guild_id
        self.schema = schema
        self.root = root
        self.publishing = publishing
        self.ready = False
        self.client = None
        self.tree = None

    def _readiness_path(self) -> Path:
        path = self.root / "state" / "discord-readiness.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _write_readiness(self, receipt: dict[str, Any]) -> None:
        self._readiness_path().write_text(
            json.dumps(receipt, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )

    async def start(self, token: str) -> None:
        if discord is None or app_commands is None:
            raise RuntimeError("discord.py is not installed")
        if not self.guild_id:
            raise RuntimeError("DISCORD_GUILD_ID is required")

        intents = discord.Intents.none()
        intents.guilds = True
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)

        for command_name in REQUIRED_COMMANDS:

            async def callback(
                interaction: discord.Interaction,
                value: str = "",
                _name: str = command_name,
            ) -> None:
                try:
                    result = self.dispatcher.execute(_name, interaction.user.id, value)
                except Exception as exc:  # command boundary returns a readable error
                    result = {"status": "FAILED", "error": f"{type(exc).__name__}: {exc}"}
                chunks = format_command_response(result)
                await interaction.response.send_message(chunks[0], ephemeral=True)
                for chunk in chunks[1:]:
                    await interaction.followup.send(chunk, ephemeral=True)

            self.tree.add_command(
                app_commands.Command(
                    name=command_name,
                    description=f"Tradysquid {command_name}"[:100],
                    callback=callback,
                )
            )

        @self.client.event
        async def on_ready() -> None:
            self.ready = False
            receipt: dict[str, Any] = {
                "status": "FAILED",
                "bot_user_id": str(self.client.user.id) if self.client.user else None,
                "guild_id": str(self.guild_id),
                "categories_resolved": 0,
                "channels_resolved": 0,
                "slash_commands_synchronized": 0,
                "publishing_bootstrap": None,
                "completed_at": None,
                "secret_values_written": False,
            }
            try:
                guild = self.client.get_guild(self.guild_id)
                if guild is None:
                    guild = await self.client.fetch_guild(self.guild_id)
                if guild is None:
                    raise RuntimeError("Configured Discord guild could not be resolved")

                database = getattr(self.publishing, "db", None)
                structure_receipts = await DiscordStructureService(
                    self.schema,
                    database=database,
                ).sync(guild)
                channel_map: dict[str, Any] = {}
                categories = list(getattr(guild, "categories", []))
                for category in categories:
                    for channel in getattr(category, "text_channels", []):
                        channel_map[channel.name.casefold()] = channel
                for channel in getattr(guild, "text_channels", []):
                    channel_map[channel.name.casefold()] = channel

                synchronized = await self.tree.sync(guild=discord.Object(id=self.guild_id))
                publishing_receipt = None
                if self.publishing is not None:
                    publishing_receipt = await self.publishing.bootstrap(guild, channel_map)

                receipt.update(
                    {
                        "status": "PASS",
                        "categories_resolved": len(categories),
                        "channels_resolved": len(channel_map),
                        "structure_receipts": len(structure_receipts),
                        "structure_details": structure_receipts,
                        "slash_commands_synchronized": len(synchronized),
                        "publishing_bootstrap": publishing_receipt,
                        "completed_at": _utc_now(),
                    }
                )
                self._write_readiness(receipt)
                self.ready = True
            except Exception as exc:
                receipt.update(
                    {
                        "status": "FAILED",
                        "error": f"{type(exc).__name__}: {exc}",
                        "completed_at": _utc_now(),
                    }
                )
                self._write_readiness(receipt)
                raise

        await self.client.start(token)

    async def close(self) -> None:
        if self.client and not self.client.is_closed():
            await self.client.close()
