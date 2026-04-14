from __future__ import annotations

from kor_legal_mcp.models.schemas import (
    SearchInterpretationInput,
    SearchInterpretationOutput,
)
from kor_legal_mcp.tools._common import ToolContext


async def handle(ctx: ToolContext, payload: dict) -> SearchInterpretationOutput:
    # 행정해석 데이터 소스는 후속 단계에서 통합될 예정.
    # 현 단계에서는 스키마를 준수하는 빈 응답과 안내 메시지를 반환한다.
    params = SearchInterpretationInput.model_validate(payload)
    _ = params
    return SearchInterpretationOutput(
        results=[],
        message="행정해석 데이터 소스는 아직 연동되지 않았습니다. 추후 업데이트 예정.",
    )
