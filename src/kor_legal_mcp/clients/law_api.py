from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx
from lxml import etree

from kor_legal_mcp.cache.memory_cache import MemoryCache, make_key
from kor_legal_mcp.clients.article_number import article_matches, normalize_article_number
from kor_legal_mcp.config import settings

logger = logging.getLogger(__name__)

WARMUP_LAWS = [
    "공동주택관리법",
    "공동주택관리법 시행령",
    "집합건물의 소유 및 관리에 관한 법률",
    "주택법",
    "도시 및 주거환경정비법",
    "민법",
]


@dataclass
class LawSearchHit:
    law_name: str
    mst: str
    enforcement_date: str | None
    last_amended: str | None


@dataclass
class Article:
    law_name: str
    article_number: str  # canonical "제20조"
    article_title: str
    full_text: str


@dataclass
class PrecedentHit:
    case_id: str
    case_number: str
    case_name: str
    court: str
    date: str
    case_type: str


@dataclass
class PrecedentFull:
    case_id: str
    case_number: str
    case_name: str
    court: str
    date: str
    case_type: str
    holding: str       # 판시사항
    summary: str       # 판결요지
    reasoning: str     # 판례내용 / 판단근거
    ruling: str        # 주문
    related_laws: list[str]


# --- 법령해석례 (법제처·부처 유권해석) ---
@dataclass
class InterpretationHit:
    interpretation_id: str    # 법령해석례일련번호
    case_name: str            # 안건명
    case_number: str          # 안건번호
    inquiry_agency: str       # 질의기관명
    reply_agency: str         # 회신기관명
    reply_date: str           # 회신일자


@dataclass
class InterpretationFull:
    interpretation_id: str
    case_name: str
    case_number: str
    interpretation_date: str  # 해석일자
    interpretation_agency: str  # 해석기관명
    inquiry_agency: str
    inquiry_summary: str      # 질의요지
    answer: str               # 회답
    reasoning: str            # 이유


# --- 헌법재판소 결정례 ---
@dataclass
class ConstitutionalHit:
    decision_id: str          # 헌재결정례일련번호
    case_number: str          # 사건번호
    case_name: str            # 사건명
    decision_date: str        # 종국일자


@dataclass
class ConstitutionalFull:
    decision_id: str
    case_number: str
    case_name: str
    decision_date: str
    case_type: str            # 사건종류명
    holding: str              # 판시사항
    summary: str              # 결정요지
    full_text: str            # 전문
    related_laws: str         # 참조조문
    related_precedents: str   # 참조판례
    target_laws: str          # 심판대상조문


# --- 행정규칙 (훈령·예규·고시) ---
@dataclass
class AdmRuleHit:
    rule_id: str              # 행정규칙일련번호
    rule_name: str            # 행정규칙명
    rule_type: str            # 행정규칙종류
    issued_date: str          # 발령일자
    issued_number: str        # 발령번호
    agency: str               # 소관부처명
    enforcement_date: str     # 시행일자
    is_current: str           # 현행여부 (Y/N)


@dataclass
class AdmRuleArticle:
    content: str              # 조문내용 (단일 문자열)


@dataclass
class AdmRuleFull:
    rule_id: str
    rule_name: str
    rule_type: str
    issued_date: str
    issued_number: str
    agency: str
    department: str           # 담당부서기관명
    enforcement_date: str
    articles: list[str]       # 조문내용[]
    amendment_reason: str     # 제개정이유


# --- 자치법규 (지자체 조례·규칙) ---
@dataclass
class OrdinanceHit:
    ordinance_id: str         # 자치법규ID (detail에서 ID 파라미터로 사용)
    ordinance_serial: str     # 자치법규일련번호
    ordinance_name: str       # 자치법규명
    local_gov: str            # 지자체기관명
    ordinance_type: str       # 자치법규종류 (조례/규칙)
    promulgation_date: str    # 공포일자
    enforcement_date: str     # 시행일자


@dataclass
class OrdinanceArticle:
    article_number: str       # 조번호
    article_title: str        # 조제목
    article_text: str         # 조내용


@dataclass
class OrdinanceFull:
    ordinance_id: str
    ordinance_serial: str
    ordinance_name: str
    local_gov: str
    ordinance_type: str
    promulgation_date: str
    enforcement_date: str
    department: str           # 담당부서명
    amendment_type: str       # 제개정정보
    articles: list[OrdinanceArticle]


# --- 조약 ---
@dataclass
class TreatyHit:
    treaty_id: str            # 조약일련번호
    treaty_name: str          # 조약명
    treaty_type: str          # 조약구분명
    effective_date: str       # 발효일자
    signed_date: str          # 서명일자
    treaty_number: str        # 조약번호


@dataclass
class TreatyFull:
    treaty_id: str
    treaty_name_ko: str       # 조약명_한글
    treaty_name_en: str       # 조약명_영문
    treaty_type: str
    treaty_number: str
    effective_date: str
    signed_date: str
    category: str             # 다자조약분야명
    depositary: str           # 기탁처
    content: str              # 조약내용


class LawApiError(Exception):
    pass


class LawApiClient:
    def __init__(
        self,
        search_url: str | None = None,
        service_url: str | None = None,
        api_key: str | None = None,
        cache: MemoryCache | None = None,
        timeout: float | None = None,
        max_concurrency: int | None = None,
    ):
        self._search_url = search_url or settings.law_api_search_url
        self._service_url = service_url or settings.law_api_service_url
        self._api_key = api_key or settings.law_api_key
        self._cache = cache or MemoryCache(
            max_items=settings.cache_max_items,
            default_ttl_seconds=settings.cache_ttl_hours * 3600,
        )
        self._timeout = timeout or settings.law_api_timeout_seconds
        self._sem = asyncio.Semaphore(max_concurrency or settings.law_api_max_concurrency)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "LawApiClient":
        self._client = httpx.AsyncClient(timeout=self._timeout)
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def _get_xml(
        self, params: dict[str, str], endpoint: str = "service"
    ) -> etree._Element:
        url = self._search_url if endpoint == "search" else self._service_url
        params = {"OC": self._api_key, **params}
        client = self._ensure_client()
        last_exc: Exception | None = None
        async with self._sem:
            for attempt in range(3):
                try:
                    resp = await client.get(url, params=params)
                    resp.raise_for_status()
                    last_exc = None
                    break
                except httpx.HTTPError as exc:
                    last_exc = exc
                    if attempt < 2:
                        await asyncio.sleep(0.3 * (attempt + 1))
                        continue
        if last_exc is not None:
            # Some httpx exceptions (RemoteProtocolError, ConnectError) have
            # an empty str() — include the class name so logs are diagnosable.
            raise LawApiError(
                f"law.go.kr request failed [{type(last_exc).__name__}]: "
                f"{last_exc!r}"
            ) from last_exc
        raw = resp.content
        # Encoding fallback: try UTF-8 then EUC-KR.
        text: str
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            try:
                text = raw.decode("euc-kr")
            except UnicodeDecodeError:
                text = raw.decode("utf-8", errors="replace")
        try:
            return etree.fromstring(text.encode("utf-8"))
        except etree.XMLSyntaxError as exc:
            raise LawApiError(f"invalid XML from law.go.kr: {exc}") from exc

    async def search_laws(self, query: str, max_results: int = 5) -> list[LawSearchHit]:
        key = make_key("law_api.search_laws", query=query, max_results=max_results)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "law",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[LawSearchHit] = []
        for law_el in root.findall(".//law"):
            name = _text(law_el, "법령명한글") or _text(law_el, "법령명")
            mst = _text(law_el, "법령일련번호") or _text(law_el, "MST")
            if not name or not mst:
                continue
            hits.append(
                LawSearchHit(
                    law_name=name.strip(),
                    mst=mst.strip(),
                    enforcement_date=_text(law_el, "시행일자"),
                    last_amended=_text(law_el, "공포일자"),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_law_detail(self, mst: str) -> list[Article]:
        key = make_key("law_api.get_law_detail", mst=mst)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "law", "MST": mst, "type": "XML"}, endpoint="service"
        )
        law_name = (
            _text(root, ".//법령명_한글")
            or _text(root, ".//법령명한글")
            or _text(root, ".//법령명")
            or ""
        ).strip()
        articles: list[Article] = []
        for art_el in root.findall(".//조문단위"):
            num_raw = _text(art_el, "조문번호")
            if not num_raw:
                continue
            sub = _text(art_el, "조문가지번호")
            canonical_raw = f"제{num_raw}조"
            if sub and sub != "0":
                canonical_raw = f"{canonical_raw}의{sub}"
            canonical = normalize_article_number(canonical_raw) or canonical_raw
            title = (_text(art_el, "조문제목") or "").strip()
            body = (_text(art_el, "조문내용") or "").strip()
            # Append paragraphs (항) and subparagraphs (호)
            parts: list[str] = [body] if body else []
            for hang_el in art_el.findall(".//항"):
                hang_text = (_text(hang_el, "항내용") or "").strip()
                if hang_text:
                    parts.append(hang_text)
                for ho_el in hang_el.findall(".//호"):
                    ho_text = (_text(ho_el, "호내용") or "").strip()
                    if ho_text:
                        parts.append(ho_text)
            full_text = "\n".join(parts).strip()
            articles.append(
                Article(
                    law_name=law_name,
                    article_number=canonical,
                    article_title=title,
                    full_text=full_text,
                )
            )
        await self._cache.set(key, articles, ttl_seconds=7 * 24 * 3600)
        return articles

    async def get_article(self, law_name: str, article_number: str) -> Article | None:
        hits = await self.search_laws(law_name, max_results=5)
        target = self._best_law_match(law_name, hits)
        if target is None:
            return None
        articles = await self.get_law_detail(target.mst)
        for art in articles:
            if article_matches(art.article_number, article_number):
                return art
        return None

    @staticmethod
    def _best_law_match(
        law_name: str, hits: list[LawSearchHit]
    ) -> LawSearchHit | None:
        if not hits:
            return None
        # 1. Exact name match
        for hit in hits:
            if hit.law_name == law_name:
                return hit
        # 2. Substring match — prefer shortest name (본법 > 시행령 > 시행규칙)
        candidates = [
            hit for hit in hits
            if law_name in hit.law_name or hit.law_name in law_name
        ]
        if candidates:
            return min(candidates, key=lambda h: len(h.law_name))
        # 3. Fallback to first result
        return hits[0]

    async def search_precedents(
        self,
        query: str,
        court_level: str | None = None,
        max_results: int = 5,
        body_search: bool = True,
    ) -> list[PrecedentHit]:
        # body_search=True (default): search=2 본문검색 — better recall for
        # semantic queries like "층간소음".
        # body_search=False: omit search param → law.go.kr defaults to
        # section=evtNm (사건명/사건번호 metadata). Required when looking up
        # a precedent by its 사건번호 (e.g. "2021마6763") because the case
        # number is not part of body text.
        key = make_key(
            "law_api.search_precedents",
            query=query,
            court_level=court_level,
            max_results=max_results,
            body_search=body_search,
        )
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        params = {
            "target": "prec",
            "type": "XML",
            "query": query,
            "display": str(max_results),
        }
        if body_search:
            params["search"] = "2"
        root = await self._get_xml(params, endpoint="search")
        hits: list[PrecedentHit] = []
        for prec_el in root.findall(".//prec"):
            case_id = (_text(prec_el, "판례일련번호") or "").strip()
            case_number = (
                _text(prec_el, "사건번호") or _text(prec_el, "판례번호") or ""
            ).strip()
            case_name = (_text(prec_el, "사건명") or "").strip()
            court = (_text(prec_el, "법원명") or "").strip()
            date = (_text(prec_el, "선고일자") or "").strip()
            case_type = (_text(prec_el, "사건종류명") or "").strip()
            if not case_id and not case_number:
                continue
            if court_level and court_level not in court:
                continue
            hits.append(
                PrecedentHit(
                    case_id=case_id,
                    case_number=case_number,
                    case_name=case_name,
                    court=court,
                    date=date,
                    case_type=case_type,
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_precedent_detail(self, case_id: str) -> PrecedentFull | None:
        key = make_key("law_api.get_precedent_detail", case_id=case_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        # law.go.kr uses ID or LID param depending on endpoint variant.
        root = await self._get_xml(
            {"target": "prec", "ID": case_id, "type": "XML"}, endpoint="service"
        )
        node = root.find(".//prec") if root.tag != "prec" else root
        if node is None:
            node = root
        case_number = (
            _text(node, "사건번호") or _text(node, "판례번호") or ""
        ).strip()
        case_name = (_text(node, "사건명") or "").strip()
        court = (_text(node, "법원명") or "").strip()
        date = (_text(node, "선고일자") or "").strip()
        case_type = (_text(node, "사건종류명") or "").strip()
        holding = (_text(node, "판시사항") or "").strip()
        summary = (_text(node, "판결요지") or "").strip()
        reasoning = (_text(node, "판례내용") or _text(node, "전문") or "").strip()
        ruling = (_text(node, "주문") or "").strip()
        refs_raw = (_text(node, "참조조문") or "").strip()
        related_laws = [r.strip() for r in refs_raw.replace(";", ",").split(",") if r.strip()]

        if not case_number and not case_name and not reasoning and not summary:
            return None

        detail = PrecedentFull(
            case_id=case_id,
            case_number=case_number,
            case_name=case_name,
            court=court,
            date=date,
            case_type=case_type,
            holding=holding,
            summary=summary,
            reasoning=reasoning,
            ruling=ruling,
            related_laws=related_laws,
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    # ---------------------------------------------------------------
    # 법령해석례 (expc)
    # ---------------------------------------------------------------
    async def search_interpretations(
        self, query: str, max_results: int = 5
    ) -> list[InterpretationHit]:
        key = make_key(
            "law_api.search_interpretations", query=query, max_results=max_results
        )
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "expc",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[InterpretationHit] = []
        for el in root.findall(".//expc"):
            iid = (_text(el, "법령해석례일련번호") or "").strip()
            if not iid:
                continue
            hits.append(
                InterpretationHit(
                    interpretation_id=iid,
                    case_name=(_text(el, "안건명") or "").strip(),
                    case_number=(_text(el, "안건번호") or "").strip(),
                    inquiry_agency=(_text(el, "질의기관명") or "").strip(),
                    reply_agency=(_text(el, "회신기관명") or "").strip(),
                    reply_date=(_text(el, "회신일자") or "").strip(),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_interpretation_detail(
        self, interpretation_id: str
    ) -> InterpretationFull | None:
        key = make_key("law_api.get_interpretation_detail", id=interpretation_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "expc", "ID": interpretation_id, "type": "XML"},
            endpoint="service",
        )
        iid = (_text(root, ".//법령해석례일련번호") or "").strip()
        if not iid:
            return None
        detail = InterpretationFull(
            interpretation_id=iid,
            case_name=(_text(root, ".//안건명") or "").strip(),
            case_number=(_text(root, ".//안건번호") or "").strip(),
            interpretation_date=(_text(root, ".//해석일자") or "").strip(),
            interpretation_agency=(_text(root, ".//해석기관명") or "").strip(),
            inquiry_agency=(_text(root, ".//질의기관명") or "").strip(),
            inquiry_summary=(_text(root, ".//질의요지") or "").strip(),
            answer=(_text(root, ".//회답") or "").strip(),
            reasoning=(_text(root, ".//이유") or "").strip(),
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    # ---------------------------------------------------------------
    # 헌법재판소 결정례 (detc)
    # ---------------------------------------------------------------
    async def search_constitutional_decisions(
        self, query: str, max_results: int = 5
    ) -> list[ConstitutionalHit]:
        key = make_key(
            "law_api.search_constitutional_decisions",
            query=query,
            max_results=max_results,
        )
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "detc",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[ConstitutionalHit] = []
        for el in root.findall(".//Detc"):
            did = (_text(el, "헌재결정례일련번호") or "").strip()
            if not did:
                continue
            hits.append(
                ConstitutionalHit(
                    decision_id=did,
                    case_number=(_text(el, "사건번호") or "").strip(),
                    case_name=(_text(el, "사건명") or "").strip(),
                    decision_date=(_text(el, "종국일자") or "").strip(),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_constitutional_decision_detail(
        self, decision_id: str
    ) -> ConstitutionalFull | None:
        key = make_key("law_api.get_constitutional_decision_detail", id=decision_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "detc", "ID": decision_id, "type": "XML"},
            endpoint="service",
        )
        did = (_text(root, ".//헌재결정례일련번호") or "").strip()
        if not did:
            return None
        detail = ConstitutionalFull(
            decision_id=did,
            case_number=(_text(root, ".//사건번호") or "").strip(),
            case_name=(_text(root, ".//사건명") or "").strip(),
            decision_date=(_text(root, ".//종국일자") or "").strip(),
            case_type=(_text(root, ".//사건종류명") or "").strip(),
            holding=(_text(root, ".//판시사항") or "").strip(),
            summary=(_text(root, ".//결정요지") or "").strip(),
            full_text=(_text(root, ".//전문") or "").strip(),
            related_laws=(_text(root, ".//참조조문") or "").strip(),
            related_precedents=(_text(root, ".//참조판례") or "").strip(),
            target_laws=(_text(root, ".//심판대상조문") or "").strip(),
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    # ---------------------------------------------------------------
    # 행정규칙 (admrul)
    # ---------------------------------------------------------------
    async def search_admrules(
        self, query: str, max_results: int = 5
    ) -> list[AdmRuleHit]:
        key = make_key("law_api.search_admrules", query=query, max_results=max_results)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "admrul",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[AdmRuleHit] = []
        for el in root.findall(".//admrul"):
            rid = (_text(el, "행정규칙일련번호") or "").strip()
            if not rid:
                continue
            hits.append(
                AdmRuleHit(
                    rule_id=rid,
                    rule_name=(_text(el, "행정규칙명") or "").strip(),
                    rule_type=(_text(el, "행정규칙종류") or "").strip(),
                    issued_date=(_text(el, "발령일자") or "").strip(),
                    issued_number=(_text(el, "발령번호") or "").strip(),
                    agency=(_text(el, "소관부처명") or "").strip(),
                    enforcement_date=(_text(el, "시행일자") or "").strip(),
                    is_current=(_text(el, "현행연혁구분") or "").strip(),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_admrule_detail(self, rule_id: str) -> AdmRuleFull | None:
        key = make_key("law_api.get_admrule_detail", id=rule_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "admrul", "ID": rule_id, "type": "XML"}, endpoint="service"
        )
        basic = root.find(".//행정규칙기본정보")
        if basic is None:
            return None
        rid = (_text(basic, "행정규칙일련번호") or "").strip()
        if not rid:
            return None
        articles: list[str] = []
        for el in root.findall(".//조문내용"):
            if el.text and el.text.strip():
                articles.append(el.text.strip())
        detail = AdmRuleFull(
            rule_id=rid,
            rule_name=(_text(basic, "행정규칙명") or "").strip(),
            rule_type=(_text(basic, "행정규칙종류") or "").strip(),
            issued_date=(_text(basic, "발령일자") or "").strip(),
            issued_number=(_text(basic, "발령번호") or "").strip(),
            agency=(_text(basic, "소관부처명") or "").strip(),
            department=(_text(basic, "담당부서기관명") or "").strip(),
            enforcement_date=(_text(basic, "시행일자") or "").strip(),
            articles=articles,
            amendment_reason=(_text(root, ".//제개정이유") or "").strip(),
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    # ---------------------------------------------------------------
    # 자치법규 (ordin)
    # ---------------------------------------------------------------
    async def search_ordinances(
        self, query: str, region: str | None = None, max_results: int = 5
    ) -> list[OrdinanceHit]:
        key = make_key(
            "law_api.search_ordinances",
            query=query,
            region=region,
            max_results=max_results,
        )
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "ordin",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[OrdinanceHit] = []
        for el in root.findall(".//law"):
            oid = (_text(el, "자치법규ID") or "").strip()
            if not oid:
                continue
            local_gov = (_text(el, "지자체기관명") or "").strip()
            if region and region not in local_gov:
                continue
            hits.append(
                OrdinanceHit(
                    ordinance_id=oid,
                    ordinance_serial=(_text(el, "자치법규일련번호") or "").strip(),
                    ordinance_name=(_text(el, "자치법규명") or "").strip(),
                    local_gov=local_gov,
                    ordinance_type=(_text(el, "자치법규종류") or "").strip(),
                    promulgation_date=(_text(el, "공포일자") or "").strip(),
                    enforcement_date=(_text(el, "시행일자") or "").strip(),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_ordinance_detail(self, ordinance_id: str) -> OrdinanceFull | None:
        key = make_key("law_api.get_ordinance_detail", id=ordinance_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "ordin", "ID": ordinance_id, "type": "XML"},
            endpoint="service",
        )
        basic = root.find(".//자치법규기본정보")
        if basic is None:
            return None
        oid = (_text(basic, "자치법규ID") or "").strip() or ordinance_id
        articles: list[OrdinanceArticle] = []
        for jo in root.findall(".//조문/조"):
            num = (_text(jo, "조번호") or "").strip()
            title = (_text(jo, "조제목") or "").strip()
            content = (_text(jo, "조내용") or "").strip()
            if not (num or title or content):
                continue
            articles.append(
                OrdinanceArticle(
                    article_number=num,
                    article_title=title,
                    article_text=content,
                )
            )
        detail = OrdinanceFull(
            ordinance_id=oid,
            ordinance_serial=(_text(basic, "자치법규일련번호") or "").strip(),
            ordinance_name=(_text(basic, "자치법규명") or "").strip(),
            local_gov=(_text(basic, "지자체기관명") or "").strip(),
            ordinance_type=(_text(basic, "자치법규종류") or "").strip(),
            promulgation_date=(_text(basic, "공포일자") or "").strip(),
            enforcement_date=(_text(basic, "시행일자") or "").strip(),
            department=(_text(basic, "담당부서명") or "").strip(),
            amendment_type=(_text(basic, "제개정정보") or "").strip(),
            articles=articles,
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    # ---------------------------------------------------------------
    # 조약 (trty)
    # ---------------------------------------------------------------
    async def search_treaties(
        self, query: str, max_results: int = 5
    ) -> list[TreatyHit]:
        key = make_key("law_api.search_treaties", query=query, max_results=max_results)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {
                "target": "trty",
                "type": "XML",
                "query": query,
                "display": str(max_results),
            },
            endpoint="search",
        )
        hits: list[TreatyHit] = []
        for el in root.findall(".//Trty"):
            tid = (_text(el, "조약일련번호") or "").strip()
            if not tid:
                continue
            hits.append(
                TreatyHit(
                    treaty_id=tid,
                    treaty_name=(_text(el, "조약명") or "").strip(),
                    treaty_type=(_text(el, "조약구분명") or "").strip(),
                    effective_date=(_text(el, "발효일자") or "").strip(),
                    signed_date=(_text(el, "서명일자") or "").strip(),
                    treaty_number=(_text(el, "조약번호") or "").strip(),
                )
            )
        await self._cache.set(key, hits)
        return hits

    async def get_treaty_detail(self, treaty_id: str) -> TreatyFull | None:
        key = make_key("law_api.get_treaty_detail", id=treaty_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return cached

        root = await self._get_xml(
            {"target": "trty", "ID": treaty_id, "type": "XML"}, endpoint="service"
        )
        basic = root.find(".//조약기본정보")
        if basic is None:
            return None
        tid = (_text(basic, "조약일련번호") or "").strip()
        if not tid:
            return None
        extra = root.find(".//추가정보")
        content_el = root.find(".//조약내용/조약내용")
        content = (content_el.text or "").strip() if content_el is not None else ""
        detail = TreatyFull(
            treaty_id=tid,
            treaty_name_ko=(_text(basic, "조약명_한글") or _text(basic, "조약명") or "").strip(),
            treaty_name_en=(_text(basic, "조약명_영문") or "").strip(),
            treaty_type=(_text(basic, "조약구분명") or "").strip(),
            treaty_number=(_text(basic, "조약번호") or "").strip(),
            effective_date=(_text(basic, "발효일자") or "").strip(),
            signed_date=(_text(basic, "서명일자") or "").strip(),
            category=(_text(extra, "다자조약분야명") or "").strip() if extra is not None else "",
            depositary=(_text(extra, "기탁처") or "").strip() if extra is not None else "",
            content=content,
        )
        await self._cache.set(key, detail, ttl_seconds=7 * 24 * 3600)
        return detail

    async def warmup(self) -> None:
        async def _one(name: str) -> None:
            try:
                await self.search_laws(name, max_results=1)
            except Exception as exc:  # noqa: BLE001
                logger.warning("warmup failed for %s: %s", name, exc)

        await asyncio.gather(*(_one(n) for n in WARMUP_LAWS))

    async def ping(self) -> bool:
        # Try several short queries; succeed if ANY returns. Avoids flaky
        # single-query false negatives in environments with intermittent
        # network to law.go.kr (observed on EKS).
        for query in ("민법", "공동주택관리법", "주택법"):
            try:
                await self.search_laws(query, max_results=1)
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning("ping query %r failed: %r", query, exc)
        return False


def _text(el: etree._Element, path: str) -> str | None:
    if el is None:
        return None
    node = el.find(path)
    if node is None or node.text is None:
        return None
    return node.text
