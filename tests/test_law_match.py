"""Tests for LawApiClient._best_law_match — exact > shortest substring > fallback."""

from kor_legal_mcp.clients.law_api import LawApiClient, LawSearchHit


def _hit(name: str, mst: str = "0") -> LawSearchHit:
    return LawSearchHit(law_name=name, mst=mst, enforcement_date=None, last_amended=None)


def test_exact_match_preferred():
    hits = [
        _hit("동물보호법 시행령", "1"),
        _hit("동물보호법", "2"),
        _hit("동물보호법 시행규칙", "3"),
    ]
    result = LawApiClient._best_law_match("동물보호법", hits)
    assert result is not None
    assert result.law_name == "동물보호법"


def test_shortest_substring_when_no_exact():
    hits = [
        _hit("공동주택관리법 시행령", "1"),
        _hit("공동주택관리법 시행규칙", "2"),
        _hit("공동주택관리법", "3"),
    ]
    result = LawApiClient._best_law_match("공동주택관리법", hits)
    assert result is not None
    assert result.law_name == "공동주택관리법"


def test_substring_prefers_shortest():
    """When query is a prefix, pick the shortest matching name (본법)."""
    hits = [
        _hit("민법 시행법", "1"),
        _hit("민법 시행규칙", "2"),
    ]
    result = LawApiClient._best_law_match("민법", hits)
    assert result is not None
    assert result.law_name == "민법 시행법"  # shorter


def test_fallback_to_first_when_no_substring():
    hits = [_hit("전혀다른법", "1")]
    result = LawApiClient._best_law_match("동물보호법", hits)
    assert result is not None
    assert result.law_name == "전혀다른법"


def test_empty_hits():
    assert LawApiClient._best_law_match("동물보호법", []) is None
