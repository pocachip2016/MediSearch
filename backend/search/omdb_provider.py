"""search/omdb_provider.py — OMDb API 기반 IMDb 영화 메타 수집.

해외/비인기 영화 커버용. imdb_id 있으면 정확 조회, 없으면 title+year 검색.
DailyQuotaGuard로 1000req/일 한도 초과 방지. 한도 초과 시 빈 결과 반환,
파이프라인은 다른 provider 결과로 계속 진행.

원본 폐기 원칙: Plot/Genre/Director/Actors 텍스트만 조합하여 반환.
"""
from __future__ import annotations

import logging

import httpx

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.config import settings
from shared.limiter import DomainThrottle
from shared.quota import DailyQuotaGuard

logger = logging.getLogger(__name__)

_omdb_throttle = DomainThrottle(min_interval_s=settings.OMDB_MIN_INTERVAL_S)
_omdb_quota = DailyQuotaGuard(limit=settings.OMDB_DAILY_QUOTA, path="./omdb_quota.json")

_API_URL = "http://www.omdbapi.com/"
_USER_AGENT = "MediSearch/0.1 (facet pipeline; contact: ops@mediax.local)"


def _build_text(data: dict) -> str:
    """OMDb 응답에서 facet 평가에 유용한 텍스트 조합."""
    parts: list[str] = []
    if genre := data.get("Genre", "N/A"):
        if genre != "N/A":
            parts.append(f"장르: {genre}")
    if plot := data.get("Plot", "N/A"):
        if plot not in ("N/A", ""):
            parts.append(plot)
    extras: list[str] = []
    if director := data.get("Director", "N/A"):
        if director != "N/A":
            extras.append(f"감독: {director}")
    if actors := data.get("Actors", "N/A"):
        if actors != "N/A":
            extras.append(f"출연: {actors}")
    if country := data.get("Country", "N/A"):
        if country != "N/A":
            extras.append(f"제작국: {country}")
    if extras:
        parts.append(" | ".join(extras))
    return "\n\n".join(parts)


class OmdbProvider(SearchProvider):
    """OMDb API 기반 영화 메타 provider."""

    @property
    def provider_name(self) -> str:
        return "omdb"

    async def _fetch(
        self, client: httpx.AsyncClient, params: dict
    ) -> dict | None:
        """OMDb API 단건 조회. Response=False 또는 오류 시 None."""
        if not settings.OMDB_API_KEY:
            logger.warning("[omdb] OMDB_API_KEY 미설정 — 건너뜀")
            return None
        if not _omdb_quota.consume():
            return None

        await _omdb_throttle.wait()
        try:
            resp = await client.get(
                _API_URL,
                params={"apikey": settings.OMDB_API_KEY, "r": "json", **params},
            )
        except Exception as e:
            logger.warning(f"[omdb] 요청 실패: {e}")
            return None

        if resp.status_code != 200:
            logger.warning(f"[omdb] HTTP {resp.status_code}")
            return None

        data = resp.json()
        if data.get("Response") == "False":
            logger.info(f"[omdb] 결과 없음: {data.get('Error', '?')} / params={params}")
            return None
        return data

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """OMDb 문서 → SourceDocument. 쿼터 초과 시 빈 결과."""
        results: list[SourceDocument] = []
        try:
            async with httpx.AsyncClient(
                timeout=settings.OMDB_TIMEOUT_S,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                data = None

                # 1) imdb_id 정확 조회
                if query.imdb_id:
                    data = await self._fetch(client, {"i": query.imdb_id})

                # 2) title + year 폴백
                if data is None:
                    search_title = query.original_title or query.title
                    params: dict = {"t": search_title, "type": "movie"}
                    if query.production_year:
                        params["y"] = str(query.production_year)
                    data = await self._fetch(client, params)

                if data is None:
                    logger.info(f"[omdb] {query.title!r} → 결과 없음")
                    return results

                text = _build_text(data)
                if not text:
                    logger.info(f"[omdb] {query.title!r} → 텍스트 추출 실패")
                    return results

                imdb_id = data.get("imdbID", "")
                url = (
                    f"https://www.imdb.com/title/{imdb_id}/"
                    if imdb_id
                    else f"https://www.omdbapi.com/?t={query.title}"
                )
                title_str = data.get("Title", query.title)
                year_str = data.get("Year", "")
                results.append(
                    SourceDocument(
                        url=url,
                        title=f"{title_str} ({year_str})" if year_str else title_str,
                        text=text,
                        source_domain="omdbapi.com",
                        source_type=SourceType.synopsis,
                        trust_score=0.82,
                    )
                )
                logger.info(
                    f"[omdb] ✓ {title_str!r} ({year_str}) "
                    f"[quota 잔여: {_omdb_quota.remaining}]"
                )

        except Exception as e:
            logger.error(f"[omdb] 오류: {e}", exc_info=True)

        logger.info(f"[omdb] {query.title!r} → {len(results)}개 문서")
        return results
