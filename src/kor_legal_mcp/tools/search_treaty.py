from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    SearchTreatyInput,
    SearchTreatyOutput,
    TreatySearchResultItem,
)
from kor_legal_mcp.tools._common import ToolContext, normalize_query


async def handle(ctx: ToolContext, payload: dict) -> SearchTreatyOutput:
    params = SearchTreatyInput.model_validate(payload)
    query = normalize_query(params.query)

    cache_key = make_key(
        "tool.search_treaty", query=query, max_results=params.max_results
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchTreatyOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_treaties(
            query=query, max_results=params.max_results
        )
    except LawApiError as exc:
        return SearchTreatyOutput(results=[], message=f"조약 검색 실패: {exc}")

    results = [
        TreatySearchResultItem(
            treaty_id=h.treaty_id,
            treaty_name=h.treaty_name,
            treaty_type=h.treaty_type,
            effective_date=h.effective_date,
            signed_date=h.signed_date,
            treaty_number=h.treaty_number,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 조약이 없습니다."
    output = SearchTreatyOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
