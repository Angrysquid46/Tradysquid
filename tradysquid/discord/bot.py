from __future__ import annotations
from typing import Any
try:
    import discord
    from discord import app_commands
except ImportError:
    discord=None; app_commands=None
from .commands import CommandDispatcher
from .structure import DiscordStructureService
REQUIRED_COMMANDS=['status','diagnostics','version','restart','update-status','universe','universe-refresh','universe-pin','universe-unpin','universe-add','universe-remove','universe-exclude','universe-include','scan','scan-all','scan-status','candidate','rejections','shadow-results','paper-open','paper-close','paper-position','open-positions','closed-positions','strategies','strategy-show','strategy-enable','strategy-disable','strategy-preset','strategy-setting','strategy-version','strategy-rollback','strategy-recommendations','strategy-approve','strategy-reject','daily-report','weekly-report','monthly-report','ticker-report','strategy-report','learning-results','learn','learning-search','why']
class DiscordBotService:
    def __init__(self,services:dict[str,Any],owner_id:int,guild_id:int|None,schema:dict):
        self.dispatcher=CommandDispatcher(services,owner_id); self.guild_id=guild_id; self.schema=schema; self.ready=False; self.client=None
    async def start(self,token:str):
        if discord is None: raise RuntimeError('discord.py is not installed')
        intents=discord.Intents.none(); intents.guilds=True
        self.client=discord.Client(intents=intents); tree=app_commands.CommandTree(self.client)
        for command_name in REQUIRED_COMMANDS:
            async def callback(interaction:discord.Interaction,value:str='',_name=command_name):
                try: result=self.dispatcher.execute(_name,interaction.user.id,value)
                except Exception as exc: result=f'{type(exc).__name__}: {exc}'
                await interaction.response.send_message(result[:1900],ephemeral=True)
            tree.add_command(app_commands.Command(name=command_name,description=f'Tradysquid {command_name}',callback=callback))
        @self.client.event
        async def on_ready():
            guild=self.client.get_guild(self.guild_id) if self.guild_id else None
            if guild: await DiscordStructureService(self.schema).sync(guild); await tree.sync(guild=discord.Object(id=self.guild_id))
            else: await tree.sync()
            self.ready=True
        await self.client.start(token)
    async def close(self):
        if self.client and not self.client.is_closed(): await self.client.close()
