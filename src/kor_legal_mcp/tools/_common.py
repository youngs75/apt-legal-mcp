from __future__ import annotations

import re
from dataclasses import dataclass

from kor_legal_mcp.cache.memory_cache import MemoryCache
from kor_legal_mcp.clients.law_api import LawApiClient


@dataclass
class ToolContext:
    law_api: LawApiClient
    cache: MemoryCache


_JOSA_SUFFIX = re.compile(
    r"(은|는|이|가|을|를|에|의|와|과|로|으로|에서|부터|까지|도|만|에게|께|이나|나)$"
)


def normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query).strip()


def extract_keywords(query: str) -> list[str]:
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    out: list[str] = []
    for t in tokens:
        stripped = _JOSA_SUFFIX.sub("", t)
        if stripped and stripped not in out:
            out.append(stripped)
    return out


def score_relevance(query: str, text: str) -> float:
    keywords = extract_keywords(query)
    if not keywords or not text:
        return 0.0
    hits = sum(1 for kw in keywords if kw and kw in text)
    return round(hits / len(keywords), 3)


def snippet_around(text: str, query: str, window: int = 80) -> str:
    if not text:
        return ""
    keywords = extract_keywords(query)
    for kw in keywords:
        idx = text.find(kw)
        if idx >= 0:
            start = max(0, idx - window)
            end = min(len(text), idx + len(kw) + window)
            prefix = "..." if start > 0 else ""
            suffix = "..." if end < len(text) else ""
            return f"{prefix}{text[start:end]}{suffix}"
    return text[: window * 2] + ("..." if len(text) > window * 2 else "")


def truncate(text: str, limit: int = 200) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
