"""Verify enforcement_date / last_amended propagation through search_law
and get_law_article. Required by downstream sufficiency-loop deterministic
guards in apt-legal-agent (Citation.effective_date round-trip).

search_law 와 get_law_article 가 enforcement_date / last_amended 를 손실 없이
전달하는지 검증. apt-legal-agent 의 sufficiency-loop 결정론 가드
(Citation.effective_date round-trip)에 필요.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from kor_legal_mcp.cache.memory_cache import MemoryCache
from kor_legal_mcp.clients.law_api import Article, LawApiClient, LawSearchHit
from kor_legal_mcp.tools._common import ToolContext
from kor_legal_mcp.tools.get_law_article import handle as get_article_handle
from kor_legal_mcp.tools.search_law import handle as search_law_handle


@pytest.fixture
def ctx():
    api = AsyncMock(spec=LawApiClient)
    cache = MemoryCache(max_items=100, default_ttl_seconds=60)
    return ToolContext(law_api=api, cache=cache)


@pytest.mark.asyncio
async def test_search_law_propagates_enforcement_date(ctx):
    # The fix turns LawSearchResultItem.enforcement_date from "always missing"
    # into "set when the law.go.kr search hit carried it" — the deterministic
    # citation guard depends on this field surviving the tool boundary.
    # 이 fix 는 LawSearchResultItem.enforcement_date 를 "항상 누락" 에서
    # "law.go.kr search hit 에 있으면 설정됨" 으로 바꾼다 — 결정론 citation 가드는
    # 이 필드가 도구 경계를 살아서 넘어오는 것에 의존한다.
    hit = LawSearchHit(
        law_name="공동주택관리법",
        mst="200",
        enforcement_date="2024-02-17",
        last_amended="2023-08-16",
    )
    ctx.law_api.search_laws = AsyncMock(return_value=[hit])
    ctx.law_api.get_law_detail = AsyncMock(
        return_value=[
            Article(
                law_name="공동주택관리법",
                article_number="제65조",
                article_title="입주자대표회의의 구성 등",
                full_text="입주자대표회의는 4명 이상으로 구성한다.",
            )
        ]
    )

    result = await search_law_handle(
        ctx, {"query": "입주자대표회의", "law_name": "공동주택관리법"}
    )

    assert len(result.results) == 1
    assert result.results[0].enforcement_date == "2024-02-17"
    assert result.results[0].last_amended == "2023-08-16"


@pytest.mark.asyncio
async def test_search_law_no_articles_path_carries_metadata(ctx):
    # Edge case: no articles returned for a hit — the fallback row that the
    # handler emits must still carry the law-level dates.
    # 엣지 케이스: hit 에 대해 조문이 없을 때 — handler 가 emit 하는 fallback
    # 행도 법령 단위 날짜를 운반해야 함.
    hit = LawSearchHit(
        law_name="공동주택관리법",
        mst="200",
        enforcement_date="2024-02-17",
        last_amended="2023-08-16",
    )
    ctx.law_api.search_laws = AsyncMock(return_value=[hit])
    ctx.law_api.get_law_detail = AsyncMock(return_value=[])

    result = await search_law_handle(
        ctx, {"query": "관리비", "law_name": "공동주택관리법"}
    )

    assert len(result.results) == 1
    assert result.results[0].article_number == "-"
    assert result.results[0].enforcement_date == "2024-02-17"
    assert result.results[0].last_amended == "2023-08-16"


@pytest.mark.asyncio
async def test_get_law_article_returns_enforcement_date(ctx):
    # The handler used to hard-code enforcement_date=None / last_amended=None
    # so even when LawApiClient knew the dates, they were lost at the tool
    # boundary. The fix wires the article fields through.
    # 이 handler 는 enforcement_date=None / last_amended=None 을 하드코딩해서
    # LawApiClient 가 날짜를 알고 있어도 도구 경계에서 잃었다. fix 는
    # article 필드를 그대로 전달한다.
    article = Article(
        law_name="공동주택관리법",
        article_number="제65조",
        article_title="입주자대표회의의 구성 등",
        full_text="입주자대표회의는 4명 이상으로 구성한다.",
        enforcement_date="2024-02-17",
        last_amended="2023-08-16",
    )
    ctx.law_api.get_article = AsyncMock(return_value=article)

    result = await get_article_handle(
        ctx, {"law_name": "공동주택관리법", "article_number": "제65조"}
    )

    assert result.enforcement_date == "2024-02-17"
    assert result.last_amended == "2023-08-16"


@pytest.mark.asyncio
async def test_get_law_article_metadata_is_optional(ctx):
    # If the search hit had no dates, the handler must still succeed and
    # return None for the optional fields — agents downstream treat None
    # as "skip the deterministic check for this anchor" rather than fail.
    # search hit 에 날짜가 없다면 handler 는 성공해야 하고 옵셔널 필드는 None
    # 을 반환. 다운스트림 에이전트는 None 을 "이 anchor 의 결정론 검증을 스킵"
    # 으로 처리하지 실패로 보지 않는다.
    article = Article(
        law_name="공동주택관리법",
        article_number="제65조",
        article_title="입주자대표회의의 구성 등",
        full_text="...",
    )
    ctx.law_api.get_article = AsyncMock(return_value=article)

    result = await get_article_handle(
        ctx, {"law_name": "공동주택관리법", "article_number": "제65조"}
    )

    assert result.enforcement_date is None
    assert result.last_amended is None
