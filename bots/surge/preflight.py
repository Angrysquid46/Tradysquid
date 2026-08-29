from __future__ import annotations
import json,socket,subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path
import market_api_budget,market_data,scoreboard
ROOT=Path(__file__).resolve().parents[2];INSTANCE_PORT=8894
@dataclass(frozen=True)
class Check:name:str;passed:bool;detail:str
def port_free(port=INSTANCE_PORT):
    s=socket.socket()
    try:s.bind(("127.0.0.1",port));return True
    except OSError:return False
    finally:s.close()
def run(session_date:date,require_clean_start=True):
    try:state=json.loads((ROOT/"state"/"supervisor-state.json").read_text())
    except Exception:state={}
    p=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True);head=p.stdout.strip();deployed=str(state.get("deployed_sha") or "")
    checks=[Check("deployed-main",bool(deployed and head.startswith(deployed) and state.get("last_update_status") in {"DEPLOYED","UP_TO_DATE"}),f"head={head[:12]} deployed={deployed[:12]}"),Check("single-instance",port_free(),"SURGE port 8894 free")]
    c=scoreboard.connect_db()
    try:g=scoreboard.current_generation(c,"SURGE");b=scoreboard.current_bankroll(c,"SURGE");t=scoreboard.trade_count(c,"SURGE");flat=scoreboard.current_position_status(c,"SURGE") is None
    finally:c.close()
    checks.append(Check("official-state",(g==1 and abs(b-1000)<.01 and t==0 and flat) if require_clean_start else g>=1,f"generation={g} bankroll={b:.2f} trades={t} flat={flat}"))
    try:
        checks.append(Check("tradier-quote",bool(market_data.get_quote("SPY",priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT)),"live SPY quote available"));ex=market_data.get_expirations("SPY",priority=market_api_budget.PRIORITY_SECONDARY_CONTEXT);checks.append(Check("target-expiration",session_date.isoformat() in ex,f"target listed={session_date.isoformat() in ex}"))
    except Exception as e:checks.extend([Check("tradier-quote",False,str(e)),Check("target-expiration",False,"provider failed")])
    return checks
def require_ready(session_date,require_clean_start=True):
    checks=run(session_date,require_clean_start);failed=[x for x in checks if not x.passed]
    if failed:raise RuntimeError("; ".join(f"{x.name}: {x.detail}" for x in failed))
    return checks
