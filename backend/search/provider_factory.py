"""search/provider_factory.py — provider 이름 → 인스턴스 팩토리."""
from __future__ import annotations

import logging

from search.base import SearchProvider
from search.fixture_provider import FixtureProvider
from search.kmdb_provider import KmdbProvider
from search.namu_provider import NamuHttpProvider
from search.tmdb_provider import TmdbProvider
from search.ko_wiki_provider import KoreanWikiProvider
from search.omdb_provider import OmdbProvider
from search.wikipedia_provider import WikipediaProvider

logger = logging.getLogger(__name__)

_PROVIDER_MAP: dict[str, callable] = {
    "fixture":    lambda: FixtureProvider(),
    "namu":       lambda: NamuHttpProvider(timeout_s=15.0),
    # 레거시 별칭 — playwright 명칭의 기존 env(BACKFILL_PROVIDERS 등) 호환
    "playwright": lambda: NamuHttpProvider(timeout_s=15.0),
    "tmdb":       lambda: TmdbProvider(),
    "kmdb":       lambda: KmdbProvider(),
    "wikipedia":  lambda: WikipediaProvider(),
    "kowiki":     lambda: KoreanWikiProvider(),
    "omdb":       lambda: OmdbProvider(),
}


def build_providers(names: list[str], headless: bool = True) -> list[SearchProvider]:
    """name 목록 → SearchProvider 인스턴스 리스트.

    알 수 없는 이름은 경고 후 무시. 빈 리스트 반환 시 호출부에서 처리.
    headless 파라미터는 playwright 시절 호환용 잔재 — namu(httpx)에서는 무의미.
    """
    providers: list[SearchProvider] = []
    for name in names:
        factory = _PROVIDER_MAP.get(name)
        if factory is None:
            logger.warning(f"[factory] 알 수 없는 provider: {name!r} — 무시")
            continue
        if name == "playwright":
            logger.info("[factory] 'playwright'는 deprecated — 'namu'(httpx)로 대체됨")
        providers.append(factory())
        logger.info(f"[factory] provider 등록: {name}")
    return providers
