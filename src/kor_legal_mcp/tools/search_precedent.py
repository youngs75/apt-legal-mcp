from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    PrecedentSearchResultItem,
    SearchPrecedentInput,
    SearchPrecedentOutput,
)
from kor_legal_mcp.tools._common import (
    ToolContext,
    extract_keywords,
    normalize_query,
    truncate,
)

COURT_LEVEL_MAP = {
    "대법원": "대법원",
    "supreme": "대법원",
    "고등": "고등법원",
    "고등법원": "고등법원",
    "high": "고등법원",
    "지방": "지방법원",
    "지방법원": "지방법원",
    "district": "지방법원",
}


def _normalize_court(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip().lower()
    for key, canonical in COURT_LEVEL_MAP.items():
        if key.lower() in v:
            return canonical
    return None


async def handle(ctx: ToolContext, payload: dict) -> SearchPrecedentOutput:
    params = SearchPrecedentInput.model_validate(payload)
    query = normalize_query(params.query)
    court = _normalize_court(params.court_level)

    cache_key = make_key(
        "tool.search_precedent",
        query=query,
        court=court,
        max_results=params.max_results,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchPrecedentOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_precedents(
            query=query,
            court_level=court,
            max_results=params.max_results,
        )
    except LawApiError as exc:
        return SearchPrecedentOutput(
            results=[],
            message=f"판례 검색 실패: {exc}",
        )

    keywords = extract_keywords(query)
    results = [
        PrecedentSearchResultItem(
            case_number=h.case_number or h.case_id,
            court=h.court,
            date=h.date,
            summary=truncate(h.case_name, limit=200),
            keywords=keywords,
        )
        for h in hits
    ]
    message = None if results else "해당 키워드에 일치하는 판례가 없습니다."
    output = SearchPrecedentOutput(results=results, message=message)
    await ctx.cache.set(cache_key, output.model_dump())
    return output
