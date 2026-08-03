from __future__ import annotations
from ..core.models import utc_now
class ShadowTrackingService:
    def __init__(self,database): self.db=database
    def mark(self,candidate_id:str,current_value:float,entry_value:float):
        if entry_value<=0: raise ValueError('entry_value must be positive')
        move=(current_value-entry_value)/entry_value
        self.db.execute('INSERT INTO shadow_marks(candidate_id,observed_at,value,favorable_pct,adverse_pct) VALUES (?,?,?,?,?)',(candidate_id,utc_now(),current_value,max(move,0),min(move,0)))
        rows=self.db.query('SELECT MAX(favorable_pct) mfe, MIN(adverse_pct) mae FROM shadow_marks WHERE candidate_id=?',(candidate_id,))
        return {'candidate_id':candidate_id,'mfe_pct':rows[0]['mfe'] or 0,'mae_pct':rows[0]['mae'] or 0}
