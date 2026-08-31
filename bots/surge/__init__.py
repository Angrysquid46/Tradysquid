"""SURGE: reactive three-minute SPY 0DTE impulse paper competitor."""
from .env_bootstrap import bootstrap
bootstrap()
from .engine import Decision,Surge
from .runtime import SurgeRuntime
__all__=["Decision","Surge","SurgeRuntime"]
