from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    InterpretationResultItem,
    SearchInterpretationInput,
    SearchInterpretationOutput,
)
from kor_legal_mcp.tools._common import ToolContext, normalize_query


async def handle(ctx: ToolContext, payload: dict) -> SearchInterpretationOutput:
    params = SearchInterpretationInput.model_validate(payload)
    query = normalize_query(params.query)

    cache_key = make_key(
        "tool.search_interpretation",
        query=query,
        source=params.source,
        max_results=params.max_results,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchInterpretationOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_interpretations(
            query=query, max_results=params.max_results
        )
    except LawApiError as exc:
        return SearchInterpretationOutput(
            results=[], message=f"법령해석례 검색 실패: {exc}"
        )

    # `source` 필터: 회신기관명 부분 일치 (예: "법제처", "국토교통부")
    if params.source:
        hits = [h for h in hits if params.source in h.reply_agency]

    results = [
        InterpretationResultItem(
            interpretation_id=h.interpretation_id,
            case_name=h.case_name,
            case_number=h.case_number,
            inquiry_agency=h.inquiry_agency,
            reply_agency=h.reply_agency,
            reply_date=h.reply_date,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 법령해석례가 없습니다."
    output = SearchInterpretationOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
