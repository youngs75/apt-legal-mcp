from kor_legal_mcp.tools._common import (
    extract_keywords,
    normalize_query,
    score_relevance,
    snippet_around,
    truncate,
)


def test_normalize_query():
    assert normalize_query("  층간  소음  ") == "층간 소음"


def test_extract_keywords_strips_josa():
    kws = extract_keywords("층간소음으로 손해배상을 청구")
    assert "층간소음" in kws
    assert "손해배상" in kws


def test_score_relevance():
    assert score_relevance("층간 소음", "층간 소음이 심하다") == 1.0
    assert score_relevance("층간 소음", "주차 분쟁") == 0.0


def test_snippet_around():
    text = "가" * 100 + "층간소음" + "나" * 100
    s = snippet_around(text, "층간소음", window=10)
    assert "층간소음" in s
    assert s.startswith("...")


def test_truncate():
    assert truncate("abc") == "abc"
    assert truncate("a" * 300, limit=10).endswith("…")
