import pytest
from tradysquid.discord.commands import CommandDispatcher
SERVICES={'health':lambda:{'ok':True},'universe':lambda:['X'],'universe_configured':lambda:[],'strategies':lambda x:[],'report':lambda n,v:{},'learn':lambda v:[]}
def test_owner_permission():
    d=CommandDispatcher(SERVICES,1)
    with pytest.raises(PermissionError): d.execute('scan',2,'X')
def test_read_only_status(): assert 'true' in CommandDispatcher(SERVICES,1).execute('status',2).lower()
