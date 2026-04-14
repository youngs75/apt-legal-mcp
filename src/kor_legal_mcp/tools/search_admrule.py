from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    AdmRuleSearchResultItem,
    SearchAdmRuleInput,
    SearchAdmRuleOutput,
)
from kor_legal_mcp.tools._common import ToolContext, normalize_query


async def handle(ctx: ToolContext, payload: dict) -> SearchAdmRuleOutput:
    params = SearchAdmRuleInput.model_validate(payload)
    query = normalize_query(params.query)

    cache_key = make_key(
        "tool.search_admrule", query=query, max_results=params.max_results
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchAdmRuleOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_admrules(
            query=query, max_results=params.max_results
        )
    except LawApiError as exc:
        return SearchAdmRuleOutput(
            results=[], message=f"행정규칙 검색 실패: {exc}"
        )

    results = [
        AdmRuleSearchResultItem(
            rule_id=h.rule_id,
            rule_name=h.rule_name,
            rule_type=h.rule_type,
            issued_date=h.issued_date,
            issued_number=h.issued_number,
            agency=h.agency,
            enforcement_date=h.enforcement_date,
            is_current=h.is_current,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 행정규칙이 없습니다."
    output = SearchAdmRuleOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
