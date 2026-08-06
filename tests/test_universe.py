from tradysquid.data.database import Database
from tradysquid.universe.service import UniverseService,UniverseDecision
def test_universe_cap_and_protection(tmp_path):
    db=Database(tmp_path/'u.db'); db.initialize(); u=UniverseService(db,25)
    decisions=[UniverseDecision(f'T{i}',100-i,True,{},[]) for i in range(40)]
    active=u.rotate(decisions,protected={'T39'},pinned={'T38'}); assert len(active)==25; assert 'T39' in active and 'T38' in active
def test_rotation_is_deterministic(tmp_path):
    db=Database(tmp_path/'u.db'); db.initialize(); u=UniverseService(db,25); d=[UniverseDecision('B',1,True,{},[]),UniverseDecision('A',1,True,{},[])]
    assert u.rotate(d)==['A','B']; assert u.rotate(d)==['A','B']
