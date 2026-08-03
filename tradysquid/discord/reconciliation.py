from __future__ import annotations
from .contracts import signature, validate_payload

class MessageReconciler:
    """Non-destructive stable-message reconciliation."""
    def __init__(self,api,state_repository): self.api=api; self.state=state_repository
    def reconcile(self,stable_id:str,channel_id:str,payload:dict,version:str):
        validate_payload(payload); sig=signature(payload); current=self.state.get(stable_id)
        if current and current.get('signature')==sig and current.get('acknowledged'): return current
        if current and current.get('message_id'):
            try: result=self.api.update_message(channel_id,current['message_id'],payload)
            except Exception:
                # Preserve the last valid message and local state.
                raise
        else:
            result=self.api.create_message(channel_id,payload)
        if not result or not result.get('id'): raise RuntimeError('Discord did not acknowledge the message')
        verified=self.api.get_message(channel_id,result['id'])
        if not verified or str(verified.get('id'))!=str(result['id']): raise RuntimeError('Discord message verification failed')
        state={'stable_id':stable_id,'channel_id':channel_id,'message_id':str(result['id']),'version':version,'signature':sig,'acknowledged':True}
        self.state.put(stable_id,state)
        return state
