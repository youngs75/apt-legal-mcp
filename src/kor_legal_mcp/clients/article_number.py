from __future__ import annotations

import re

_ARTICLE_RE = re.compile(
    r"^\s*제?\s*(?P<main>\d+)\s*조?(?:\s*(?:의|[-－])\s*(?P<sub>\d+))?\s*$"
)


def normalize_article_number(raw: str) -> str | None:
    """Return canonical form like '제20조' or '제20조의2'.

    Accepts: '제20조', '20조', '제20', '20', '제20조의2', '20-2', '제20-2'.
    """
    if not raw:
        return None
    m = _ARTICLE_RE.match(raw)
    if not m:
        return None
    main = m.group("main")
    sub = m.group("sub")
    if sub:
        return f"제{main}조의{sub}"
    return f"제{main}조"


def article_matches(candidate: str, target: str) -> bool:
    c = normalize_article_number(candidate)
    t = normalize_article_number(target)
    return c is not None and c == t
