"""GROK strategy evolution — promote parameter changes only with evidence.

Anti-overfit posture: require chronological validation, minimum trade counts,
and stability before promoting a new version into the live path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bots.grok.state import StrategyVersion, load_state, save_state


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def propose_version(
    description: str,
    parameters: dict[str, Any],
    parent_version: str | None = None,
) -> StrategyVersion:
    state = load_state()
    version_id = f"v0.{len(state.strategy_versions) + 1}.0"
    ver = StrategyVersion(
        version_id=version_id,
        created_at=_now_iso(),
        description=description,
        parameters=parameters,
        parent_version=parent_version or state.strategy_version,
        promoted=False,
        validation_notes="pending walk-forward",
    )
    state.strategy_versions.append({
        "version_id": ver.version_id,
        "created_at": ver.created_at,
        "description": ver.description,
        "parameters": ver.parameters,
        "parent_version": ver.parent_version,
        "promoted": False,
        "validation_notes": ver.validation_notes,
    })
    save_state(state)
    return ver


def promote_version(version_id: str, validation_notes: str) -> bool:
    """Promote only after explicit validation evidence is attached."""
    state = load_state()
    for v in state.strategy_versions:
        if v["version_id"] == version_id:
            if "pending" in (v.get("validation_notes") or ""):
                return False  # refuse blind promotion
            v["promoted"] = True
            v["validation_notes"] = validation_notes
            state.strategy_version = version_id
            save_state(state)
            return True
    return False
