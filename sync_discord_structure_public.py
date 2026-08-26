"""Apply Discord structure, public ticker policy, and cards."""

from __future__ import annotations

import sys

import discord_transport
import sync_discord_structure as sync

# Retired 2026-08-25 - owner: "the system catagory and all channels I want
# removed forever." This module used to unconditionally re-insert
# system-activity/automation-diagnostics ChannelSpecs into "SYSTEM" (a
# category that no longer exists in sync.CATEGORY_ORDER) and to overwrite
# sync.GUIDES["how-to-use-tradebot"]/["how-trades-are-found"] with older
# text that both referenced those now-deleted channels and silently
# discarded whatever sync_discord_structure.py's own GUIDES said - the
# exact same "stale override re-posted live" bug class the
# "scanner-controls" retirement above already caught once. Removed rather
# than repointed: SYSTEM and everything in it is gone, not relocated.
sync.CHANNEL_STARTERS.update(
    {
        "news-and-events": (
            "News and event sweeps continue during market hours, evenings, overnight periods, and weekends."
        ),
    }
)


def _tracker() -> discord_transport.DiscordTracker:
    tracker = discord_transport.DiscordTracker(
        discord_transport.DISCORD_BOT_TOKEN, discord_transport.DISCORD_GUILD_ID
    )
    if not tracker.enabled:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_GUILD_ID are required.")
    return tracker


def main() -> int:
    apply = "--apply" in sys.argv
    result = sync.main()
    if result:
        return result
    if not apply:
        print("Dry run: structure synchronized above; no live changes made.")
    else:
        print("Discord release complete: structure synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
