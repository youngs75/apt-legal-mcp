from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, Field


def _non_empty(v: str) -> str:
    if not v or not v.strip():
        raise ValueError("must not be empty")
    return v.strip()


# Pydantic v2: using Annotated + BeforeValidator avoids the classmethod
# pitfall of `field_validator(...)(lambda cls, v: ...)`, which silently
# passes ValidationInfo as `v` and breaks at runtime.
NonEmptyStr = Annotated[str, BeforeValidator(_non_empty)]


class LawSearchResultItem(BaseModel):
    law_name: str
    article_number: str
    article_title: str
    snippet: str
    relevance_score: float = Field(ge=0.0, le=1.0)


class SearchLawInput(BaseModel):
    query: NonEmptyStr
    law_name: str | None = None
    max_results: int = Field(default=5, ge=1, le=20)


class SearchLawOutput(BaseModel):
    results: list[LawSearchResultItem]
    message: str | None = None


class GetLawArticleInput(BaseModel):
    law_name: NonEmptyStr
    article_number: NonEmptyStr
    include_history: bool = False


class AmendmentHistoryItem(BaseModel):
    date: str
    description: str


class GetLawArticleOutput(BaseModel):
    law_name: str
    article_number: str
    article_title: str
    full_text: str
    enforcement_date: str | None = None
    last_amended: str | None = None
    amendment_history: list[AmendmentHistoryItem] | None = None


class PrecedentSearchResultItem(BaseModel):
    case_id: str  # 판례일련번호 — pass this to get_precedent_detail for fastest lookup
    case_number: str
    court: str
    date: str
    summary: str
    keywords: list[str]


CourtLevel = Literal["대법원", "고등법원", "지방법원"]


class SearchPrecedentInput(BaseModel):
    query: NonEmptyStr
    court_level: str | None = None
    max_results: int = Field(default=5, ge=1, le=20)


class SearchPrecedentOutput(BaseModel):
    results: list[PrecedentSearchResultItem]
    message: str | None = None


class GetPrecedentDetailInput(BaseModel):
    case_number: NonEmptyStr


class GetPrecedentDetailOutput(BaseModel):
    case_number: str
    court: str
    date: str
    case_type: str
    summary: str
    facts: str
    reasoning: str
    ruling: str
    related_laws: list[str]


class InterpretationResultItem(BaseModel):
    interpretation_id: str  # 법령해석례일련번호 — pass to get_interpretation_detail
    case_name: str          # 안건명
    case_number: str        # 안건번호
    inquiry_agency: str     # 질의기관명
    reply_agency: str       # 회신기관명
    reply_date: str         # 회신일자


class SearchInterpretationInput(BaseModel):
    query: NonEmptyStr
    source: str | None = None
    max_results: int = Field(default=5, ge=1, le=20)


class SearchInterpretationOutput(BaseModel):
    results: list[InterpretationResultItem]
    message: str | None = None


class GetInterpretationDetailInput(BaseModel):
    interpretation_id: NonEmptyStr


class GetInterpretationDetailOutput(BaseModel):
    interpretation_id: str
    case_name: str
    case_number: str
    interpretation_date: str
    interpretation_agency: str
    inquiry_agency: str
    inquiry_summary: str    # 질의요지
    answer: str             # 회답
    reasoning: str          # 이유


# ------------------------- 헌법재판소 결정례 -------------------------
class ConstitutionalSearchResultItem(BaseModel):
    decision_id: str        # 헌재결정례일련번호 — pass to detail
    case_number: str
    case_name: str
    decision_date: str


class SearchConstitutionalDecisionInput(BaseModel):
    query: NonEmptyStr
    max_results: int = Field(default=5, ge=1, le=20)


class SearchConstitutionalDecisionOutput(BaseModel):
    results: list[ConstitutionalSearchResultItem]
    message: str | None = None


class GetConstitutionalDecisionDetailInput(BaseModel):
    decision_id: NonEmptyStr


class GetConstitutionalDecisionDetailOutput(BaseModel):
    decision_id: str
    case_number: str
    case_name: str
    decision_date: str
    case_type: str
    holding: str            # 판시사항
    summary: str            # 결정요지
    full_text: str          # 전문
    related_laws: str       # 참조조문
    related_precedents: str  # 참조판례
    target_laws: str        # 심판대상조문


# ------------------------- 행정규칙 -------------------------
class AdmRuleSearchResultItem(BaseModel):
    rule_id: str            # 행정규칙일련번호
    rule_name: str
    rule_type: str          # 훈령/예규/고시
    issued_date: str
    issued_number: str
    agency: str             # 소관부처명
    enforcement_date: str
    is_current: str         # 현행/연혁


class SearchAdmRuleInput(BaseModel):
    query: NonEmptyStr
    max_results: int = Field(default=5, ge=1, le=20)


class SearchAdmRuleOutput(BaseModel):
    results: list[AdmRuleSearchResultItem]
    message: str | None = None


class GetAdmRuleDetailInput(BaseModel):
    rule_id: NonEmptyStr


class GetAdmRuleDetailOutput(BaseModel):
    rule_id: str
    rule_name: str
    rule_type: str
    issued_date: str
    issued_number: str
    agency: str
    department: str
    enforcement_date: str
    articles: list[str]
    amendment_reason: str


# ------------------------- 자치법규 -------------------------
class OrdinanceSearchResultItem(BaseModel):
    ordinance_id: str       # 자치법규ID — pass to detail
    ordinance_name: str
    local_gov: str          # 지자체기관명
    ordinance_type: str     # 조례/규칙
    promulgation_date: str
    enforcement_date: str


class SearchOrdinanceInput(BaseModel):
    query: NonEmptyStr
    region: str | None = None  # 지자체 이름 부분 일치 (예: "서울특별시")
    max_results: int = Field(default=5, ge=1, le=20)


class SearchOrdinanceOutput(BaseModel):
    results: list[OrdinanceSearchResultItem]
    message: str | None = None


class GetOrdinanceDetailInput(BaseModel):
    ordinance_id: NonEmptyStr


class OrdinanceArticleItem(BaseModel):
    article_number: str
    article_title: str
    article_text: str


class GetOrdinanceDetailOutput(BaseModel):
    ordinance_id: str
    ordinance_name: str
    local_gov: str
    ordinance_type: str
    promulgation_date: str
    enforcement_date: str
    department: str
    amendment_type: str
    articles: list[OrdinanceArticleItem]


# ------------------------- 조약 -------------------------
class TreatySearchResultItem(BaseModel):
    treaty_id: str          # 조약일련번호 — pass to detail
    treaty_name: str
    treaty_type: str        # 양자조약/다자조약
    effective_date: str
    signed_date: str
    treaty_number: str


class SearchTreatyInput(BaseModel):
    query: NonEmptyStr
    max_results: int = Field(default=5, ge=1, le=20)


class SearchTreatyOutput(BaseModel):
    results: list[TreatySearchResultItem]
    message: str | None = None


class GetTreatyDetailInput(BaseModel):
    treaty_id: NonEmptyStr


class GetTreatyDetailOutput(BaseModel):
    treaty_id: str
    treaty_name_ko: str
    treaty_name_en: str
    treaty_type: str
    treaty_number: str
    effective_date: str
    signed_date: str
    category: str
    depositary: str
    content: str


class ComparisonItem(BaseModel):
    law_name: NonEmptyStr
    article_number: NonEmptyStr


class CompareLawsInput(BaseModel):
    comparisons: list[ComparisonItem] = Field(min_length=2, max_length=5)
    focus: str | None = None


class ComparisonResultItem(BaseModel):
    law_name: str
    article_number: str
    article_title: str
    full_text: str


class CompareLawsOutput(BaseModel):
    items: list[ComparisonResultItem]
    comparison_note: str
