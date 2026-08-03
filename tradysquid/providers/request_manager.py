from __future__ import annotations
import hashlib, json, threading, time, uuid
from dataclasses import dataclass
from typing import Callable, Any
from ..core.models import utc_now

@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    observed_at: str

class RequestManager:
    def __init__(self, database=None):
        self.database = database
        self._lock = threading.RLock()
        self._cache: dict[str, CacheEntry] = {}
        self.allowed = 125
        self.used = 0
        self.available = 125
        self.expires_at = ''

    def update_limits(self, headers: dict[str, str]) -> None:
        with self._lock:
            def parse(*names, default):
                for n in names:
                    if n in headers:
                        try: return int(headers[n])
                        except ValueError: pass
                return default
            self.allowed = parse('X-Ratelimit-Allowed','X-RateLimit-Limit',default=self.allowed)
            self.used = parse('X-Ratelimit-Used','X-RateLimit-Used',default=self.used)
            self.available = parse('X-Ratelimit-Available','X-RateLimit-Remaining',default=max(self.allowed-self.used,0))
            self.expires_at = headers.get('X-Ratelimit-Expiry', headers.get('X-RateLimit-Reset',''))

    def request(self, key: str, priority: int, ttl_seconds: int, call: Callable[[], tuple[Any, dict[str,str]]], fresh_required: bool = False) -> Any:
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached and cached.expires_at > now and not fresh_required:
                return cached.value
            if self.available <= 2 and priority > 1:
                raise RuntimeError('Provider capacity reserved for open-position safety')
        value, headers = call()
        self.update_limits(headers)
        with self._lock:
            self.used += 1
            self.available = max(self.available - 1, 0)
            self._cache[key] = CacheEntry(value, now + max(ttl_seconds,0), utc_now())
        return value
