from __future__ import annotations

import json
import shlex
from typing import Any

MUTATING = {
    "restart",
    "universe-refresh",
    "universe-pin",
    "universe-unpin",
    "universe-add",
    "universe-remove",
    "universe-exclude",
    "universe-include",
    "scan",
    "scan-all",
    "paper-open",
    "paper-close",
    "strategy-enable",
    "strategy-disable",
    "strategy-preset",
    "strategy-setting",
    "strategy-rollback",
    "strategy-approve",
    "strategy-reject",
}


class CommandDispatcher:
    def __init__(self, services: dict[str, Any], owner_id: int):
        self.services = services
        self.owner_id = int(owner_id)

    def _owner(self, user_id: int):
        if int(user_id) != self.owner_id:
            raise PermissionError("This command is owner-only")

    @staticmethod
    def _parts(value: str) -> list[str]:
        return shlex.split(value or "")

    def execute(self, name: str, user_id: int, value: str = "") -> str:
        if name in MUTATING:
            self._owner(user_id)
        parts = self._parts(value)
        if name in {"status", "diagnostics", "version", "update-status"}:
            return json.dumps(
                self.services["health"](), sort_keys=True, default=str
            )
        if name == "restart":
            return self.services["restart"]()
        if name == "universe":
            return json.dumps(
                {
                    "active": self.services["universe"](),
                    "configured": self.services["universe_configured"](),
                },
                sort_keys=True,
            )
        if name in {
            "universe-add",
            "universe-pin",
            "universe-unpin",
            "universe-remove",
            "universe-exclude",
            "universe-include",
        }:
            if not parts:
                raise ValueError("A ticker symbol is required")
            result = self.services["universe_change"](name, parts[0])
            return json.dumps(result, sort_keys=True)
        if name == "universe-refresh":
            return json.dumps(
                {"active": self.services["universe_refresh"]()}, sort_keys=True
            )
        if name in {"scan", "scan-all"}:
            symbols = (
                [parts[0].upper()]
                if name == "scan" and parts
                else self.services["universe"]()
            )
            decisions = []
            for symbol in symbols:
                decisions.extend(self.services["scan"](symbol, "discord-owner"))
            return json.dumps(
                {"symbols": symbols, "decisions": len(decisions)}, sort_keys=True
            )
        if name == "scan-status":
            return json.dumps(self.services["scan_status"](), sort_keys=True)
        if name in {"candidate", "rejections"}:
            return json.dumps(
                self.services["candidate_view"](
                    name, parts[0] if parts else ""
                ),
                sort_keys=True,
                default=str,
            )
        if name in {
            "paper-open",
            "paper-close",
            "paper-position",
            "open-positions",
            "closed-positions",
        }:
            return json.dumps(
                self.services["paper"](name, parts),
                sort_keys=True,
                default=str,
            )
        if name in {"strategies", "strategy-show", "strategy-version"}:
            return json.dumps(
                self.services["strategies"](parts[0] if parts else ""),
                sort_keys=True,
                default=str,
            )
        if name in {
            "strategy-enable",
            "strategy-disable",
            "strategy-preset",
            "strategy-setting",
            "strategy-rollback",
        }:
            return json.dumps(
                self.services["strategy_change"](name, parts),
                sort_keys=True,
                default=str,
            )
        if name in {
            "strategy-recommendations",
            "strategy-approve",
            "strategy-reject",
        }:
            return json.dumps(
                self.services["recommendations"](name, parts),
                sort_keys=True,
                default=str,
            )
        if name in {
            "daily-report",
            "weekly-report",
            "monthly-report",
            "strategy-report",
            "ticker-report",
            "learning-results",
        }:
            return json.dumps(
                self.services["report"](name, parts[0] if parts else ""),
                sort_keys=True,
                default=str,
            )
        if name in {"learn", "learning-search", "why"}:
            return json.dumps(self.services["learn"](value), sort_keys=True)
        raise ValueError(f"Unsupported command: {name}")
