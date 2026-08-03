from __future__ import annotations
import json
from typing import Any
MUTATING_PREFIXES=('restart','universe-refresh','universe-pin','universe-unpin','universe-add','universe-remove','universe-exclude','universe-include','scan','scan-all','paper-open','paper-close','strategy-enable','strategy-disable','strategy-preset','strategy-setting','strategy-rollback','strategy-approve','strategy-reject')
class CommandDispatcher:
    def __init__(self,services:dict[str,Any],owner_id:int): self.services=services; self.owner_id=int(owner_id)
    def _owner(self,user_id:int):
        if int(user_id)!=self.owner_id: raise PermissionError('This command is owner-only')
    def execute(self,name:str,user_id:int,value:str='')->str:
        if name in MUTATING_PREFIXES: self._owner(user_id)
        if name in {'status','diagnostics','version','update-status'}: return json.dumps(self.services['health'](),sort_keys=True)
        if name=='universe': return ', '.join(self.services['universe']()) or 'Universe is empty.'
        if name in {'scan','scan-all'}:
            symbols=[value.upper()] if name=='scan' and value else self.services['universe']()
            total=sum(len(self.services['scan'](s)) for s in symbols); return f'Scan completed: {total} strategy decisions.'
        if name in {'strategies','strategy-show','strategy-version'}: return json.dumps(self.services['strategies'](value),sort_keys=True)
        if name in {'daily-report','weekly-report','monthly-report','strategy-report','ticker-report','learning-results'}: return json.dumps(self.services['report'](name,value),sort_keys=True,default=str)
        if name in {'learn','learning-search','why'}: return json.dumps(self.services['learn'](value),sort_keys=True)
        return self.services.get('command_fallback',lambda n,v:f'{n} accepted for owner review.')(name,value)
