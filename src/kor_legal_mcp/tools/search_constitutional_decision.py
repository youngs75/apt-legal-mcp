from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    ConstitutionalSearchResultItem,
    SearchConstitutionalDecisionInput,
    SearchConstitutionalDecisionOutput,
)
from kor_legal_mcp.tools._common import ToolContext, normalize_query


async def handle(
    ctx: ToolContext, payload: dict
) -> SearchConstitutionalDecisionOutput:
    params = SearchConstitutionalDecisionInput.model_validate(payload)
    query = normalize_query(params.query)

    cache_key = make_key(
        "tool.search_constitutional_decision",
        query=query,
        max_results=params.max_results,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchConstitutionalDecisionOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_constitutional_decisions(
            query=query, max_results=params.max_results
        )
    except LawApiError as exc:
        return SearchConstitutionalDecisionOutput(
            results=[], message=f"헌재결정례 검색 실패: {exc}"
        )

    results = [
        ConstitutionalSearchResultItem(
            decision_id=h.decision_id,
            case_number=h.case_number,
            case_name=h.case_name,
            decision_date=h.decision_date,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 헌재결정례가 없습니다."
    output = SearchConstitutionalDecisionOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
