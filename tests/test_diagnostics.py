from tradysquid.data.database import Database
from tradysquid.operations.diagnostics import DiagnosticService

def test_repeated_failure_uses_one_fingerprint(tmp_path):
    db=Database(tmp_path/'d.db'); db.initialize(); service=DiagnosticService(db)
    a=service.observe('NETWORK','Tradier','Connect timeout',healthy=False); b=service.observe('NETWORK','Tradier',' Connect   timeout ',healthy=False)
    assert a['fingerprint']==b['fingerprint']; assert db.query('SELECT count FROM diagnostics')[0]['count']==2

def test_recovery_updates_existing_record(tmp_path):
    db=Database(tmp_path/'d.db'); db.initialize(); service=DiagnosticService(db); service.observe('DATABASE','sqlite','locked',healthy=False); service.observe('DATABASE','sqlite','locked',healthy=True)
    assert db.query('SELECT status FROM diagnostics')[0]['status']=='RECOVERED'
