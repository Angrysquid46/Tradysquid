import argparse,signal,socket,threading
from datetime import date,datetime
from zoneinfo import ZoneInfo
from .preflight import INSTANCE_PORT,require_ready
from .scheduler import build_scheduler
CENTRAL=ZoneInfo("America/Chicago")
def current_session_date():return datetime.now(CENTRAL).date()
def acquire_instance_lock(port=INSTANCE_PORT):s=socket.socket();s.bind(("127.0.0.1",port));s.listen(1);return s
def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument("--session",type=date.fromisoformat);p.add_argument("--require-clean-start",action="store_true");a=p.parse_args(argv);require_ready(a.session or current_session_date(),a.require_clean_start);lock=acquire_instance_lock();scheduler=build_scheduler();stop=threading.Event();signal.signal(signal.SIGINT,lambda *_:stop.set());signal.signal(signal.SIGTERM,lambda *_:stop.set())
    try:scheduler.start();stop.wait()
    finally:scheduler.shutdown(wait=True);lock.close()
    return 0
if __name__=="__main__":raise SystemExit(main())
