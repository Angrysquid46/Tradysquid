from __future__ import annotations
import json, time, uuid
from ..core.models import utc_now

class JobRunner:
    def __init__(self, database):
        self.db = database

    def wrap(self, job_id: str, function):
        def run():
            run_id = str(uuid.uuid4())
            started = utc_now(); before = time.monotonic()
            self.db.execute(
                'INSERT INTO scheduler_runs(id,job_id,status,started_at,details_json) VALUES (?,?,?,?,?)',
                (run_id, job_id, 'RUNNING', started, '{}'),
            )
            try:
                result = function()
                details = {'duration_seconds': round(time.monotonic() - before, 3), 'result': result}
                self.db.execute(
                    'UPDATE scheduler_runs SET status=?,completed_at=?,details_json=? WHERE id=?',
                    ('PASSED', utc_now(), json.dumps(details, default=str), run_id),
                )
                return result
            except Exception as exc:
                details = {'duration_seconds': round(time.monotonic() - before, 3), 'error': f'{type(exc).__name__}: {exc}'}
                self.db.execute(
                    'UPDATE scheduler_runs SET status=?,completed_at=?,details_json=? WHERE id=?',
                    ('FAILED', utc_now(), json.dumps(details), run_id),
                )
                raise
        return run
