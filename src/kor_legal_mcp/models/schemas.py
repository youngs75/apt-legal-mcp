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
    title: str
    source: str
    date: str
    question: str
    answer: str
    related_laws: list[str]


class SearchInterpretationInput(BaseModel):
    query: NonEmptyStr
    source: str | None = None
    max_results: int = Field(default=5, ge=1, le=20)


class SearchInterpretationOutput(BaseModel):
    results: list[InterpretationResultItem]
    message: str | None = None


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
