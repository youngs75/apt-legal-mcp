from __future__ import annotations

from kor_legal_mcp.clients.law_api import LawApiError
from kor_legal_mcp.models.schemas import (
    GetAdmRuleDetailInput,
    GetAdmRuleDetailOutput,
)
from kor_legal_mcp.tools._common import ToolContext


class AdmRuleNotFound(Exception):
    pass


async def handle(ctx: ToolContext, payload: dict) -> GetAdmRuleDetailOutput:
    params = GetAdmRuleDetailInput.model_validate(payload)
    try:
        detail = await ctx.law_api.get_admrule_detail(params.rule_id)
    except LawApiError as exc:
        raise AdmRuleNotFound(f"행정규칙 조회 실패: {exc}") from exc

    if detail is None:
        raise AdmRuleNotFound(
            f"행정규칙일련번호 {params.rule_id}에 해당하는 규칙을 찾을 수 없습니다."
        )

    return GetAdmRuleDetailOutput(
        rule_id=detail.rule_id,
        rule_name=detail.rule_name,
        rule_type=detail.rule_type,
        issued_date=detail.issued_date,
        issued_number=detail.issued_number,
        agency=detail.agency,
        department=detail.department,
        enforcement_date=detail.enforcement_date,
        articles=detail.articles,
        amendment_reason=detail.amendment_reason,
    )
