from __future__ import annotations

import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from typing import Any


class MemoryCache:
    def __init__(self, max_items: int = 1000, default_ttl_seconds: float = 86400.0):
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._max_items = max_items
        self._default_ttl = default_ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Any | None:
        async with self._lock:
            item = self._store.get(key)
            if item is None:
                return None
            expires_at, value = item
            if expires_at < time.monotonic():
                self._store.pop(key, None)
                return None
            self._store.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        async with self._lock:
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl
            expires_at = time.monotonic() + ttl
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = (expires_at, value)
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)

    async def clear(self) -> None:
        async with self._lock:
            self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


def make_key(namespace: str, **params: Any) -> str:
    payload = json.dumps(params, sort_keys=True, ensure_ascii=False, default=str)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{namespace}:{digest}"
