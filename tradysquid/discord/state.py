from __future__ import annotations
import json
from ..core.models import utc_now

class DiscordStateRepository:
    def __init__(self, database):
        self.db = database
    def get(self, stable_id: str):
        rows = self.db.query('SELECT * FROM discord_message_state WHERE stable_id=?', (stable_id,))
        if not rows:
            return None
        row = rows[0]
        return {'stable_id': row['stable_id'], 'channel_id': row['channel_name'], 'message_id': row['message_id'], 'version': row['version'], 'signature': row['signature'], 'acknowledged': bool(row['acknowledged'])}
    def put(self, stable_id: str, value: dict):
        self.db.execute(
            'INSERT OR REPLACE INTO discord_message_state(stable_id,channel_name,message_id,version,signature,acknowledged,updated_at) VALUES (?,?,?,?,?,?,?)',
            (stable_id, value['channel_id'], value['message_id'], value['version'], value['signature'], int(value['acknowledged']), utc_now()),
        )
