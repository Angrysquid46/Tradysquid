from __future__ import annotations
import hashlib, json
from ..core.models import utc_now

class DiagnosticService:
    def __init__(self, database):
        self.db = database

    @staticmethod
    def fingerprint(category: str, component: str, message: str) -> str:
        normalized = ' '.join(message.lower().split())
        return hashlib.sha256(f'{category}|{component}|{normalized}'.encode()).hexdigest()[:24]

    def observe(self, category: str, component: str, message: str, *, healthy: bool) -> dict:
        fp = self.fingerprint(category, component, message)
        now = utc_now()
        existing = self.db.query('SELECT * FROM diagnostics WHERE fingerprint=?', (fp,))
        status = 'RECOVERED' if healthy and existing else 'HEALTHY' if healthy else 'OPEN'
        if existing:
            self.db.execute(
                'UPDATE diagnostics SET status=?,message=?,last_seen=?,count=count+1 WHERE fingerprint=?',
                (status, message, now, fp),
            )
        else:
            self.db.execute(
                'INSERT INTO diagnostics(fingerprint,category,status,message,first_seen,last_seen,count) VALUES (?,?,?,?,?,?,1)',
                (fp, category, status, message, now, now),
            )
        return {'fingerprint': fp, 'category': category, 'component': component, 'status': status, 'message': message}

    def current(self) -> list[dict]:
        return self.db.query("SELECT * FROM diagnostics WHERE status='OPEN' ORDER BY last_seen DESC")
