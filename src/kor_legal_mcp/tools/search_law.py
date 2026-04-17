from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    LawSearchResultItem,
    SearchLawInput,
    SearchLawOutput,
)
from kor_legal_mcp.tools._common import (
    ToolContext,
    normalize_query,
    score_relevance,
    snippet_around,
)


async def handle(ctx: ToolContext, payload: dict) -> SearchLawOutput:
    params = SearchLawInput.model_validate(payload)
    query = normalize_query(params.query)
    effective_query = f"{params.law_name} {query}".strip() if params.law_name else query

    cache_key = make_key(
        "tool.search_law",
        query=effective_query,
        max_results=params.max_results,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return SearchLawOutput.model_validate(cached)

    try:
        hits = await ctx.law_api.search_laws(effective_query, max_results=params.max_results)
    except LawApiError:
        stale = await ctx.cache.get(cache_key + ":stale")
        if stale is not None:
            return SearchLawOutput.model_validate(stale)
        raise

    if not hits:
        keywords = [t for t in effective_query.split() if len(t) > 1]
        if keywords:
            retry_query = " ".join(keywords[:3])
            if retry_query != effective_query:
                hits = await ctx.law_api.search_laws(
                    retry_query, max_results=params.max_results
                )

    # Fallback: when law_name is specified but combined query yielded no
    # hits, search by law_name alone and rank articles locally by relevance
    # to the original query.  law.go.kr full-text search often fails on
    # combined terms like "공동주택관리법 장기수선충당금".
    local_filter = False
    if not hits and params.law_name:
        hits = await ctx.law_api.search_laws(params.law_name, max_results=params.max_results)
        local_filter = True

    results: list[LawSearchResultItem] = []
    for hit in hits[: params.max_results]:
        articles = []
        try:
            articles = await ctx.law_api.get_law_detail(hit.mst)
        except LawApiError:
            articles = []
        if not articles:
            results.append(
                LawSearchResultItem(
                    law_name=hit.law_name,
                    article_number="-",
                    article_title="",
                    snippet="",
                    relevance_score=score_relevance(query, hit.law_name),
                )
            )
            continue

        if local_filter:
            # Return top-N articles ranked by relevance to the original
            # query instead of just the single best match.
            scored = sorted(
                articles,
                key=lambda a: score_relevance(
                    query, f"{a.article_title}\n{a.full_text}"
                ),
                reverse=True,
            )
            for art in scored[:3]:
                sc = score_relevance(query, f"{art.article_title}\n{art.full_text}")
                if sc > 0:
                    results.append(
                        LawSearchResultItem(
                            law_name=hit.law_name,
                            article_number=art.article_number,
                            article_title=art.article_title,
                            snippet=snippet_around(art.full_text, query),
                            relevance_score=sc,
                        )
                    )
        else:
            best = max(
                articles,
                key=lambda a: score_relevance(
                    query, f"{a.article_title}\n{a.full_text}"
                ),
            )
            results.append(
                LawSearchResultItem(
                    law_name=hit.law_name,
                    article_number=best.article_number,
                    article_title=best.article_title,
                    snippet=snippet_around(best.full_text, query),
                    relevance_score=score_relevance(
                        query, f"{best.article_title}\n{best.full_text}"
                    ),
                )
            )

    results.sort(key=lambda r: r.relevance_score, reverse=True)
    message = None
    if not results:
        message = "검색 결과가 없습니다. 다른 키워드를 시도해 주세요."
    output = SearchLawOutput(results=results, message=message)
    dumped = output.model_dump()
    await ctx.cache.set(cache_key, dumped)
    await ctx.cache.set(cache_key + ":stale", dumped, ttl_seconds=7 * 24 * 3600)
    return output
