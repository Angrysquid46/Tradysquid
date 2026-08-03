from __future__ import annotations
import asyncio, os, signal
from pathlib import Path
from dotenv import load_dotenv
from .core.config import AppConfig
from .core.logging import configure_logging
from .core.process_lock import ProcessLock
from .data.database import Database
from .providers.request_manager import RequestManager
from .providers.tradier import TradierClient
from .strategies.registry import StrategyRegistry
from .universe.service import UniverseService
from .universe.discovery import UniverseDiscovery
from .scanner.service import ScanService
from .scanner.shadow_tracking import ShadowTrackingService
from .trading.paper_broker import PaperBroker
from .learning.center import LearningCenter
from .reporting.service import ReportingService
from .operations.scheduler import SchedulerService
from .operations.health import build_health
from .discord.bot import DiscordBotService
class Application:
    def __init__(self,root:Path):
        self.root=root; load_dotenv(root/'.env',override=True); self.config=AppConfig.load(root); configure_logging(root/'logs',self.config.defaults['logging']['level'])
        self.lock=ProcessLock(root/'state'/'tradysquid.pid.json'); self.db=Database(root/self.config.defaults['database']['path']); self.db.initialize(); self.db.register_strategies(self.config.strategies)
        self.manager=RequestManager(self.db); self.provider=TradierClient(self.manager); self.registry=StrategyRegistry(self.config.strategies); self.universe=UniverseService(self.db,25); self.discovery=UniverseDiscovery(self.provider)
        self.scanner=ScanService(self.db,self.provider,self.registry); self.shadow=ShadowTrackingService(self.db); self.paper=PaperBroker(self.db); self.reporting=ReportingService(self.db); self.learning=LearningCenter(self.config.learning_center)
        self.scheduler=SchedulerService(self.config.defaults['market_timezone']); self._stop=asyncio.Event(); self.discord=None; self.discord_task=None
        owner=os.environ.get('DISCORD_OWNER_USER_ID'); guild=os.environ.get('DISCORD_GUILD_ID')
        if owner:
            services={'health':self.health,'universe':self.universe.active,'scan':self.scanner.scan_symbol,'strategies':self.strategy_view,'report':self.report_view,'learn':self.learning.search}
            self.discord=DiscordBotService(services,int(owner),int(guild) if guild else None,self.config.discord_schema)
    def strategy_view(self,value=''):
        values=[{'strategy_id':s.id,'version':s.config['version'],'hash':s.config['configuration_hash'],'preset':s.config['preset'],'enabled':s.config['enabled']} for s in self.registry.all()]
        return next((x for x in values if x['strategy_id']==value),values) if value else values
    def report_view(self,name,value=''):
        if name=='strategy-report': return self.reporting.by_strategy()
        if name=='ticker-report': return self.reporting.by_ticker()
        return self.reporting.overall()
    def health(self): return build_health(self.db,self.registry,self.universe,self.scheduler,bool(self.discord and self.discord.ready))
    def initialize_universe(self):
        configured=self.config.defaults['universe']['candidate_pool']; self.universe.seed(configured)
        if configured:
            decisions=[]
            from .universe.service import UniverseDecision
            for s in configured: decisions.append(UniverseDecision(s.upper(),1.0,True,{'source':'configuration'},[]))
        else: decisions=self.discovery.discover(25)
        return self.universe.rotate(decisions)
    async def run(self):
        self.lock.acquire(); self.initialize_universe()
        jobs={'universe-rotation':self.initialize_universe,'full-strategy-scan':self.scan_all,'daily-reporting':self.reporting.overall,'weekly-reporting':self.reporting.overall,'monthly-reporting':self.reporting.overall,'learning-results':self.reporting.by_strategy,'database-backup':self.backup,'diagnostics':self.health}
        self.scheduler.register(jobs); self.scheduler.start()
        token=os.environ.get('DISCORD_BOT_TOKEN')
        if self.discord and token: self.discord_task=asyncio.create_task(self.discord.start(token))
        loop=asyncio.get_running_loop()
        for sig in (signal.SIGINT,signal.SIGTERM):
            try: loop.add_signal_handler(sig,self._stop.set)
            except NotImplementedError: pass
        try: await self._stop.wait()
        finally:
            self.scheduler.shutdown()
            if self.discord: await self.discord.close()
            if self.discord_task: self.discord_task.cancel()
            self.lock.release()
    def scan_all(self):
        for symbol in self.universe.active():
            try: self.scanner.scan_symbol(symbol,'scheduled')
            except Exception: continue
    def backup(self):
        from datetime import datetime
        self.db.backup(self.root/'backups'/f'tradysquid-{datetime.now():%Y%m%d-%H%M%S}.db')
def main(): asyncio.run(Application(Path(__file__).resolve().parents[1]).run())
if __name__=='__main__': main()
