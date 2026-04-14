from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetTreatyDetailInput,
    GetTreatyDetailOutput,
)
from kor_legal_mcp.tools._common import ToolContext


class TreatyNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetTreatyDetailOutput:
    params = GetTreatyDetailInput.model_validate(payload)
    try:
        detail = await ctx.law_api.get_treaty_detail(params.treaty_id)
    except LawApiError as exc:
        raise TreatyNotFound(f"조약 조회 실패: {exc}") from exc

    if detail is None:
        raise TreatyNotFound(
            f"조약일련번호 {params.treaty_id}에 해당하는 조약을 찾을 수 없습니다."
        )

    return GetTreatyDetailOutput(
        treaty_id=detail.treaty_id,
        treaty_name_ko=detail.treaty_name_ko,
        treaty_name_en=detail.treaty_name_en,
        treaty_type=detail.treaty_type,
        treaty_number=detail.treaty_number,
        effective_date=detail.effective_date,
        signed_date=detail.signed_date,
        category=detail.category,
        depositary=detail.depositary,
        content=detail.content,
    )
