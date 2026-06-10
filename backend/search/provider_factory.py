"""search/provider_factory.py — provider 이름 → 인스턴스 팩토리."""
from __future__ import annotations

import logging

from search.base import SearchProvider
from search.fixture_provider import FixtureProvider
from search.kmdb_provider import KmdbProvider
from search.playwright_provider import PlaywrightProvider
from search.tmdb_provider import TmdbProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, callable] = {
    "fixture":    lambda: FixtureProvider(),
    "playwright": lambda: PlaywrightProvider(headless=True, timeout_ms=15000),
    "tmdb":       lambda: TmdbProvider(),
    "kmdb":       lambda: KmdbProvider(),
}


def build_providers(names: list[str]) -> list[SearchProvider]:
    """name 목록 → SearchProvider 인스턴스 리스트.

    알 수 없는 이름은 경고 후 무시. 빈 리스트 반환 시 호출부에서 처리.
    """
    providers: list[SearchProvider] = []
    for name in names:
        factory = _PROVIDER_MAP.get(name)
        if factory is None:
            logger.warning(f"[factory] 알 수 없는 provider: {name!r} — 무시")
            continue
        providers.append(factory())
        logger.info(f"[factory] provider 등록: {name}")
    return providers
