from __future__ import annotations
import copy, json, re
from dataclasses import dataclass
from typing import Any
from ..core.config import stable_hash, validate_strategy_config
from ..core.models import utc_now

_PATH_PART = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

@dataclass(frozen=True)
class VersionChange:
    strategy_id: str
    previous_version: str
    new_version: str
    configuration_hash: str
    reason: str


def _next_patch(version: str) -> str:
    parts = version.split('.')
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError('Strategy version must use MAJOR.MINOR.PATCH')
    return f'{parts[0]}.{parts[1]}.{int(parts[2]) + 1}'


def _set_path(config: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split('.')
    if not parts or any(not _PATH_PART.match(part) for part in parts):
        raise ValueError('Invalid strategy setting path')
    target: dict[str, Any] = config
    for part in parts[:-1]:
        existing = target.get(part)
        if not isinstance(existing, dict):
            raise ValueError(f'Unknown strategy setting group: {part}')
        target = existing
    if parts[-1] not in target:
        raise ValueError(f'Unknown strategy setting: {path}')
    target[parts[-1]] = value


class StrategyVersionService:
    """Owner-approved strategy changes persisted as immutable versions."""
    def __init__(self, database, registry):
        self.db = database
        self.registry = registry

    def active(self, strategy_id: str) -> dict[str, Any]:
        return copy.deepcopy(self.registry.get(strategy_id).config)

    def propose(self, strategy_id: str, path: str, value: Any, reason: str) -> dict[str, Any]:
        current = self.active(strategy_id)
        proposed = copy.deepcopy(current)
        proposed.pop('configuration_hash', None)
        _set_path(proposed, path, value)
        proposed['version'] = _next_patch(str(current['version']))
        proposed['change_explanation'] = reason.strip() or 'Owner-requested setting change'
        validate_strategy_config(proposed)
        proposed_hash = stable_hash(proposed)
        proposed['configuration_hash'] = proposed_hash
        return proposed

    def activate(self, strategy_id: str, proposed: dict[str, Any], reason: str) -> VersionChange:
        current = self.active(strategy_id)
        if proposed.get('strategy_id') != strategy_id:
            raise ValueError('Strategy ID cannot be changed')
        validate_strategy_config(proposed)
        proposed = copy.deepcopy(proposed)
        proposed_hash = stable_hash({k: v for k, v in proposed.items() if k != 'configuration_hash'})
        proposed['configuration_hash'] = proposed_hash
        now = utc_now()
        version_id = f"{strategy_id}:{proposed['version']}:{proposed_hash[:12]}"
        with self.db.transaction() as conn:
            conn.execute('UPDATE strategy_versions SET active=0,retired_at=? WHERE strategy_id=? AND active=1', (now, strategy_id))
            conn.execute(
                'INSERT INTO strategy_versions(id,strategy_id,version,hash,preset,config_json,owner_approved,active,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                (version_id, strategy_id, proposed['version'], proposed_hash, proposed['preset'], json.dumps(proposed, sort_keys=True), 1, 1, now),
            )
            conn.execute(
                'UPDATE strategy_profiles SET display_name=?,enabled=?,active_version=?,active_hash=? WHERE strategy_id=?',
                (proposed['display_name'], int(proposed['enabled']), proposed['version'], proposed_hash, strategy_id),
            )
            for component in ('scanner', 'position-manager', 'reporting'):
                conn.execute(
                    'INSERT OR REPLACE INTO strategy_acknowledgements(strategy_id,version,hash,component,acknowledged_at) VALUES (?,?,?,?,?)',
                    (strategy_id, proposed['version'], proposed_hash, component, now),
                )
        self.registry.replace(strategy_id, proposed)
        return VersionChange(strategy_id, current['version'], proposed['version'], proposed_hash, reason)

    def rollback(self, strategy_id: str, version: str) -> VersionChange:
        rows = self.db.query(
            'SELECT config_json FROM strategy_versions WHERE strategy_id=? AND version=? ORDER BY created_at DESC LIMIT 1',
            (strategy_id, version),
        )
        if not rows:
            raise ValueError(f'No stored version {version} for {strategy_id}')
        config = json.loads(rows[0]['config_json'])
        config['version'] = _next_patch(self.active(strategy_id)['version'])
        config['change_explanation'] = f'Rollback to settings from {version}'
        return self.activate(strategy_id, config, config['change_explanation'])

    def history(self, strategy_id: str) -> list[dict[str, Any]]:
        return self.db.query(
            'SELECT version,hash,preset,owner_approved,active,created_at,retired_at FROM strategy_versions WHERE strategy_id=? ORDER BY created_at DESC',
            (strategy_id,),
        )
