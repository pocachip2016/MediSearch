"""search/kmdb_provider.py — mediaX kmdb_movie_cache 읽기 provider.

KMDb 캐시는 검색 하이라이트 마크업(!HS ... !HE)이 title/synopsis에 박혀 있다.
정제 후 정확매칭을 우선해 동음이의 노이즈를 제거한다.
"""
from __future__ import annotations

import logging
import re

from sqlalchemy import text

from search.base import SearchProvider, SourceDocument, SourceType
from shared.mediax_db import get_mediax_session

logger = logging.getLogger(__name__)

# 후보 수집: ILIKE 부분매칭 (마크업 사이에 있어도 매칭됨)
_QUERY = text(
    """
    SELECT title, synopsis, prod_year, nation, genre
    FROM kmdb_movie_cache
    WHERE synopsis IS NOT NULL AND synopsis <> ''
      AND title ILIKE :like
    ORDER BY COALESCE(prod_year, 0) DESC
    LIMIT 20
    """
)

_HS_HE = re.compile(r"\s*!H[SE]\s*")
_MULTISPACE = re.compile(r"\s{2,}")


def clean_markup(s: str | None) -> str:
    """KMDb 하이라이트 마크업(!HS/!HE) 제거 + 공백 정리."""
    if not s:
        return ""
    out = _HS_HE.sub(" ", s)
    return _MULTISPACE.sub(" ", out).strip()


class KmdbProvider(SearchProvider):
    """mediaX KMDb 캐시 기반 한국영화 공식 메타 provider."""

    @property
    def provider_name(self) -> str:
        return "kmdb"

    async def search(self, query: str, num: int = 1) -> list[SourceDocument]:
        session = get_mediax_session()
        if session is None:
            logger.warning("[kmdb] mediaX 세션 없음 — 빈 결과")
            return []

        try:
            rows = session.execute(_QUERY, {"like": f"%{query}%"}).fetchall()
        except Exception as e:
            logger.error(f"[kmdb] 쿼리 실패 {query!r}: {e}")
            return []
        finally:
            session.close()

        # 정제 후 정확매칭 우선, 없으면 부분매칭 폴백
        exact, partial = [], []
        for row in rows:
            title, synopsis, prod_year, nation, genre = row
            clean_title = clean_markup(title)
            doc = SourceDocument(
                url=f"https://www.kmdb.or.kr/search?query={query}",
                title=f"{clean_title} ({prod_year or '?'})",
                text=clean_markup(synopsis),
                source_domain="kmdb.or.kr",
                source_type=SourceType.synopsis,
                trust_score=0.85,  # 공식 메타
            )
            (exact if clean_title == query else partial).append(doc)

        docs = (exact or partial)[:num]
        logger.info(
            f"[kmdb] {query!r} → {len(docs)}개 "
            f"(exact={len(exact)}, partial={len(partial)})"
        )
        return docs
