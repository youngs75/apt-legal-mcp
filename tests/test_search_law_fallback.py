"""Tests for search_law local-filter fallback when combined query yields 0 hits."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from kor_legal_mcp.cache.memory_cache import MemoryCache
from kor_legal_mcp.clients.law_api import Article, LawApiClient, LawSearchHit
from kor_legal_mcp.tools._common import ToolContext
from kor_legal_mcp.tools.search_law import handle


def _hit(name: str, mst: str = "100") -> LawSearchHit:
    return LawSearchHit(law_name=name, mst=mst, enforcement_date=None, last_amended=None)


def _article(num: str, title: str, text: str) -> Article:
    return Article(law_name="공동주택관리법", article_number=num, article_title=title, full_text=text)


ARTICLES = [
    _article("제23조", "관리비", "관리주체는 관리비를 부과한다."),
    _article("제30조", "장기수선충당금의 적립", "관리주체는 장기수선충당금을 해당 주택의 소유자로부터 징수하여 적립하여야 한다."),
    _article("제35조", "하자보수", "사업주체는 하자보수를 이행하여야 한다."),
]


@pytest.fixture
def ctx():
    """ToolContext with mocked LawApiClient."""
    api = AsyncMock(spec=LawApiClient)
    cache = MemoryCache(max_items=100, default_ttl_seconds=60)
    return ToolContext(law_api=api, cache=cache)


@pytest.mark.asyncio
async def test_fallback_finds_articles_by_law_name(ctx):
    """When combined query returns 0 hits but law_name-only returns hits,
    local-filter should rank articles by relevance to query."""
    # Combined "공동주택관리법 장기수선충당금" → 0 hits
    # Keyword retry is skipped (same query after truncation to 3 keywords)
    # law_name-only "공동주택관리법" → 1 hit
    ctx.law_api.search_laws = AsyncMock(
        side_effect=[
            [],  # 1st call: effective_query (combined)
            [_hit("공동주택관리법", "200")],  # 2nd call: law_name fallback
        ]
    )
    ctx.law_api.get_law_detail = AsyncMock(return_value=ARTICLES)

    result = await handle(ctx, {
        "query": "장기수선충당금",
        "law_name": "공동주택관리법",
    })

    assert len(result.results) > 0
    # Top result should be article 30 (contains "장기수선충당금")
    assert result.results[0].article_number == "제30조"
    assert "장기수선충당금" in result.results[0].snippet


@pytest.mark.asyncio
async def test_no_fallback_when_combined_succeeds(ctx):
    """When combined query returns hits, no fallback needed."""
    ctx.law_api.search_laws = AsyncMock(
        return_value=[_hit("공동주택관리법", "200")]
    )
    ctx.law_api.get_law_detail = AsyncMock(return_value=ARTICLES)

    result = await handle(ctx, {
        "query": "장기수선충당금",
        "law_name": "공동주택관리법",
    })

    assert len(result.results) == 1
    # Normal path: single best article
    assert result.results[0].law_name == "공동주택관리법"
    # search_laws called only once
    assert ctx.law_api.search_laws.call_count == 1


@pytest.mark.asyncio
async def test_fallback_filters_zero_relevance(ctx):
    """Local-filter skips articles with 0 relevance score."""
    ctx.law_api.search_laws = AsyncMock(
        side_effect=[
            [],  # combined
            [_hit("공동주택관리법", "200")],  # fallback (keyword retry skipped)
        ]
    )
    # Articles that don't contain "주차" at all
    ctx.law_api.get_law_detail = AsyncMock(return_value=ARTICLES)

    result = await handle(ctx, {
        "query": "주차",
        "law_name": "공동주택관리법",
    })

    # None of ARTICLES mention "주차", so all filtered out
    assert len(result.results) == 0
    assert result.message is not None  # "검색 결과가 없습니다" message
