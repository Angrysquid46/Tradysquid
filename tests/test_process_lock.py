import json,os
import pytest
from tradysquid.core.process_lock import ProcessLock,ProcessLockError
def test_duplicate_lock_rejected(tmp_path):
    path=tmp_path/'pid'; path.write_text(json.dumps({'pid':os.getpid()}))
    with pytest.raises(ProcessLockError): ProcessLock(path).acquire()
def test_stale_lock_replaced(tmp_path,monkeypatch):
    path=tmp_path/'pid'; path.write_text(json.dumps({'pid':99999999})); lock=ProcessLock(path); lock.acquire(); assert path.exists(); lock.release()
