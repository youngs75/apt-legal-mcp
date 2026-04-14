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
        hits = await self.search_laws(law_name, max_results=3)
        target = None
        for hit in hits:
            if law_name in hit.law_name or hit.law_name in law_name:
                target = hit
                break
        if target is None and hits:
            target = hits[0]
        if target is None:
            return None
        articles = await self.get_law_detail(target.mst)
        for art in articles:
            if article_matches(art.article_number, article_number):
                return art
        return None

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
