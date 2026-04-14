from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route

from kor_legal_mcp import __version__
from kor_legal_mcp.cache.memory_cache import MemoryCache
from kor_legal_mcp.clients.law_api import LawApiClient
from kor_legal_mcp.config import settings
from kor_legal_mcp.tools import (
    compare_laws,
    get_law_article,
    get_precedent_detail,
    search_interpretation,
    search_law,
    search_precedent,
)
from kor_legal_mcp.tools._common import ToolContext

logger = logging.getLogger(__name__)

SERVER_NAME = "kor-legal-mcp"


def _build_context() -> ToolContext:
    cache = MemoryCache(
        max_items=settings.cache_max_items,
        default_ttl_seconds=settings.cache_ttl_hours * 3600,
    )
    law_api = LawApiClient(cache=cache)
    return ToolContext(law_api=law_api, cache=cache)


def _json_dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def build_mcp(ctx: ToolContext | None = None) -> tuple[FastMCP, ToolContext]:
    ctx = ctx or _build_context()
    # FastMCP defaults to DNS-rebinding protection that only allows loopback
    # Host headers. We deploy behind an HTTPS reverse proxy (Samsung SDS CoE
    # portal), so the protection is unnecessary and blocks all real traffic
    # with 421 Misdirected Request. Disable it.
    mcp = FastMCP(
        SERVER_NAME,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )

    @mcp.tool(
        name="search_law",
        description="키워드 기반으로 한국 법령 조문을 검색합니다.",
    )
    async def _search_law(
        query: str,
        law_name: str | None = None,
        max_results: int = 5,
    ) -> str:
        output = await search_law.handle(
            ctx, {"query": query, "law_name": law_name, "max_results": max_results}
        )
        return _json_dump(output.model_dump())

    @mcp.tool(
        name="get_law_article",
        description="특정 법령의 조문 전문을 조회합니다.",
    )
    async def _get_law_article(
        law_name: str,
        article_number: str,
        include_history: bool = False,
    ) -> str:
        try:
            output = await get_law_article.handle(
                ctx,
                {
                    "law_name": law_name,
                    "article_number": article_number,
                    "include_history": include_history,
                },
            )
        except get_law_article.ArticleNotFound as exc:
            return _json_dump({"error": "LAW_NOT_FOUND", "message": str(exc)})
        return _json_dump(output.model_dump())

    @mcp.tool(
        name="search_precedent",
        description="키워드 기반으로 관련 판례를 검색합니다.",
    )
    async def _search_precedent(
        query: str,
        court_level: str | None = None,
        max_results: int = 5,
    ) -> str:
        output = await search_precedent.handle(
            ctx,
            {
                "query": query,
                "court_level": court_level,
                "max_results": max_results,
            },
        )
        return _json_dump(output.model_dump())

    @mcp.tool(
        name="get_precedent_detail",
        description="판례 상세 정보를 조회합니다. 사건번호 또는 판례일련번호로 검색합니다.",
    )
    async def _get_precedent_detail(case_number: str) -> str:
        try:
            output = await get_precedent_detail.handle(ctx, {"case_number": case_number})
        except get_precedent_detail.PrecedentNotFound as exc:
            return _json_dump({"error": "PRECEDENT_NOT_FOUND", "message": str(exc)})
        return _json_dump(output.model_dump())

    @mcp.tool(
        name="search_interpretation",
        description="행정해석·유권해석을 검색합니다 (현 단계에서는 연동 대기).",
    )
    async def _search_interpretation(
        query: str,
        source: str | None = None,
        max_results: int = 5,
    ) -> str:
        output = await search_interpretation.handle(
            ctx,
            {"query": query, "source": source, "max_results": max_results},
        )
        return _json_dump(output.model_dump())

    @mcp.tool(
        name="compare_laws",
        description="두 개 이상의 법령 조문을 나란히 비교 조회합니다.",
    )
    async def _compare_laws(
        comparisons: list[dict],
        focus: str | None = None,
    ) -> str:
        output = await compare_laws.handle(
            ctx, {"comparisons": comparisons, "focus": focus}
        )
        return _json_dump(output.model_dump())

    @mcp.resource("kor-legal://law/{law_name}/article/{article_number}")
    async def _law_article_resource(law_name: str, article_number: str) -> str:
        try:
            output = await get_law_article.handle(
                ctx,
                {
                    "law_name": law_name,
                    "article_number": article_number,
                    "include_history": False,
                },
            )
        except get_law_article.ArticleNotFound as exc:
            return f"[오류] {exc}"
        return f"{output.law_name} {output.article_number} {output.article_title}\n\n{output.full_text}"

    @mcp.resource("kor-legal://precedent/{case_number}")
    async def _precedent_resource(case_number: str) -> str:
        try:
            output = await get_precedent_detail.handle(ctx, {"case_number": case_number})
        except get_precedent_detail.PrecedentNotFound as exc:
            return f"[오류] {exc}"
        return _json_dump(output.model_dump())

    return mcp, ctx


async def _healthz(_request: Request) -> JSONResponse:
    ok = await _CTX.law_api.ping()
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "components": {"law_api": "ok" if ok else "unavailable"},
        }
    )


async def _root(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "name": SERVER_NAME,
            "version": __version__,
            "description": "한국 법령·판례·행정해석 조회 범용 MCP 서버",
            "endpoints": {"mcp": "/mcp", "health": "/healthz"},
        }
    )


_MCP, _CTX = build_mcp()
_INNER_MCP_APP = _MCP.streamable_http_app()


@asynccontextmanager
async def _lifespan(app: Starlette):
    # Delegate to the inner FastMCP app's lifespan first — it starts the
    # StreamableHTTPSessionManager task group. Without this the /mcp route
    # raises "Task group is not initialized" on every request.
    async with _INNER_MCP_APP.router.lifespan_context(app):
        try:
            await asyncio.wait_for(_CTX.law_api.warmup(), timeout=10)
        except Exception as exc:  # noqa: BLE001
            logger.warning("warmup skipped: %s", exc)
        try:
            yield
        finally:
            await _CTX.law_api.__aexit__(None, None, None)


app = Starlette(
    routes=[
        Route("/", _root),
        Route("/healthz", _healthz),
        # FastMCP's streamable_http_app() already exposes /mcp internally;
        # mount it at root so its /mcp route is reachable directly without
        # double-prefixing (which would cause a 307 redirect).
        Mount("/", app=_INNER_MCP_APP),
    ],
    lifespan=_lifespan,
)
