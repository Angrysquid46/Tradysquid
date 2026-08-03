from __future__ import annotations
from dataclasses import dataclass
from ..core.models import OptionContract

class FillError(ValueError): pass

@dataclass(frozen=True)
class Fill:
    price: float
    model: dict

def _valid(contract: OptionContract) -> None:
    if contract.multiplier <= 0: raise FillError('contract multiplier is unavailable or invalid')
    if contract.bid < 0 or contract.ask <= 0 or contract.ask < contract.bid: raise FillError('option market is crossed or invalid')

def long_entry(contract: OptionContract, slippage: float=0.01) -> Fill:
    _valid(contract); price=round(contract.ask+max(slippage,0),4)
    return Fill(price, {'side':'buy','basis':'ask','ask':contract.ask,'slippage':slippage})
def long_exit(contract: OptionContract, slippage: float=0.01) -> Fill:
    _valid(contract); price=round(max(contract.bid-max(slippage,0),0),4)
    return Fill(price, {'side':'sell','basis':'bid','bid':contract.bid,'slippage':slippage})
def short_entry(contract: OptionContract, slippage: float=0.01) -> Fill:
    _valid(contract); price=round(max(contract.bid-max(slippage,0),0),4)
    return Fill(price, {'side':'sell','basis':'bid','bid':contract.bid,'slippage':slippage})
def short_exit(contract: OptionContract, slippage: float=0.01) -> Fill:
    _valid(contract); price=round(contract.ask+max(slippage,0),4)
    return Fill(price, {'side':'buy-to-close','basis':'ask','ask':contract.ask,'slippage':slippage})
