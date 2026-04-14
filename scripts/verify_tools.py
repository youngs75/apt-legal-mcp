"""End-to-end verification of every MCP Tool handler.

Calls each tool with realistic inputs (mirroring what the LLM would send
for the 재건축/입찰 scenario) and prints the result OR full traceback.
This catches handler-level bugs that don't surface in verify_law_api.py.
"""
from __future__ import annotations

import asyncio
import json
import traceback

from kor_legal_mcp.cache.memory_cache import MemoryCache
from kor_legal_mcp.clients.law_api import LawApiClient
from kor_legal_mcp.config import settings
from kor_legal_mcp.tools import (
    compare_laws,
    get_admrule_detail,
    get_constitutional_decision_detail,
    get_interpretation_detail,
    get_law_article,
    get_ordinance_detail,
    get_precedent_detail,
    get_treaty_detail,
    search_admrule,
    search_constitutional_decision,
    search_interpretation,
    search_law,
    search_ordinance,
    search_precedent,
    search_treaty,
)
from kor_legal_mcp.tools._common import ToolContext


def _dump(obj) -> str:
    if hasattr(obj, "model_dump"):
        return json.dumps(obj.model_dump(), ensure_ascii=False, indent=2)[:1200]
    return str(obj)[:1200]


async def run(label: str, coro):
    print(f"\n=== {label} ===")
    try:
        result = await coro
        print("OK")
        print(_dump(result))
    except Exception as exc:
        print(f"FAIL [{type(exc).__name__}]: {exc!r}")
        traceback.print_exc()


async def main() -> None:
    print(f"LAW_API_KEY={settings.law_api_key!r}")
    cache = MemoryCache(
        max_items=settings.cache_max_items,
        default_ttl_seconds=settings.cache_ttl_hours * 3600,
    )
    law_api = LawApiClient(cache=cache)
    ctx = ToolContext(law_api=law_api, cache=cache)

    try:
        await run(
            "search_law(층간소음)",
            search_law.handle(ctx, {"query": "층간소음", "max_results": 3}),
        )

        await run(
            "search_law(입주자대표회의 의결 관리업체 선정)",
            search_law.handle(
                ctx,
                {
                    "query": "입주자대표회의 의결 관리업체 선정",
                    "max_results": 5,
                },
            ),
        )

        await run(
            "get_law_article(공동주택관리법, 제20조)",
            get_law_article.handle(
                ctx,
                {
                    "law_name": "공동주택관리법",
                    "article_number": "제20조",
                    "include_history": False,
                },
            ),
        )

        await run(
            "get_law_article(공동주택관리법, 제25조)",
            get_law_article.handle(
                ctx,
                {
                    "law_name": "공동주택관리법",
                    "article_number": "제25조",
                    "include_history": False,
                },
            ),
        )

        await run(
            "search_precedent(층간소음)",
            search_precedent.handle(
                ctx, {"query": "층간소음", "max_results": 3}
            ),
        )

        await run(
            "search_precedent(입주자대표회의 입찰 절차 위반)",
            search_precedent.handle(
                ctx,
                {
                    "query": "입주자대표회의 주택관리업자 선정 입찰 절차 위반",
                    "max_results": 3,
                },
            ),
        )

        await run(
            "get_precedent_detail(2021마6763)",
            get_precedent_detail.handle(ctx, {"case_number": "2021마6763"}),
        )

        await run(
            "search_interpretation(공동주택 층간소음)",
            search_interpretation.handle(
                ctx, {"query": "공동주택 층간소음", "max_results": 3}
            ),
        )

        await run(
            "compare_laws(공동주택관리법 제20조 vs 주택법 제35조)",
            compare_laws.handle(
                ctx,
                {
                    "comparisons": [
                        {"law_name": "공동주택관리법", "article_number": "제20조"},
                        {"law_name": "주택법", "article_number": "제35조"},
                    ]
                },
            ),
        )

        # --- 신규 tool 회귀 ---
        # search → detail 체인: search에서 첫 hit의 id를 detail에 전달
        interp_hits = await ctx.law_api.search_interpretations(
            query="공동주택", max_results=1
        )
        if interp_hits:
            await run(
                f"get_interpretation_detail({interp_hits[0].interpretation_id})",
                get_interpretation_detail.handle(
                    ctx, {"interpretation_id": interp_hits[0].interpretation_id}
                ),
            )
        else:
            print("\n=== get_interpretation_detail skipped (no hits) ===")

        await run(
            "search_constitutional_decision(집회)",
            search_constitutional_decision.handle(
                ctx, {"query": "집회", "max_results": 3}
            ),
        )
        detc_hits = await ctx.law_api.search_constitutional_decisions(
            query="집회", max_results=1
        )
        if detc_hits:
            # pick one with populated content — search first 5 and test each
            detc_hits5 = await ctx.law_api.search_constitutional_decisions(
                query="집회", max_results=5
            )
            for h in detc_hits5:
                await run(
                    f"get_constitutional_decision_detail({h.decision_id})",
                    get_constitutional_decision_detail.handle(
                        ctx, {"decision_id": h.decision_id}
                    ),
                )
                break

        await run(
            "search_admrule(공동주택관리)",
            search_admrule.handle(
                ctx, {"query": "공동주택관리", "max_results": 3}
            ),
        )
        admrul_hits = await ctx.law_api.search_admrules(
            query="공동주택관리", max_results=1
        )
        if admrul_hits:
            await run(
                f"get_admrule_detail({admrul_hits[0].rule_id})",
                get_admrule_detail.handle(
                    ctx, {"rule_id": admrul_hits[0].rule_id}
                ),
            )

        await run(
            "search_ordinance(주차장, 서울특별시)",
            search_ordinance.handle(
                ctx,
                {"query": "주차장", "region": "서울특별시", "max_results": 3},
            ),
        )
        ordin_hits = await ctx.law_api.search_ordinances(
            query="주차장", max_results=1
        )
        if ordin_hits:
            await run(
                f"get_ordinance_detail({ordin_hits[0].ordinance_id})",
                get_ordinance_detail.handle(
                    ctx, {"ordinance_id": ordin_hits[0].ordinance_id}
                ),
            )

        await run(
            "search_treaty(항공)",
            search_treaty.handle(ctx, {"query": "항공", "max_results": 3}),
        )
        trty_hits = await ctx.law_api.search_treaties(
            query="항공", max_results=1
        )
        if trty_hits:
            await run(
                f"get_treaty_detail({trty_hits[0].treaty_id})",
                get_treaty_detail.handle(
                    ctx, {"treaty_id": trty_hits[0].treaty_id}
                ),
            )
    finally:
        await law_api.__aexit__(None, None, None)


if __name__ == "__main__":
    asyncio.run(main())
