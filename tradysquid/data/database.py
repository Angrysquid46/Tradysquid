from __future__ import annotations
import contextlib, hashlib, json, shutil, sqlite3
from pathlib import Path
from typing import Iterator, Any
from ..core.models import utc_now
from .schema import DDL, SCHEMA_VERSION

class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys=ON')
        conn.execute('PRAGMA busy_timeout=10000')
        return conn

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(DDL)
            conn.execute('INSERT OR IGNORE INTO schema_versions(version, applied_at) VALUES (?,?)', (SCHEMA_VERSION, utc_now()))

    @contextlib.contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn
            conn.execute('COMMIT')
        except Exception:
            conn.execute('ROLLBACK')
            raise
        finally:
            conn.close()

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> None:
        with self.connect() as conn:
            conn.execute(sql, params)

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as conn:
            return [dict(row) for row in conn.execute(sql, params).fetchall()]

    def integrity_check(self) -> str:
        with self.connect() as conn:
            return str(conn.execute('PRAGMA integrity_check').fetchone()[0])

    def journal_mode(self) -> str:
        with self.connect() as conn:
            return str(conn.execute('PRAGMA journal_mode').fetchone()[0]).lower()

    def backup(self, destination: Path) -> dict[str, str]:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as src, sqlite3.connect(destination) as dst:
            src.backup(dst)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        return {'path': str(destination), 'sha256': digest}

    def register_strategies(self, strategies: dict[str, dict[str, Any]]) -> None:
        with self.transaction() as conn:
            for sid, config in strategies.items():
                h = config['configuration_hash']
                conn.execute('INSERT OR REPLACE INTO strategy_profiles(strategy_id,display_name,enabled,active_version,active_hash) VALUES (?,?,?,?,?)',
                             (sid, config['display_name'], int(config['enabled']), config['version'], h))
                version_id = f'{sid}:{config["version"]}:{h[:12]}'
                conn.execute('INSERT OR IGNORE INTO strategy_versions(id,strategy_id,version,hash,preset,config_json,owner_approved,active,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
                             (version_id,sid,config['version'],h,config['preset'],json.dumps(config,sort_keys=True),1,1,utc_now()))
                for component in ('scanner','position-manager','reporting'):
                    conn.execute('INSERT OR REPLACE INTO strategy_acknowledgements(strategy_id,version,hash,component,acknowledged_at) VALUES (?,?,?,?,?)',
                                 (sid,config['version'],h,component,utc_now()))

    def active_strategy_configs(self, defaults: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        output = json.loads(json.dumps(defaults))
        rows = self.query('SELECT strategy_id,config_json FROM strategy_versions WHERE active=1 ORDER BY created_at')
        for row in rows:
            output[row['strategy_id']] = json.loads(row['config_json'])
        return output
