from __future__ import annotations
from ..version import __version__

def build_health(database,registry,universe,scheduler=None,discord_ready=False):
    return {'version':__version__,'database_integrity':database.integrity_check(),'journal_mode':database.journal_mode(),'strategy_count':len(registry.all()),'active_universe_count':len(universe.active()),'scheduler_running':bool(scheduler and scheduler.running),'discord_ready':bool(discord_ready)}
