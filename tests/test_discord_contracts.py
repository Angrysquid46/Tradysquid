import pytest
from tradysquid.discord.contracts import validate_payload,split_text
from tradysquid.discord.reconciliation import MessageReconciler
def test_size_validation_and_split():
    with pytest.raises(ValueError): validate_payload({'content':'x'*2001})
    assert all(len(x)<=100 for x in split_text('x'*250,100))
class API:
    def __init__(self,fail=False): self.fail=fail; self.messages={}
    def create_message(self,c,p):
        if self.fail: raise RuntimeError('down')
        self.messages['1']={'id':'1',**p}; return {'id':'1'}
    def update_message(self,c,i,p):
        if self.fail: raise RuntimeError('down')
        self.messages[i]={'id':i,**p}; return {'id':i}
    def get_message(self,c,i): return self.messages.get(i)
class State:
    def __init__(self): self.data={}
    def get(self,k): return self.data.get(k)
    def put(self,k,v): self.data[k]=v
def test_non_destructive_reconciliation():
    s=State(); a=API(); r=MessageReconciler(a,s); first=r.reconcile('x','c',{'content':'one'},'1'); a.fail=True
    with pytest.raises(RuntimeError): r.reconcile('x','c',{'content':'two'},'2')
    assert s.get('x')==first
