import asyncio

import pytest

from kor_legal_mcp.cache.memory_cache import MemoryCache, make_key


@pytest.mark.asyncio
async def test_set_get():
    cache = MemoryCache(max_items=10, default_ttl_seconds=60)
    await cache.set("k", "v")
    assert await cache.get("k") == "v"


@pytest.mark.asyncio
async def test_ttl_expiry():
    cache = MemoryCache(max_items=10, default_ttl_seconds=60)
    await cache.set("k", "v", ttl_seconds=0.05)
    await asyncio.sleep(0.1)
    assert await cache.get("k") is None


@pytest.mark.asyncio
async def test_lru_eviction():
    cache = MemoryCache(max_items=2, default_ttl_seconds=60)
    await cache.set("a", 1)
    await cache.set("b", 2)
    await cache.set("c", 3)
    assert await cache.get("a") is None
    assert await cache.get("b") == 2
    assert await cache.get("c") == 3


def test_make_key_stable():
    k1 = make_key("ns", a=1, b="x")
    k2 = make_key("ns", b="x", a=1)
    assert k1 == k2
    assert k1.startswith("ns:")
