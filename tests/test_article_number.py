from kor_legal_mcp.clients.article_number import article_matches, normalize_article_number


def test_normalize_basic():
    assert normalize_article_number("제20조") == "제20조"
    assert normalize_article_number("20조") == "제20조"
    assert normalize_article_number("제20") == "제20조"
    assert normalize_article_number("20") == "제20조"


def test_normalize_sub():
    assert normalize_article_number("제20조의2") == "제20조의2"
    assert normalize_article_number("20-2") == "제20조의2"
    assert normalize_article_number("제20-2") == "제20조의2"


def test_normalize_invalid():
    assert normalize_article_number("") is None
    assert normalize_article_number("abc") is None


def test_matches():
    assert article_matches("20조", "제20조")
    assert article_matches("제20-2", "제20조의2")
    assert not article_matches("제20조", "제21조")
