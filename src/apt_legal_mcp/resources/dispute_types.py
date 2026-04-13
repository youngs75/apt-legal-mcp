from __future__ import annotations

DISPUTE_TYPES: list[dict[str, object]] = [
    {
        "code": "NOISE",
        "label": "층간소음",
        "primary_laws": ["공동주택관리법 제20조", "민법 제217조"],
    },
    {
        "code": "PARKING",
        "label": "주차 분쟁",
        "primary_laws": ["공동주택관리법 제35조", "도로교통법"],
    },
    {
        "code": "PET",
        "label": "반려동물",
        "primary_laws": ["공동주택관리법 제18조", "동물보호법"],
    },
    {
        "code": "MGMT_FEE",
        "label": "관리비",
        "primary_laws": ["공동주택관리법 제23조"],
    },
    {
        "code": "DEFECT",
        "label": "하자보수",
        "primary_laws": ["공동주택관리법 제36조", "민법 제667조"],
    },
    {
        "code": "RECON",
        "label": "재건축",
        "primary_laws": ["도시 및 주거환경정비법", "주택법"],
    },
    {
        "code": "REMODEL",
        "label": "리모델링",
        "primary_laws": ["주택법 제66조"],
    },
    {
        "code": "BID",
        "label": "입찰/계약",
        "primary_laws": ["공동주택관리법 제25조"],
    },
    {
        "code": "ELECTION",
        "label": "대표회의 선거",
        "primary_laws": ["공동주택관리법 제14조"],
    },
    {
        "code": "GENERAL",
        "label": "기타 법률 질의",
        "primary_laws": [],
    },
]
