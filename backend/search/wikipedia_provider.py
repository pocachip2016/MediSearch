"""search/wikipedia_provider.py — 영문 Wikipedia REST API 기반 영화 줄거리 수집.

나무위키(한국어)에 없는 해외 영화 커버용. Playwright 불필요 — 공식 API를
httpx로 호출하므로 가볍고 빠르다. original_title(영문)을 검색 키로 사용한다.

원본 폐기 원칙 동일: extract 텍스트만 SourceDocument로 반환, HTML 미저장.
"""
from __future__ import annotations

import logging

import httpx

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.limiter import DomainThrottle
from shared.config import settings

logger = logging.getLogger(__name__)

_wiki_throttle = DomainThrottle(min_interval_s=settings.WIKI_MIN_INTERVAL_S)

_API_URL = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = "MediSearch/0.1 (facet pipeline; contact: ops@mediax.local)"
_MIN_EXTRACT_LEN = 80  # 너무 짧은 disambiguation/stub 배제


class WikipediaProvider(SearchProvider):
    """영문 Wikipedia REST API 영화 문서 수집기."""

    @property
    def provider_name(self) -> str:
        return "wikipedia"

    def _candidate_titles(self, query: SearchQuery) -> list[str]:
        """검색 제목 후보: 영문 original_title 우선, 영화 한정 suffix 폴백."""
        base = query.original_title or query.title
        candidates = [base]
        if query.production_year:
            candidates.append(f"{base} ({query.production_year} film)")
        candidates.append(f"{base} (film)")
        # 중복 제거 (순서 유지)
        seen = set()
        return [c for c in candidates if not (c in seen or seen.add(c))]

    async def _fetch_extract(self, client: httpx.AsyncClient, title: str) -> tuple[str, str] | None:
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
        await _wiki_throttle.wait()
        resp = await client.get(_API_URL, params=params)
        if resp.status_code != 200:
            logger.warning(f"[wikipedia] HTTP {resp.status_code}: {title!r}")
            return None

        pages = resp.json().get("query", {}).get("pages", {})
        for page_id, page in pages.items():
            if page_id == "-1" or "missing" in page:
                continue  # 문서 없음
            extract = (page.get("extract") or "").strip()
            if len(extract) < _MIN_EXTRACT_LEN:
                continue  # stub/disambiguation
            # disambiguation 페이지 휴리스틱 배제
            if "may refer to" in extract[:120].lower():
                continue
            return page.get("title", title), extract[:1500]
        return None

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """영문 위키 문서 → SourceDocument. 첫 유효 결과 1건 반환."""
        results: list[SourceDocument] = []
        try:
            async with httpx.AsyncClient(
                timeout=settings.WIKI_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                for title in self._candidate_titles(query):
                    try:
                        found = await self._fetch_extract(client, title)
                    except Exception as e:
                        logger.warning(f"[wikipedia] 조회 실패 {title!r}: {e}")
                        continue
                    if not found:
                        continue
                    resolved_title, text = found
                    results.append(SourceDocument(
                        url=f"https://en.wikipedia.org/wiki/{resolved_title.replace(' ', '_')}",
                        title=resolved_title,
                        text=text,
                        source_domain="en.wikipedia.org",
                        source_type=SourceType.synopsis,
                        trust_score=0.75,
                    ))
                    logger.info(f"[wikipedia] ✓ {resolved_title!r}")
                    break
        except Exception as e:
            logger.error(f"[wikipedia] 오류: {e}", exc_info=True)

        logger.info(f"[wikipedia] {query.title!r} → {len(results)}개 문서")
        return results
