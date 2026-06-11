"""tests/test_playwright_provider.py — PlaywrightProvider 테스트 (mock Playwright)."""
from unittest.mock import AsyncMock, patch

import pytest

from search.playwright_provider import PlaywrightProvider
from search.base import SearchQuery, SourceType


def _sq(title: str) -> SearchQuery:
    return SearchQuery(title=title)


@pytest.fixture
def provider():
    return PlaywrightProvider(headless=True, timeout_ms=15000)


def test_provider_name(provider):
    assert provider.provider_name == "playwright"


def test_build_urls(provider):
    urls = provider._build_urls("기생충")
    assert len(urls) == 2
    assert "%EC%98%81%ED%99%94" in urls[0]  # 영화 인코딩 포함
    assert urls[0].startswith("https://namu.wiki/w/")


@pytest.mark.asyncio
async def test_search_success(provider):
    """유효 페이지 → SourceDocument 반환."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=AsyncMock(status=200))
    mock_page.title = AsyncMock(return_value="기생충(영화) - 나무위키")
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=[
        False,  # _DISAMBIG_JS → False (동음이의어 아님)
        "기생충(영화)",    # h1 innerText
        "봉준호 감독의 7번째 장편. 반지하 가족 이야기.",  # overview
        "전원백수 기택 가족이 부잣집에 잠입하면서...",    # synopsis
    ])
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)

    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()

    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("기생충"), num=5)

    assert len(results) == 1
    assert results[0].title == "기생충(영화)"
    assert results[0].source_domain == "namu.wiki"
    assert results[0].source_type == SourceType.synopsis
    assert results[0].trust_score == 0.85
    assert "봉준호" in results[0].text


@pytest.mark.asyncio
async def test_search_falls_back_to_second_url(provider):
    """첫 URL(영화) 에러 페이지 → 두 번째 URL 시도."""
    call_count = [0]

    async def title_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return "페이지를 찾을 수 없습니다."
        return "씬시어리티 - 나무위키"

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=AsyncMock(status=200))
    mock_page.title = AsyncMock(side_effect=title_side_effect)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=[
        False,  # _DISAMBIG_JS → False
        "씬시어리티",
        "개요 텍스트",
        "시놉시스 텍스트",
    ])
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("씬시어리티"), num=5)

    assert len(results) == 1
    assert results[0].title == "씬시어리티"


@pytest.mark.asyncio
async def test_search_all_urls_fail(provider):
    """모든 URL 에러 페이지 → 빈 리스트."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=AsyncMock(status=200))
    mock_page.title = AsyncMock(return_value="페이지를 찾을 수 없습니다.")
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("존재하지않는영화xyz"), num=5)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_timeout_returns_empty(provider):
    """goto 타임아웃 → 빈 리스트."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=TimeoutError("timeout"))
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("test"), num=5)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_search_disambig_page_finds_movie_link(provider):
    """동음이의어 페이지 → (영화) 링크 발견 → 성공."""
    call_count = [0]

    async def title_side_effect():
        call_count[0] += 1
        if call_count[0] == 1:
            return "올드보이 - 나무위키"  # 동음이의어 페이지
        return "올드보이(영화) - 나무위키"  # 영화 페이지

    async def evaluate_side_effect(js_str):
        # _DISAMBIG_JS → True (첫 호출)
        # _MOVIE_LINK_JS → movie_link (두 번째 호출)
        # 정상 페이지 h1, overview, synopsis (세 번째~ 호출)
        if "_DISAMBIG_JS" in str(js_str) or "hasOverview" in str(js_str):
            return True
        elif "_MOVIE_LINK_JS" in str(js_str) or "decodeURIComponent" in str(js_str):
            return "https://namu.wiki/w/%EC%98%AC%EB%93%9C%EB%B3%B4%EC%9D%B4(%EC%98%81%ED%99%94)"
        elif "h1" in str(js_str):
            return "올드보이(영화)"
        elif "개요" in str(js_str):
            return "2003년 박찬욱 감독의 대작."
        else:  # synopsis
            return "미스터 오 일명 오대수라는 남자가..."

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=AsyncMock(status=200))
    mock_page.title = AsyncMock(side_effect=title_side_effect)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("올드보이"), num=5)

    assert len(results) == 1
    assert results[0].title == "올드보이(영화)"
    assert "박찬욱" in results[0].text


@pytest.mark.asyncio
async def test_search_disambig_page_no_movie_link(provider):
    """동음이의어 페이지 + (영화) 링크 없음 → 빈 리스트."""
    async def title_side_effect():
        return "존재하지않는항목 - 나무위키"

    async def evaluate_side_effect(js_str):
        if "_DISAMBIG_JS" in str(js_str) or "hasOverview" in str(js_str):
            return True
        elif "_MOVIE_LINK_JS" in str(js_str) or "decodeURIComponent" in str(js_str):
            return None  # (영화) 링크 없음
        else:
            return ""

    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(return_value=AsyncMock(status=200))
    mock_page.title = AsyncMock(side_effect=title_side_effect)
    mock_page.wait_for_selector = AsyncMock()
    mock_page.evaluate = AsyncMock(side_effect=evaluate_side_effect)
    mock_page.add_init_script = AsyncMock()

    mock_context = AsyncMock()
    mock_context.new_page = AsyncMock(return_value=mock_page)
    mock_browser = AsyncMock()
    mock_browser.new_context = AsyncMock(return_value=mock_context)
    mock_browser.close = AsyncMock()
    mock_pw = AsyncMock()
    mock_pw.__aenter__ = AsyncMock(return_value=mock_pw)
    mock_pw.__aexit__ = AsyncMock(return_value=False)
    mock_pw.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_pw
        results = await provider.search(_sq("존재하지않는항목"), num=5)

    assert len(results) == 0
