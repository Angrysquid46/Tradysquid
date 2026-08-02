"""Apply the public Discord structure with distinct Performance report channels."""

from __future__ import annotations

import performance_channel_structure
import sync_discord_structure as sync
import upgrade_batch_44

performance_channel_structure.install(sync)
performance_channel_structure.validate(sync)

import sync_discord_structure_public as public  # noqa: E402

upgrade_batch_44.install_structure(sync)


if __name__ == "__main__":
    raise SystemExit(public.main())
