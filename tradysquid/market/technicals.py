from __future__ import annotations
from typing import Iterable

def sma(values: list[float], period: int) -> float | None:
    return None if period <= 0 or len(values) < period else sum(values[-period:]) / period

def rsi(values: list[float], period: int=14) -> float | None:
    if len(values) <= period: return None
    gains=[]; losses=[]
    for a,b in zip(values[-period-1:-1], values[-period:]):
        change=b-a; gains.append(max(change,0)); losses.append(max(-change,0))
    avg_gain=sum(gains)/period; avg_loss=sum(losses)/period
    if avg_loss == 0: return 100.0
    rs=avg_gain/avg_loss
    return 100 - 100/(1+rs)

def slope(values: list[float], bars: int=5) -> float | None:
    if len(values) < bars or bars < 2: return None
    window=values[-bars:]
    return (window[-1]-window[0]) / max(abs(window[0]), 1e-9)

def support_resistance(values: list[float], bars: int=20) -> tuple[float|None,float|None]:
    if not values: return None,None
    window=values[-bars:]
    return min(window), max(window)
