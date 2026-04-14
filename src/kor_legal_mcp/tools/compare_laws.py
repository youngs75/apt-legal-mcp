from __future__ import annotations

import asyncio

from kor_legal_mcp.clients.article_number import normalize_article_number
from kor_legal_mcp.models.schemas import (
    CompareLawsInput,
    CompareLawsOutput,
    ComparisonResultItem,
)
from kor_legal_mcp.tools._common import ToolContext


async def handle(ctx: ToolContext, payload: dict) -> CompareLawsOutput:
    params = CompareLawsInput.model_validate(payload)

    async def _fetch(law_name: str, article_number: str) -> ComparisonResultItem | None:
        canonical = normalize_article_number(article_number) or article_number
        article = await ctx.law_api.get_article(law_name, canonical)
        if article is None:
            return ComparisonResultItem(
                law_name=law_name,
                article_number=canonical,
                article_title="(조회 실패)",
                full_text="",
            )
        return ComparisonResultItem(
            law_name=article.law_name or law_name,
            article_number=article.article_number,
            article_title=article.article_title,
            full_text=article.full_text,
        )

    results = await asyncio.gather(
        *(_fetch(c.law_name, c.article_number) for c in params.comparisons)
    )
    items = [r for r in results if r is not None]

    note = f"비교 관점: {params.focus}" if params.focus else "조문 본문을 나란히 비교하세요."
    return CompareLawsOutput(items=items, comparison_note=note)
