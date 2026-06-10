"""tests/test_playwright_provider.py — PlaywrightProvider 테스트 (mock Playwright)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from search.playwright_provider import PlaywrightProvider
from search.base import SourceType


@pytest.fixture
def provider():
    return PlaywrightProvider(headless=True, timeout_ms=10000)


@pytest.mark.asyncio
async def test_playwright_provider_name(provider):
    """provider_name 확인."""
    assert provider.provider_name == "playwright"


@pytest.mark.asyncio
async def test_playwright_provider_search_success(provider):
    """성공적인 검색 크롤링."""
    # Mock async context manager
    async def async_none(*args, **kwargs):
        return None

    async def async_str(val):
        async def _coro():
            return val
        return await _coro()

    # Mock page
    mock_page = AsyncMock()

    # Mock items with proper async mocks
    mock_link1 = AsyncMock()
    mock_link1.get_attribute = AsyncMock(return_value="/w/기생충 (영화)")
    mock_link1.inner_text = AsyncMock(return_value="기생충 (영화)")

    mock_snippet1 = AsyncMock()
    mock_snippet1.inner_text = AsyncMock(
        return_value="봉준호 감독 2019년 작품. 칸 황금종려상 수상."
    )

    mock_item1 = AsyncMock()
    mock_item1.query_selector = AsyncMock(
        side_effect=lambda x: mock_link1 if x == "a.wiki_link" else mock_snippet1
    )

    # Item 2
    mock_link2 = AsyncMock()
    mock_link2.get_attribute = AsyncMock(return_value="/w/기생충 (드라마)")
    mock_link2.inner_text = AsyncMock(return_value="기생충 (드라마)")

    mock_snippet2 = AsyncMock()
    mock_snippet2.inner_text = AsyncMock(return_value="HBO 리메이크 작품.")

    mock_item2 = AsyncMock()
    mock_item2.query_selector = AsyncMock(
        side_effect=lambda x: mock_link2 if x == "a.wiki_link" else mock_snippet2
    )

    mock_page.query_selector_all = AsyncMock(return_value=[mock_item1, mock_item2])
    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()

    # Mock browser
    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    # Mock async_playwright
    mock_playwright = AsyncMock()
    mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_playwright.__aexit__ = AsyncMock(return_value=False)
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_playwright

        results = await provider.search("기생충", num=5)

    assert len(results) == 2
    assert results[0].title == "기생충 (영화)"
    assert results[0].source_domain == "namu.wiki"
    assert results[0].trust_score == 0.85


@pytest.mark.asyncio
async def test_playwright_provider_search_empty_results(provider):
    """검색 결과 없음."""
    mock_page = AsyncMock()
    mock_page.query_selector_all = AsyncMock(return_value=[])
    mock_page.goto = AsyncMock()
    mock_page.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_playwright = AsyncMock()
    mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_playwright.__aexit__ = AsyncMock(return_value=False)
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_playwright

        results = await provider.search("존재하지않는영화", num=5)

    assert len(results) == 0


@pytest.mark.asyncio
async def test_playwright_provider_timeout_returns_empty(provider):
    """페이지 로딩 타임아웃 → 빈 결과."""
    mock_page = AsyncMock()
    mock_page.goto = AsyncMock(side_effect=TimeoutError("page timeout"))
    mock_page.close = AsyncMock()

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_playwright = AsyncMock()
    mock_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
    mock_playwright.__aexit__ = AsyncMock(return_value=False)
    mock_playwright.chromium.launch = AsyncMock(return_value=mock_browser)

    with patch("search.playwright_provider.async_playwright") as mock_ap:
        mock_ap.return_value = mock_playwright

        results = await provider.search("test", num=5)

    assert len(results) == 0
