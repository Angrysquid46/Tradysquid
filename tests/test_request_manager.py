import pytest
from tradysquid.providers.request_manager import RequestManager
def test_cache_and_rate_headers():
    m=RequestManager(); calls=[]
    def call(): calls.append(1); return {'x':1},{'X-Ratelimit-Allowed':'10','X-Ratelimit-Available':'8'}
    assert m.request('x',3,60,call)=={'x':1}; assert m.request('x',3,60,call)=={'x':1}; assert len(calls)==1 and m.allowed==10
def test_reserve_blocks_low_priority():
    m=RequestManager(); m.available=2
    with pytest.raises(RuntimeError): m.request('x',3,0,lambda:({},{}))
