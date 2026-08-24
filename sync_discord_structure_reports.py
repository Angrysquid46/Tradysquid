"""Apply the public Discord structure with reports and upgrade verification."""

from __future__ import annotations

import applied_upgrades
import sync_discord_structure as sync
import upgrade_batch_44

# performance_channel_structure.install()/validate() removed - Phase 3 purge
# (old strategy performance-channel structure, deleted with the roster).

import sync_discord_structure_public as public  # noqa: E402

upgrade_batch_44.install_structure(sync)
applied_upgrades.install_structure(sync)


if __name__ == "__main__":
    raise SystemExit(public.main())
