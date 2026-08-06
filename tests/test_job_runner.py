import pytest
from tradysquid.data.database import Database
from tradysquid.operations.jobs import JobRunner

def test_job_receipt_success(tmp_path):
    db=Database(tmp_path/'j.db'); db.initialize(); assert JobRunner(db).wrap('x',lambda:{'ok':True})()=={'ok':True}; assert db.query('SELECT status FROM scheduler_runs')[0]['status']=='PASSED'
def test_job_receipt_failure(tmp_path):
    db=Database(tmp_path/'j.db'); db.initialize()
    def fail(): raise RuntimeError('nope')
    with pytest.raises(RuntimeError): JobRunner(db).wrap('x',fail)()
    assert db.query('SELECT status FROM scheduler_runs')[0]['status']=='FAILED'
