"""Quick verification of LAW_API_KEY (OC param) against law.go.kr."""
from __future__ import annotations

import asyncio
import sys

import httpx

from kor_legal_mcp.clients.law_api import LawApiClient
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


async def main() -> None:
    print(f"LAW_API_KEY={settings.law_api_key!r}")
    if not settings.law_api_key:
        print("ERROR: LAW_API_KEY not set")
        sys.exit(1)
    await raw_search(settings.law_api_key)
    await via_client()


if __name__ == "__main__":
    asyncio.run(main())
