"""검색 계층 팩토리 및 제공자 관리."""
from shared.config import settings
from search.base import SearchProvider
from search.fixture_provider import FixtureProvider


def get_search_provider() -> SearchProvider:
    """환경 변수 기반 검색 제공자 반환.

    SEARCH_PROVIDER 환경변수:
      - 'fixture': FixtureProvider (POC 기본)
      - 'playwright': PlaywrightProvider (추후 구현)
    """
    provider_type = getattr(settings, "SEARCH_PROVIDER", "fixture").lower()

    if provider_type == "fixture":
        return FixtureProvider()
    elif provider_type == "playwright":
        # 추후: from search.playwright_provider import PlaywrightProvider
        raise NotImplementedError("Playwright provider coming soon")
    else:
        raise ValueError(f"Unknown search provider: {provider_type}")


__all__ = [
    "SearchProvider",
    "SourceDocument",
    "SourceType",
    "get_search_provider",
    "FixtureProvider",
]
