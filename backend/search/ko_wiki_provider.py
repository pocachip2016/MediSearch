"""search/ko_wiki_provider.py — 한국어 위키백과 MediaWiki API 기반 영화 문서 수집.

나무위키에 없거나 공식 정보가 필요한 영화용. 영문 wikipedia_provider 패턴 동일.
원본 폐기 원칙: extract 텍스트만 SourceDocument로 반환, HTML 미저장.
"""
from __future__ import annotations

import logging

import httpx

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.config import settings
from shared.limiter import DomainThrottle

logger = logging.getLogger(__name__)

_ko_wiki_throttle = DomainThrottle(min_interval_s=settings.KO_WIKI_MIN_INTERVAL_S)

_API_URL = "https://ko.wikipedia.org/w/api.php"
_USER_AGENT = "MediSearch/0.1 (facet pipeline; contact: ops@mediax.local)"
_MIN_EXTRACT_LEN = 80

# 한국어 위키 disambiguation 패턴
_DISAMBIG_MARKERS = ("다른 뜻에 대해서는", "동음이의어", "이 문서는 동음이의")


class KoreanWikiProvider(SearchProvider):
    """한국어 위키백과 MediaWiki API 영화 문서 수집기."""

    @property
    def provider_name(self) -> str:
        return "kowiki"

    def _candidate_titles(self, query: SearchQuery) -> list[str]:
        """검색 제목 후보 목록 (순서 우선순위)."""
        base = query.title
        candidates = [base, f"{base} (영화)"]
        if query.production_year:
            candidates.append(f"{base} ({query.production_year}년 영화)")
        seen: set[str] = set()
        return [c for c in candidates if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]

    async def _fetch_extract(
        self, client: httpx.AsyncClient, title: str
    ) -> tuple[str, str] | None:
        """제목으로 intro extract 조회. (resolved_title, text) 또는 None."""
        params = {
            "action": "query",
            "format": "json",
            "prop": "extracts",
            "exintro": "1",
            "explaintext": "1",
            "redirects": "1",
            "titles": title,
        }
        await _ko_wiki_throttle.wait()
        try:
            resp = await client.get(_API_URL, params=params)
        except Exception as e:
            logger.warning(f"[kowiki] 요청 실패 {title!r}: {e}")
            return None

        if resp.status_code != 200:
            logger.warning(f"[kowiki] HTTP {resp.status_code}: {title!r}")
            return None

        pages = resp.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1" or "missing" in page:
                continue
            extract = (page.get("extract") or "").strip()
            if len(extract) < _MIN_EXTRACT_LEN:
                continue
            if any(m in extract[:200] for m in _DISAMBIG_MARKERS):
                logger.info(f"[kowiki] disambiguation 페이지 스킵: {title!r}")
                continue
            return page.get("title", title), extract[:1500]
        return None

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """한국어 위키 문서 → SourceDocument. 첫 유효 결과 1건 반환."""
        results: list[SourceDocument] = []
        try:
            async with httpx.AsyncClient(
                timeout=settings.KO_WIKI_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                for title in self._candidate_titles(query):
                    found = await self._fetch_extract(client, title)
                    if not found:
                        continue
                    resolved_title, text = found
                    results.append(
                        SourceDocument(
                            url=f"https://ko.wikipedia.org/wiki/{resolved_title.replace(' ', '_')}",
                            title=resolved_title,
                            text=text,
                            source_domain="ko.wikipedia.org",
                            source_type=SourceType.synopsis,
                            trust_score=0.80,
                        )
                    )
                    logger.info(f"[kowiki] ✓ {resolved_title!r}")
                    break
        except Exception as e:
            logger.error(f"[kowiki] 오류: {e}", exc_info=True)

        logger.info(f"[kowiki] {query.title!r} → {len(results)}개 문서")
        return results
