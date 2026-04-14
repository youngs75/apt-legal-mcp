from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetOrdinanceDetailInput,
    GetOrdinanceDetailOutput,
    OrdinanceArticleItem,
)
from kor_legal_mcp.tools._common import ToolContext


class OrdinanceNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetOrdinanceDetailOutput:
    params = GetOrdinanceDetailInput.model_validate(payload)
    try:
        detail = await ctx.law_api.get_ordinance_detail(params.ordinance_id)
    except LawApiError as exc:
        raise OrdinanceNotFound(f"자치법규 조회 실패: {exc}") from exc

    if detail is None:
        raise OrdinanceNotFound(
            f"자치법규ID {params.ordinance_id}에 해당하는 자치법규를 찾을 수 없습니다."
        )

    return GetOrdinanceDetailOutput(
        ordinance_id=detail.ordinance_id,
        ordinance_name=detail.ordinance_name,
        local_gov=detail.local_gov,
        ordinance_type=detail.ordinance_type,
        promulgation_date=detail.promulgation_date,
        enforcement_date=detail.enforcement_date,
        department=detail.department,
        amendment_type=detail.amendment_type,
        articles=[
            OrdinanceArticleItem(
                article_number=a.article_number,
                article_title=a.article_title,
                article_text=a.article_text,
            )
            for a in detail.articles
        ],
    )
