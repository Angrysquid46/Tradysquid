from tradysquid.data.database import Database
def test_database_initialization_and_backup(tmp_path):
    db=Database(tmp_path/'x.db'); db.initialize(); assert db.integrity_check()=='ok'; assert db.journal_mode()=='wal'; result=db.backup(tmp_path/'backup.db'); assert (tmp_path/'backup.db').exists(); assert len(result['sha256'])==64
def test_transaction_rolls_back(tmp_path):
    db=Database(tmp_path/'x.db'); db.initialize()
    try:
        with db.transaction() as c:
            c.execute("INSERT INTO settings VALUES ('a','{}','now')"); raise RuntimeError('boom')
    except RuntimeError: pass
    assert db.query('SELECT * FROM settings')==[]
