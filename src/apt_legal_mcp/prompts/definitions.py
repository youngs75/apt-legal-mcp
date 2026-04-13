from __future__ import annotations

DISPUTE_RESOLUTION_TEMPLATE = (
    "당신은 공동주택 법률 자문 전문가입니다.\n"
    "분쟁 유형: {dispute_type}\n"
    "상황 설명: {description}\n\n"
    "관련 법령과 판례를 조회한 후, 단계별 대응 방법을 안내해 주세요."
)

RECONSTRUCTION_CHECKLIST_TEMPLATE = (
    "재건축·리모델링 절차 점검을 요청합니다.\n"
    "단지명: {complex_name}\n"
    "현재 단계: {current_stage}\n\n"
    "이 단계에서 확인해야 할 법적 요건과 절차를 정리해 주세요."
)

BID_COMPLIANCE_CHECK_TEMPLATE = (
    "관리업체 입찰 규정을 점검합니다.\n"
    "입찰 유형: {bid_type}\n"
    "계약 금액: {contract_amount}\n\n"
    "해당 입찰에 적용되는 공동주택관리법 조항과 준수 사항을 확인해 주세요."
)

MANAGEMENT_FEE_REVIEW_TEMPLATE = (
    "관리비 분쟁 검토 요청입니다.\n"
    "관리비 항목: {fee_category}\n"
    "분쟁 내용: {dispute_detail}\n\n"
    "관련 법령과 과거 사례를 바탕으로 정당성 여부를 검토해 주세요."
)
