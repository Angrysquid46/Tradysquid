from __future__ import annotations
try:
    from apscheduler.schedulers.background import BackgroundScheduler
except ImportError:
    BackgroundScheduler=None

class SchedulerService:
    def __init__(self,timezone='America/Chicago'):
        if BackgroundScheduler is None: raise RuntimeError('APScheduler is not installed')
        self.scheduler=BackgroundScheduler(timezone=timezone,job_defaults={'coalesce':True,'max_instances':1,'misfire_grace_time':120})
    @property
    def running(self): return self.scheduler.running
    def register(self,jobs:dict):
        definitions=[('provider-budget-refresh','interval',{'seconds':30}),('market-session-refresh','interval',{'minutes':1}),('universe-evaluation','interval',{'minutes':15}),('universe-rotation','interval',{'minutes':30}),('active-universe-quotes','interval',{'minutes':1}),('full-strategy-scan','interval',{'minutes':5}),('open-position-monitoring','interval',{'minutes':1}),('shadow-candidate-monitoring','interval',{'minutes':5}),('market-intelligence-refresh','interval',{'minutes':5}),('daily-reporting','cron',{'hour':15,'minute':20}),('weekly-reporting','cron',{'day_of_week':'fri','hour':15,'minute':30}),('monthly-reporting','cron',{'day':'last','hour':15,'minute':40}),('learning-results','cron',{'hour':16,'minute':0}),('learning-center-reconciliation','interval',{'hours':6}),('strategy-control-reconciliation','interval',{'minutes':5}),('diagnostics','interval',{'minutes':5}),('database-backup','cron',{'hour':2,'minute':0}),('retention-cleanup','cron',{'hour':2,'minute':30})]
        for job_id,kind,params in definitions:
            func=jobs.get(job_id,lambda:None); self.scheduler.add_job(func,kind,id=job_id,replace_existing=True,**params)
    def start(self): self.scheduler.start()
    def shutdown(self): self.scheduler.shutdown(wait=False)
