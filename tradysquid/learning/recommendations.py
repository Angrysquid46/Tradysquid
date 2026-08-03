from __future__ import annotations
import json, uuid
from ..core.models import utc_now

ALLOWED_STATUSES={'CREATED','NEEDS_MORE_DATA','READY_FOR_REVIEW','APPROVED','REJECTED','IMPLEMENTED','ROLLED_BACK','EXPIRED'}

class RecommendationService:
    def __init__(self,database): self.db=database
    def create(self,strategy_id,current_version,setting_path,current_value,proposed_value,evidence,status='CREATED'):
        if status not in ALLOWED_STATUSES: raise ValueError(status)
        rid=str(uuid.uuid4()); now=utc_now()
        self.db.execute('INSERT INTO learning_recommendations(id,strategy_id,current_version,status,setting_path,current_json,proposed_json,evidence_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',(rid,strategy_id,current_version,status,setting_path,json.dumps(current_value),json.dumps(proposed_value),json.dumps(evidence),now,now))
        return rid
    def decide(self,recommendation_id,approved:bool):
        status='APPROVED' if approved else 'REJECTED'
        self.db.execute('UPDATE learning_recommendations SET status=?,owner_decision=?,updated_at=? WHERE id=?',(status,status,utc_now(),recommendation_id))
        return status
