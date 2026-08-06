import pytest
from tradysquid.data.database import Database
from tradysquid.universe.controls import UniverseControls

def test_add_pin_exclude_and_include(tmp_path):
    db=Database(tmp_path/'u.db'); db.initialize(); c=UniverseControls(db)
    assert c.add(' abc ')=='ABC'; c.pin('ABC'); assert c.configured()[0]['pinned']==1
    c.exclude('ABC'); assert c.configured()[0]['excluded']==1; c.exclude('ABC',False); assert c.configured()[0]['excluded']==0

def test_invalid_symbol_rejected(tmp_path):
    db=Database(tmp_path/'u.db'); db.initialize(); c=UniverseControls(db)
    with pytest.raises(ValueError): c.add('BAD SYMBOL')

def test_open_position_prevents_removal(tmp_path):
    db=Database(tmp_path/'u.db'); db.initialize(); c=UniverseControls(db); c.add('ABC')
    db.execute("INSERT INTO scan_cycles VALUES ('s','manual','test','COMPLETED','now','now','[]','{}','[]')")
    db.execute("INSERT INTO candidates VALUES ('c','s','regular-call','1','h','balanced','ABC','call','long-option','BULLISH_CONTROLLED','OPENED',1,1,50,0,50,'{}','now')")
    db.execute("INSERT INTO trade_cycles VALUES ('t','c','regular-call','now',NULL,'OPEN')")
    db.execute("INSERT INTO paper_positions VALUES ('p','t','c','regular-call','1','h','ABC','call','long-option','OPEN','now',NULL,50,50,50,0,0,0,0,'{}')")
    with pytest.raises(ValueError): c.remove('ABC')
