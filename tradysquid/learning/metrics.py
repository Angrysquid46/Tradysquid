from __future__ import annotations
from collections import defaultdict

def sample_label(n:int)->str:
    return 'INSUFFICIENT SAMPLE' if n<10 else 'EARLY SAMPLE' if n<30 else 'DESCRIPTIVE COMPARISON AVAILABLE'

def calculate(outcomes:list[dict])->dict:
    n=len(outcomes); pnls=[float(x.get('pnl_dollars',0)) for x in outcomes]
    wins=[x for x in pnls if x>0]; losses=[x for x in pnls if x<0]
    win_rate=len(wins)/n if n else 0
    avg_win=sum(wins)/len(wins) if wins else 0; avg_loss=sum(losses)/len(losses) if losses else 0
    expectancy=win_rate*avg_win+(1-win_rate)*avg_loss if n else 0
    gross_profit=sum(wins); gross_loss=abs(sum(losses)); profit_factor=(gross_profit/gross_loss if gross_loss else (float('inf') if gross_profit else 0))
    equity=0; peak=0; max_dd=0
    for pnl in pnls:
        equity+=pnl; peak=max(peak,equity); max_dd=min(max_dd,equity-peak)
    return {'sample_size':n,'sample_label':sample_label(n),'wins':len(wins),'losses':len(losses),'breakeven':n-len(wins)-len(losses),'win_rate':win_rate,'average_winner':avg_win,'average_loser':avg_loss,'expectancy':expectancy,'profit_factor':profit_factor,'net_pnl':sum(pnls),'maximum_drawdown':max_dd}
