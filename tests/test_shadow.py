from tradysquid.data.database import Database
from tradysquid.scanner.shadow_tracking import ShadowTrackingService
def test_shadow_metrics_stay_separate(tmp_path):
    db=Database(tmp_path/'x.db'); db.initialize()
    db.execute("INSERT INTO scan_cycles VALUES ('s','manual','test','COMPLETED','now','now','[]','{}','[]')")
    db.execute("INSERT INTO candidates VALUES ('c','s','regular-call','1','h','balanced','X','call','long-option','BULLISH_CONTROLLED','REJECTED',1,1,0,0,50,'{}','now')")
    db.execute("INSERT INTO shadow_candidates(candidate_id,source_status,opened_at) VALUES ('c','REJECTED','now')")
    service=ShadowTrackingService(db); service.mark('c',110,100); result=service.mark('c',90,100); assert result['mfe_pct']==.1 and result['mae_pct']==-.1
    assert db.query('SELECT COUNT(*) n FROM paper_positions')[0]['n']==0
