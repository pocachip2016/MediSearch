"""search/tmdb_provider.py — mediaX tmdb_movie_cache 읽기 provider.

title 정확매칭 우선 + vote_count/popularity 랭킹으로 동음이의 노이즈 제거.
overview를 SourceDocument.text로 사용 (사실 메타·줄거리 신호).
"""
from __future__ import annotations

import logging

from sqlalchemy import text

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.mediax_db import get_mediax_session

logger = logging.getLogger(__name__)

# tmdb_id 정확 조회 (mediaX외부ID 보유 시 사용)
_QUERY_BY_ID = text(
    """
    SELECT title, overview, vote_count, popularity, release_date
    FROM tmdb_movie_cache
    WHERE id = :tmdb_id
      AND overview IS NOT NULL AND overview <> ''
    LIMIT 1
    """
)

# 제목 ILIKE 폴백 — 인기/관객수 랭킹 + 연도 필터 옵션
_QUERY_BY_TITLE = text(
    """
    SELECT title, overview, vote_count, popularity, release_date
    FROM tmdb_movie_cache
    WHERE overview IS NOT NULL AND overview <> ''
      AND (title = :q OR original_title = :q OR title ILIKE :like)
      AND (:year_min IS NULL OR EXTRACT(YEAR FROM release_date) BETWEEN :year_min AND :year_max)
    ORDER BY
      (CASE WHEN title = :q OR original_title = :q THEN 0 ELSE 1 END),
      COALESCE(vote_count, 0) DESC,
      COALESCE(popularity, 0) DESC
    LIMIT :num
    """
)


def _trust_score(vote_count: int | None) -> float:
    """관객수 반영 신뢰도. base 0.7 + vote_count 보정(최대 +0.25)."""
    vc = vote_count or 0
    return round(min(1.0, 0.7 + min(vc, 10000) / 10000 * 0.25), 3)


class TmdbProvider(SearchProvider):
    """mediaX TMDB 캐시 기반 영화 메타 provider."""

    @property
    def provider_name(self) -> str:
        return "tmdb"

    async def search(self, query: SearchQuery, num: int = 2) -> list[SourceDocument]:
        session = get_mediax_session()
        if session is None:
            logger.warning("[tmdb] mediaX 세션 없음 — 빈 결과")
            return []

        try:
            if query.tmdb_id is not None:
                rows = session.execute(
                    _QUERY_BY_ID, {"tmdb_id": query.tmdb_id}
                ).fetchall()
                logger.info(f"[tmdb] ID 정확조회: tmdb_id={query.tmdb_id}")
            else:
                year_min = query.production_year - 1 if query.production_year else None
                year_max = query.production_year + 1 if query.production_year else None
                rows = session.execute(
                    _QUERY_BY_TITLE,
                    {
                        "q": query.title,
                        "like": f"%{query.title}%",
                        "year_min": year_min,
                        "year_max": year_max,
                        "num": num,
                    },
                ).fetchall()
        except Exception as e:
            logger.error(f"[tmdb] 쿼리 실패 {query.title!r}: {e}")
            return []
        finally:
            session.close()

        docs: list[SourceDocument] = []
        for row in rows:
            title, overview, vote_count, popularity, release_date = row
            year = release_date.year if release_date else "?"
            docs.append(
                SourceDocument(
                    url=f"https://www.themoviedb.org/search?query={query.title}",
                    title=f"{title} ({year})",
                    text=overview or "",
                    source_domain="themoviedb.org",
                    source_type=SourceType.synopsis,
                    trust_score=_trust_score(vote_count),
                )
            )

        logger.info(f"[tmdb] {query.title!r} → {len(docs)}개")
        return docs
