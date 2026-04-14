from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetConstitutionalDecisionDetailInput,
    GetConstitutionalDecisionDetailOutput,
)
from kor_legal_mcp.tools._common import ToolContext


class ConstitutionalDecisionNotFound(Exception):
    pass


async def handle(
    ctx: ToolContext, payload: dict
) -> GetConstitutionalDecisionDetailOutput:
    params = GetConstitutionalDecisionDetailInput.model_validate(payload)
    try:
        detail = await ctx.law_api.get_constitutional_decision_detail(
            params.decision_id
        )
    except LawApiError as exc:
        raise ConstitutionalDecisionNotFound(f"헌재결정례 조회 실패: {exc}") from exc

    if detail is None:
        raise ConstitutionalDecisionNotFound(
            f"헌재결정례일련번호 {params.decision_id}에 해당하는 결정례를 찾을 수 없습니다."
        )

    return GetConstitutionalDecisionDetailOutput(
        decision_id=detail.decision_id,
        case_number=detail.case_number,
        case_name=detail.case_name,
        decision_date=detail.decision_date,
        case_type=detail.case_type,
        holding=detail.holding,
        summary=detail.summary,
        full_text=detail.full_text,
        related_laws=detail.related_laws,
        related_precedents=detail.related_precedents,
        target_laws=detail.target_laws,
    )
