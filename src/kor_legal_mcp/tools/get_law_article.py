from __future__ import annotations

from kor_legal_mcp.cache.memory_cache import make_key
from kor_legal_mcp.clients.article_number import normalize_article_number
from kor_legal_mcp.models.schemas import GetLawArticleInput, GetLawArticleOutput
from kor_legal_mcp.tools._common import ToolContext


class ArticleNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetLawArticleOutput:
    params = GetLawArticleInput.model_validate(payload)
    canonical = normalize_article_number(params.article_number) or params.article_number

    cache_key = make_key(
        "tool.get_law_article",
        law_name=params.law_name,
        article=canonical,
        history=params.include_history,
    )
    cached = await ctx.cache.get(cache_key)
    if cached is not None:
        return GetLawArticleOutput.model_validate(cached)

    article = await ctx.law_api.get_article(params.law_name, canonical)
    if article is None:
        raise ArticleNotFound(
            f"{params.law_name} {canonical} 조문을 찾을 수 없습니다."
        )

    output = GetLawArticleOutput(
        law_name=article.law_name or params.law_name,
        article_number=article.article_number,
        article_title=article.article_title,
        full_text=article.full_text,
        enforcement_date=None,
        last_amended=None,
        amendment_history=None,
    )
    await ctx.cache.set(cache_key, output.model_dump(), ttl_seconds=7 * 24 * 3600)
    return output
