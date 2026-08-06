from tradysquid.core.models import Quote
from tradysquid.universe.discovery import UniverseDiscovery
class P:
    def etb_securities(self): return [{'symbol':'B','type':'stock'},{'symbol':'A','type':'etf'}]
    def quotes(self,symbols,priority=6): return [Quote(s,1,1.1,10,100 if s=='A' else 50,'now') for s in symbols]
    def expirations(self,s): return ['2030-01-01'] if s=='A' else []
def test_discovery_is_optionability_checked_and_ranked():
    d=UniverseDiscovery(P()).discover(25); assert d[0].symbol=='A' and d[0].eligible; assert not d[1].eligible
