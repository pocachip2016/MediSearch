"""tests/test_playwright_integration.py — PlaywrightProvider 실제 크롤링 통합 테스트.

실행:
    pytest tests/test_playwright_integration.py -v -m integration

CI skip:
    pytest -m "not integration"
"""
import pytest

from search.playwright_provider import PlaywrightProvider


PROVIDER = PlaywrightProvider(headless=True, timeout_ms=20000)

MOVIES = [
    "기생충",
    "설국열차",
    "아가씨",
]


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("movie", MOVIES)
async def test_crawl_returns_result(movie: str):
    """각 영화에 대해 SourceDocument 1개 이상 반환."""
    results = await PROVIDER.search(movie, num=5)
    assert len(results) >= 1, f"{movie!r}: 결과 없음"


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.parametrize("movie", MOVIES)
async def test_crawl_result_fields(movie: str):
    """반환 문서의 필수 필드 검증."""
    results = await PROVIDER.search(movie, num=5)
    assert results, f"{movie!r}: 결과 없음"
    doc = results[0]

    assert doc.title, f"{movie!r}: title 비어 있음"
    assert "namu.wiki" in doc.url, f"{movie!r}: URL에 namu.wiki 없음 — {doc.url!r}"
    assert len(doc.text) >= 20, f"{movie!r}: text 너무 짧음 ({len(doc.text)}자)"
    assert 0 < doc.trust_score <= 1.0, f"{movie!r}: trust_score 범위 오류"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crawl_movie_title_in_result():
    """기생충 검색 시 반환 title에 '기생충' 포함."""
    results = await PROVIDER.search("기생충", num=5)
    assert results
    assert "기생충" in results[0].title


@pytest.mark.integration
@pytest.mark.asyncio
async def test_crawl_unknown_movie_returns_empty_or_result():
    """존재하지 않는 영화 — 빈 리스트 또는 관련 없는 페이지 반환 (에러 없어야 함)."""
    results = await PROVIDER.search("xyznonexistentmovie12345", num=5)
    # 결과가 없거나 있어도 예외 없이 처리
    assert isinstance(results, list)
