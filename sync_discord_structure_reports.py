"""Apply the public Discord structure with reports and upgrade verification."""

from __future__ import annotations

# performance_channel_structure.install()/validate() removed - Phase 3 purge
# (old strategy performance-channel structure, deleted with the roster).
# upgrade_batch_44.install_structure()/applied_upgrades.install_structure()
# removed - the upgrade-requests/applied-upgrades Discord channels they
# added were retired along with the rest of the old upgrade-batch system.

import sync_discord_structure_public as public  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(public.main())
