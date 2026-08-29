from __future__ import annotations
import json,sqlite3,uuid
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import backtest_lab,scoreboard
from .engine import MULTIPLIER,Decision,Position,Surge

BOT="SURGE";STATE_DIR=Path(__file__).resolve().parents[2]/"state"/"surge";TELEMETRY=STATE_DIR/"live-decisions.jsonl";POSITION_STATE=STATE_DIR/"position-state.json"
class SurgeRuntime:
    def __init__(self,engine=None,market_view=None,telemetry_path=None):self.engine=engine or Surge();self.market_view=market_view or backtest_lab.MarketView("SPY");self.telemetry_path=telemetry_path or TELEMETRY
    def recover(self,c):
        self.engine.generation=scoreboard.current_generation(c,BOT);row=scoreboard.current_position_status(c,BOT)
        if row is None:self.engine.position=None;POSITION_STATE.unlink(missing_ok=True);return
        if self.engine.position and self.engine.position.trade_id==str(row["trade_id"]):return
        peak=float(row["entry_price"])
        try:
            saved=json.loads(POSITION_STATE.read_text(encoding="utf-8"))
            if saved.get("trade_id")==str(row["trade_id"]):peak=max(peak,float(saved["peak_bid"]))
        except (OSError,ValueError,TypeError,KeyError):pass
        self.engine.position=Position(str(row["trade_id"]),str(row["contract_symbol"]),str(row["side"]).lower(),int(row["contracts"]),float(row["entry_price"]),datetime.fromisoformat(str(row["opened_at"])),peak)
    def evaluate(self,as_of:datetime,c:sqlite3.Connection)->Decision:
        self.recover(c);bankroll=scoreboard.current_bankroll(c,BOT);market=self.market_view.market_as_of(as_of);options=self.market_view.options_as_of(as_of);bars=self.market_view.bars_as_of(as_of,lookback_minutes=60)
        d=self.engine.decide(as_of,bankroll,market,options,bars);self.telemetry_path.parent.mkdir(parents=True,exist_ok=True)
        with self.telemetry_path.open("a",encoding="utf-8") as f:f.write(json.dumps({**asdict(d),"observed_at":as_of.isoformat(),"bankroll":bankroll},sort_keys=True)+"\n")
        if self.engine.position:
            POSITION_STATE.write_text(json.dumps({"trade_id":self.engine.position.trade_id,"peak_bid":self.engine.position.peak_bid}),encoding="utf-8")
        if d.action=="ENTER":
            trade_id=f"surge-{uuid.uuid4()}";scoreboard.record_trade_open(c,trade_id=trade_id,bot=BOT,generation=self.engine.generation,opened_at=as_of.isoformat(),side=str(d.side),contract_symbol=str(d.contract_symbol),entry_price=float(d.price),contracts=d.contracts,entry_bankroll=bankroll)
            selected=next(x for x in options["contracts"] if x.get("option_symbol")==d.contract_symbol);self.engine.apply_entry(d,trade_id,as_of,float(selected["bid"]));POSITION_STATE.write_text(json.dumps({"trade_id":trade_id,"peak_bid":float(selected["bid"])}),encoding="utf-8")
        elif d.action=="EXIT":
            p=self.engine.position
            if not p or d.price is None:raise RuntimeError("SURGE emitted invalid exit")
            pnl=(d.price-p.entry)*p.contracts*MULTIPLIER;scoreboard.record_trade_close(c,trade_id=p.trade_id,closed_at=as_of.isoformat(),exit_price=d.price,pnl_usd=pnl);self.engine.apply_exit();POSITION_STATE.unlink(missing_ok=True)
        return d
