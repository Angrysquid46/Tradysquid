from __future__ import annotations
from dataclasses import dataclass
from ..core.enums import Regime
from .technicals import rsi, sma, slope, support_resistance

@dataclass(frozen=True)
class RegimeResult:
    regime: Regime
    confidence: float
    supporting: list[str]
    opposing: list[str]
    missing: list[str]
    metrics: dict[str,float|None]

def classify_regime(bars: list[dict]) -> RegimeResult:
    closes=[float(b['close']) for b in bars if b.get('close') is not None]
    if len(closes)<50:
        return RegimeResult(Regime.DATA_INSUFFICIENT,0,[],[],['At least 50 daily closes are required'],{})
    fast=sma(closes,20); slow=sma(closes,50); strength=rsi(closes,14); recent=slope(closes,5); support,resistance=support_resistance(closes)
    metrics={'close':closes[-1],'sma20':fast,'sma50':slow,'rsi14':strength,'slope5':recent,'support':support,'resistance':resistance}
    supporting=[]; opposing=[]
    bullish = closes[-1] > fast > slow and (strength or 0)>=52 and (recent or 0)>0
    bearish = closes[-1] < fast < slow and (strength if strength is not None else 100)<=48 and (recent or 0)<0
    if bullish:
        supporting += ['price above SMA20 and SMA50','SMA20 above SMA50','RSI supports bullish control','recent slope positive']
        return RegimeResult(Regime.BULLISH_CONTROLLED, min(100,60+(strength-50)),supporting,opposing,[],metrics)
    if bearish:
        supporting += ['price below SMA20 and SMA50','SMA20 below SMA50','RSI supports bearish control','recent slope negative']
        return RegimeResult(Regime.BEARISH_CONTROLLED, min(100,60+(50-strength)),supporting,opposing,[],metrics)
    width=(resistance-support)/max(closes[-1],1e-9) if support is not None else 0
    if width < .12 and 40 <= (strength or 50) <= 60:
        return RegimeResult(Regime.NEUTRAL_RANGE,55,['trend evidence is mixed','RSI is neutral'],[],[],metrics)
    return RegimeResult(Regime.NO_TRADE,45,[],['trend, momentum, and range evidence do not form a controlled regime'],[],metrics)
