from __future__ import annotations
import os
from datetime import date
from typing import Any
import requests
from ..core.models import OptionContract, Quote, utc_now
from .request_manager import RequestManager

class TradierError(RuntimeError): pass

class TradierClient:
    """Read-only Tradier market-data client. No order methods exist."""
    def __init__(self, manager: RequestManager, token: str | None = None, environment: str | None = None, session: requests.Session | None = None):
        self.manager = manager
        self.token = token or os.environ.get('TRADIER_ACCESS_TOKEN','')
        env = environment or os.environ.get('TRADIER_ENVIRONMENT','paper')
        self.base_url = 'https://sandbox.tradier.com/v1' if env.lower() in {'paper','sandbox'} else 'https://api.tradier.com/v1'
        self.session = session or requests.Session()
        self.session.headers.update({'Authorization': f'Bearer {self.token}', 'Accept':'application/json', 'User-Agent':'Tradysquid/0.1'})

    def _get(self, path: str, params: dict[str, Any], *, priority: int, ttl: int, fresh: bool=False) -> Any:
        if not self.token: raise TradierError('TRADIER_ACCESS_TOKEN is missing')
        key = path + '?' + '&'.join(f'{k}={params[k]}' for k in sorted(params))
        def call():
            try:
                response = self.session.get(self.base_url + path, params=params, timeout=(5,20))
            except requests.RequestException as exc:
                raise TradierError(f'Tradier network failure: {type(exc).__name__}') from exc
            if response.status_code == 401: raise TradierError('Tradier authentication failed')
            if response.status_code == 429: raise TradierError('Tradier rate limit reached')
            if response.status_code >= 400: raise TradierError(f'Tradier returned HTTP {response.status_code}')
            try: payload = response.json()
            except ValueError as exc: raise TradierError('Tradier returned invalid JSON') from exc
            return payload, dict(response.headers)
        return self.manager.request(key, priority, ttl, call, fresh_required=fresh)


    def etb_securities(self) -> list[dict[str, Any]]:
        payload = self._get('/markets/etb', {}, priority=6, ttl=86400)
        raw = ((payload.get('securities') or {}).get('security') or [])
        if isinstance(raw, dict): raw = [raw]
        return [x for x in raw if str(x.get('type','')).lower() in {'stock','etf'} and x.get('symbol')]

    def market_clock(self) -> dict[str, Any]:
        return self._get('/markets/clock', {}, priority=2, ttl=30)

    def quotes(self, symbols: list[str], *, priority: int=3, fresh: bool=False) -> list[Quote]:
        payload = self._get('/markets/quotes', {'symbols':','.join(symbols),'greeks':'false'}, priority=priority, ttl=15, fresh=fresh)
        raw = ((payload.get('quotes') or {}).get('quote') or [])
        if isinstance(raw, dict): raw = [raw]
        now = utc_now()
        return [Quote(str(x.get('symbol','')).upper(), float(x.get('bid') or 0), float(x.get('ask') or 0), float(x.get('last') or 0), int(x.get('volume') or 0), now) for x in raw]

    def history(self, symbol: str, start: str, end: str, interval: str='daily') -> list[dict[str, Any]]:
        payload = self._get('/markets/history', {'symbol':symbol,'interval':interval,'start':start,'end':end}, priority=4, ttl=300)
        raw = ((payload.get('history') or {}).get('day') or [])
        if isinstance(raw, dict): raw=[raw]
        return list(raw)

    def expirations(self, symbol: str) -> list[str]:
        payload = self._get('/markets/options/expirations', {'symbol':symbol,'includeAllRoots':'true','strikes':'false'}, priority=3, ttl=900)
        dates = ((payload.get('expirations') or {}).get('date') or [])
        return [str(x) for x in ([dates] if isinstance(dates,str) else dates)]

    def option_chain(self, symbol: str, expiration: str) -> list[OptionContract]:
        payload = self._get('/markets/options/chains', {'symbol':symbol,'expiration':expiration,'greeks':'true'}, priority=3, ttl=30)
        raw = ((payload.get('options') or {}).get('option') or [])
        if isinstance(raw, dict): raw=[raw]
        now=utc_now(); out=[]
        for x in raw:
            greeks=x.get('greeks') or {}
            out.append(OptionContract(
                symbol=str(x.get('symbol','')), underlying=symbol.upper(), expiration=str(x.get('expiration_date',expiration)),
                strike=float(x.get('strike') or 0), option_type=str(x.get('option_type','')).lower(),
                bid=float(x.get('bid') or 0), ask=float(x.get('ask') or 0), volume=int(x.get('volume') or 0),
                open_interest=int(x.get('open_interest') or 0), delta=float(greeks['delta']) if greeks.get('delta') is not None else None,
                gamma=float(greeks['gamma']) if greeks.get('gamma') is not None else None,
                theta=float(greeks['theta']) if greeks.get('theta') is not None else None,
                vega=float(greeks['vega']) if greeks.get('vega') is not None else None,
                implied_volatility=float(greeks['mid_iv']) if greeks.get('mid_iv') is not None else None,
                multiplier=int(x.get('contract_size') or 100), observed_at=now))
        return out
