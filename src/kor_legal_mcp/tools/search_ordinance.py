from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    OrdinanceSearchResultItem,
    SearchOrdinanceInput,
    SearchOrdinanceOutput,
)
from kor_legal_mcp.tools._common import ToolContext, normalize_query


async def handle(ctx: ToolContext, payload: dict) -> SearchOrdinanceOutput:
    params = SearchOrdinanceInput.model_validate(payload)
    query = normalize_query(params.query)

    cache_key = make_key(
        "tool.search_ordinance",
        query=query,
        region=params.region,
        max_results=params.max_results,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchOrdinanceOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_ordinances(
            query=query, region=params.region, max_results=params.max_results
        )
    except LawApiError as exc:
        return SearchOrdinanceOutput(
            results=[], message=f"자치법규 검색 실패: {exc}"
        )

    results = [
        OrdinanceSearchResultItem(
            ordinance_id=h.ordinance_id,
            ordinance_name=h.ordinance_name,
            local_gov=h.local_gov,
            ordinance_type=h.ordinance_type,
            promulgation_date=h.promulgation_date,
            enforcement_date=h.enforcement_date,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 자치법규가 없습니다."
    output = SearchOrdinanceOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
