from __future__ import annotations
from typing import Any
from .base import Strategy

class StrategyRegistry:
    REQUIRED={'regular-call','regular-put','swing-call','swing-put','bull-put-spread','bear-call-spread'}
    def __init__(self, configs: dict[str,dict[str,Any]]):
        if set(configs)!=self.REQUIRED: raise ValueError('Strategy registry must contain exactly the six required strategies')
        self._strategies={sid:Strategy(config) for sid,config in configs.items()}
    def all(self): return list(self._strategies.values())
    def enabled(self): return [s for s in self.all() if s.config['enabled']]
    def get(self,strategy_id): return self._strategies[strategy_id]
    def replace(self,strategy_id,config):
        if strategy_id not in self.REQUIRED: raise ValueError(strategy_id)
        self._strategies[strategy_id]=Strategy(config)
        return self._strategies[strategy_id]
    def acknowledgements(self,component): return [s.acknowledgement(component) for s in self.enabled()]
