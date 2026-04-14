from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetPrecedentDetailInput,
    GetPrecedentDetailOutput,
)
from kor_legal_mcp.tools._common import ToolContext, truncate


class PrecedentNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetPrecedentDetailOutput:
    params = GetPrecedentDetailInput.model_validate(payload)
    case_ref = params.case_number.strip()

    # `case_number`로 받은 값이 판례일련번호(숫자)일 수도, 사건번호("2020다12345")일
    # 수도 있다. 먼저 일련번호로 직접 조회하고, 실패하면 검색으로 폴백한다.
    detail = None
    try:
        if case_ref.isdigit():
            detail = await ctx.law_api.get_precedent_detail(case_ref)
        if detail is None:
            hits = await ctx.law_api.search_precedents(query=case_ref, max_results=5)
            match = next(
                (h for h in hits if h.case_number == case_ref or h.case_id == case_ref),
                hits[0] if hits else None,
            )
            if match and match.case_id:
                detail = await ctx.law_api.get_precedent_detail(match.case_id)
    except LawApiError as exc:
        raise PrecedentNotFound(f"판례 조회 실패: {exc}") from exc

    if detail is None:
        raise PrecedentNotFound(
            f"사건번호/일련번호 {case_ref}에 해당하는 판례를 찾을 수 없습니다."
        )

    return GetPrecedentDetailOutput(
        case_number=detail.case_number or detail.case_id,
        court=detail.court,
        date=detail.date,
        case_type=detail.case_type,
        summary=truncate(detail.summary or detail.holding, limit=500),
        facts=truncate(detail.reasoning, limit=1000),
        reasoning=truncate(detail.reasoning, limit=2000),
        ruling=truncate(detail.ruling, limit=500),
        related_laws=detail.related_laws,
    )
