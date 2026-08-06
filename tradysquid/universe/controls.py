from __future__ import annotations
from ..core.models import utc_now

class UniverseControls:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def normalize(symbol: str) -> str:
        value = symbol.strip().upper()
        if not value or not value.replace('.', '').isalnum():
            raise ValueError('Ticker symbol contains unsupported characters')
        return value

    def add(self, symbol: str, *, pinned: bool = False) -> str:
        symbol = self.normalize(symbol)
        self.db.execute(
            'INSERT OR REPLACE INTO universe_candidates(symbol,source,pinned,excluded,updated_at) VALUES (?,?,?,?,?)',
            (symbol, 'owner', int(pinned), 0, utc_now()),
        )
        return symbol

    def remove(self, symbol: str) -> str:
        symbol = self.normalize(symbol)
        protected = self.db.query('SELECT 1 FROM universe_protections WHERE symbol=? AND active=1 LIMIT 1', (symbol,))
        open_position = self.db.query("SELECT 1 FROM paper_positions WHERE symbol=? AND state IN ('OPEN','HOLD','PROFIT_PROTECTED','EXIT_PENDING') LIMIT 1", (symbol,))
        if protected or open_position:
            raise ValueError(f'{symbol} is protected by an open obligation')
        self.db.execute('DELETE FROM universe_candidates WHERE symbol=?', (symbol,))
        self.db.execute('UPDATE universe_membership SET active=0,reason=?,updated_at=? WHERE symbol=?', ('owner removed', utc_now(), symbol))
        return symbol

    def pin(self, symbol: str, pinned: bool = True) -> str:
        symbol = self.add(symbol, pinned=pinned)
        self.db.execute('UPDATE universe_candidates SET pinned=?,updated_at=? WHERE symbol=?', (int(pinned), utc_now(), symbol))
        return symbol

    def exclude(self, symbol: str, excluded: bool = True) -> str:
        symbol = self.add(symbol)
        self.db.execute('UPDATE universe_candidates SET excluded=?,updated_at=? WHERE symbol=?', (int(excluded), utc_now(), symbol))
        if excluded:
            self.db.execute('UPDATE universe_membership SET active=0,reason=?,updated_at=? WHERE symbol=?', ('owner excluded', utc_now(), symbol))
        return symbol

    def configured(self) -> list[dict]:
        return self.db.query('SELECT * FROM universe_candidates ORDER BY pinned DESC,symbol')
