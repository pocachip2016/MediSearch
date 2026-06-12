"""search/provider_factory.py — provider 이름 → 인스턴스 팩토리."""
from __future__ import annotations

import logging

from search.base import SearchProvider
from search.fixture_provider import FixtureProvider
from search.kmdb_provider import KmdbProvider
from search.playwright_provider import PlaywrightProvider
from search.tmdb_provider import TmdbProvider
from search.ko_wiki_provider import KoreanWikiProvider
from search.omdb_provider import OmdbProvider
from search.wikipedia_provider import WikipediaProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, callable] = {
    "fixture":    lambda: FixtureProvider(),
    "playwright": lambda: PlaywrightProvider(headless=True, timeout_ms=15000),
    "tmdb":       lambda: TmdbProvider(),
    "kmdb":       lambda: KmdbProvider(),
    "wikipedia":  lambda: WikipediaProvider(),
    "kowiki":     lambda: KoreanWikiProvider(),
    "omdb":       lambda: OmdbProvider(),
}


def build_providers(names: list[str], headless: bool = True) -> list[SearchProvider]:
    """name 목록 → SearchProvider 인스턴스 리스트.

    알 수 없는 이름은 경고 후 무시. 빈 리스트 반환 시 호출부에서 처리.
    headless=False 시 playwright provider는 실제 브라우저 창을 표시한다 (로컬 실행 전용).
    """
    provider_map: dict[str, callable] = {
        **_PROVIDER_MAP,
        "playwright": lambda: PlaywrightProvider(headless=headless, timeout_ms=15000),
    }
    providers: list[SearchProvider] = []
    for name in names:
        factory = provider_map.get(name)
        if factory is None:
            logger.warning(f"[factory] 알 수 없는 provider: {name!r} — 무시")
            continue
        providers.append(factory())
        logger.info(f"[factory] provider 등록: {name} (headless={headless if name == 'playwright' else 'N/A'})")
    return providers
