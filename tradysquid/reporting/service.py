from __future__ import annotations
from ..learning.metrics import calculate

class ReportingService:
    def __init__(self,database): self.db=database
    def overall(self): return calculate(self.db.query('SELECT * FROM closed_outcomes ORDER BY closed_at'))
    def by_strategy(self):
        rows=self.db.query('SELECT o.*,p.strategy_id,p.strategy_version FROM closed_outcomes o JOIN paper_positions p ON p.id=o.position_id ORDER BY o.closed_at')
        groups={}
        for row in rows: groups.setdefault((row['strategy_id'],row['strategy_version']),[]).append(row)
        return {f'{k[0]}@{k[1]}':calculate(v) for k,v in groups.items()}
    def by_ticker(self):
        rows=self.db.query('SELECT o.*,p.symbol FROM closed_outcomes o JOIN paper_positions p ON p.id=o.position_id ORDER BY o.closed_at')
        groups={}
        for row in rows: groups.setdefault(row['symbol'],[]).append(row)
        return {k:calculate(v) for k,v in groups.items()}
    def rejected_analysis(self):
        return self.db.query('SELECT reason,COUNT(*) count FROM candidate_rejections GROUP BY reason ORDER BY count DESC,reason')
    def shadow_analysis(self):
        return self.db.query('SELECT outcome,COUNT(*) count,AVG(mfe_pct) avg_mfe,AVG(mae_pct) avg_mae FROM shadow_outcomes GROUP BY outcome')
    def reconcile(self):
        overall=self.overall(); wins=self.db.query("SELECT COUNT(*) n FROM closed_outcomes WHERE pnl_dollars>0")[0]['n']; losses=self.db.query("SELECT COUNT(*) n FROM closed_outcomes WHERE pnl_dollars<0")[0]['n']
        return {'closed':overall['sample_size'],'wins':wins,'losses':losses,'net_pnl':overall['net_pnl'],'reconciled':wins==overall['wins'] and losses==overall['losses']}
