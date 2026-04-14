"""Quick verification of LAW_API_KEY (OC param) against law.go.kr."""
from __future__ import annotations

import asyncio
import sys
import traceback

import httpx

from kor_legal_mcp.clients.law_api import WARMUP_LAWS, LawApiClient
from kor_legal_mcp.config import settings


async def raw_search(oc: str) -> None:
    print(f"\n[1] Raw lawSearch.do call (OC={oc})")
    url = "http://www.law.go.kr/DRF/lawSearch.do"
    params = {"OC": oc, "target": "law", "type": "XML", "query": "공동주택관리법", "display": "3"}
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.get(url, params=params)
        print(f"  status={r.status_code} len={len(r.content)}")
        print(f"  preview={r.text[:400]}")


async def via_client() -> None:
    print(
        f"\n[2] LawApiClient.search_laws "
        f"(search_url={settings.law_api_search_url})"
    )
    async with LawApiClient() as client:
        try:
            hits = await client.search_laws("공동주택관리법", max_results=3)
            print(f"  hits={len(hits)}")
            for h in hits:
                print(f"   - {h.law_name} (mst={h.mst}, 시행={h.enforcement_date})")
            if hits:
                print(f"\n[3] LawApiClient.get_law_detail(mst={hits[0].mst})")
                articles = await client.get_law_detail(hits[0].mst)
                print(f"  articles={len(articles)}")
                for art in articles[:3]:
                    print(f"   - {art.article_number} {art.article_title}")
                print(f"\n[4] LawApiClient.search_precedents('층간소음')")
                precs = await client.search_precedents("층간소음", max_results=3)
                print(f"  precedents={len(precs)}")
                for p in precs:
                    print(f"   - {p.case_number} {p.case_name} ({p.court}, {p.date})")
        except Exception as exc:
            print(f"  ERROR: {exc!r}")


async def reproduce_warmup() -> None:
    print(f"\n[5] Reproduce warmup (concurrent gather over {len(WARMUP_LAWS)} laws)")
    async with LawApiClient() as client:
        async def _one(name: str) -> tuple[str, str]:
            try:
                hits = await client.search_laws(name, max_results=1)
                return name, f"OK ({len(hits)} hits)"
            except Exception as exc:
                return name, f"FAIL [{type(exc).__name__}] {exc!r}"

        results = await asyncio.gather(*(_one(n) for n in WARMUP_LAWS))
        for name, status in results:
            print(f"  - {name}: {status}")


async def reproduce_warmup_sequential() -> None:
    print(f"\n[6] Sequential (no concurrency) over same {len(WARMUP_LAWS)} laws")
    async with LawApiClient() as client:
        for name in WARMUP_LAWS:
            try:
                hits = await client.search_laws(name, max_results=1)
                print(f"  - {name}: OK ({len(hits)} hits)")
            except Exception as exc:
                print(f"  - {name}: FAIL [{type(exc).__name__}] {exc!r}")


async def ping_check() -> None:
    print("\n[7] LawApiClient.ping()")
    async with LawApiClient() as client:
        ok = await client.ping()
        print(f"  ping={ok}")


async def main() -> None:
    print(f"LAW_API_KEY={settings.law_api_key!r}")
    if not settings.law_api_key:
        print("ERROR: LAW_API_KEY not set")
        sys.exit(1)
    await raw_search(settings.law_api_key)
    await via_client()
    await reproduce_warmup()
    await reproduce_warmup_sequential()
    await ping_check()


if __name__ == "__main__":
    asyncio.run(main())
