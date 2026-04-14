from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetInterpretationDetailInput,
    GetInterpretationDetailOutput,
)
from kor_legal_mcp.tools._common import ToolContext


class InterpretationNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetInterpretationDetailOutput:
    params = GetInterpretationDetailInput.model_validate(payload)
    try:
        detail = await ctx.law_api.get_interpretation_detail(params.interpretation_id)
    except LawApiError as exc:
        raise InterpretationNotFound(f"법령해석례 조회 실패: {exc}") from exc

    if detail is None:
        raise InterpretationNotFound(
            f"법령해석례일련번호 {params.interpretation_id}에 해당하는 해석례를 찾을 수 없습니다."
        )

    return GetInterpretationDetailOutput(
        interpretation_id=detail.interpretation_id,
        case_name=detail.case_name,
        case_number=detail.case_number,
        interpretation_date=detail.interpretation_date,
        interpretation_agency=detail.interpretation_agency,
        inquiry_agency=detail.inquiry_agency,
        inquiry_summary=detail.inquiry_summary,
        answer=detail.answer,
        reasoning=detail.reasoning,
    )
