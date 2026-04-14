"""Probe law.go.kr API response structure for new targets.

Dumps search + detail XML for: expc, detc, admrul, ordin, trty.
Output goes to ./probe_out/ as raw .xml files for offline inspection.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import httpx

OC = os.environ.get("LAW_API_KEY", "apt-legal-agent")
SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"

OUT = Path(__file__).parent.parent / "probe_out"
OUT.mkdir(exist_ok=True)


async def fetch(client: httpx.AsyncClient, url: str, params: dict) -> bytes:
    params = {"OC": OC, **params}
    resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.content


async def probe_target(
    client: httpx.AsyncClient,
    target: str,
    query: str,
    id_field: str = "ID",
    detail_id_extractor=None,
) -> None:
    print(f"\n=== target={target} query={query} ===")
    # 1. search
    try:
        search_xml = await fetch(
            client,
            SEARCH_URL,
            {"target": target, "type": "XML", "query": query, "display": "3"},
        )
        (OUT / f"{target}_search.xml").write_bytes(search_xml)
        print(f"  search: {len(search_xml)} bytes → {target}_search.xml")
    except Exception as exc:
        print(f"  search FAILED: {type(exc).__name__}: {exc}")
        return

    # 2. detail for first hit — try to extract a usable id from XML
    from lxml import etree
    try:
        root = etree.fromstring(search_xml)
    except etree.XMLSyntaxError as exc:
        print(f"  search XML parse failed: {exc}")
        return

    # Print top-level tag names for manual inspection
    items = list(root)
    print(f"  root tag: {root.tag}, children: {[c.tag for c in items[:5]]}")
    if items:
        first = None
        # Find the first item-like child (not totalCnt/section/etc.)
        for c in items:
            if len(c) > 0:
                first = c
                break
        if first is not None:
            print(f"  first item fields: {[ch.tag for ch in first]}")
            # Try to extract ID using common field names
            id_val = None
            for candidate in (
                "판례일련번호", "해석일련번호", "법령해석일련번호",
                "행정규칙일련번호", "결정례일련번호", "헌재결정일련번호",
                "자치법규일련번호", "조약일련번호", "ID", "id",
                "법령ID", "MST",
            ):
                el = first.find(candidate)
                if el is not None and el.text:
                    id_val = el.text.strip()
                    print(f"  extracted id from <{candidate}>: {id_val}")
                    break
            if id_val:
                try:
                    detail_xml = await fetch(
                        client,
                        SERVICE_URL,
                        {"target": target, id_field: id_val, "type": "XML"},
                    )
                    (OUT / f"{target}_detail.xml").write_bytes(detail_xml)
                    print(f"  detail: {len(detail_xml)} bytes → {target}_detail.xml")
                    dr = etree.fromstring(detail_xml)
                    print(f"  detail root: {dr.tag}, children: {[c.tag for c in dr[:10]]}")
                except Exception as exc:
                    print(f"  detail FAILED: {type(exc).__name__}: {exc}")
            else:
                print(f"  no id field found in first item")


async def main() -> None:
    async with httpx.AsyncClient(timeout=20) as client:
        # expc: 법령해석례
        await probe_target(client, "expc", "공동주택", id_field="ID")
        # detc: 헌재결정례
        await probe_target(client, "detc", "공동주택", id_field="ID")
        # admrul: 행정규칙
        await probe_target(client, "admrul", "공동주택관리", id_field="ID")
        # ordin: 자치법규
        await probe_target(client, "ordin", "주차장", id_field="ID")
        # trty: 조약
        await probe_target(client, "trty", "항공", id_field="ID")


if __name__ == "__main__":
    asyncio.run(main())
