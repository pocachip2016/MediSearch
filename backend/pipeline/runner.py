"""pipeline/runner.py — 파이프라인 orchestrator (search → evaluate → save).

원본 폐기 원칙 준수: 검색된 소스 메타만 DB에 저장.
"""
from __future__ import annotations

import logging
from sqlalchemy.orm import Session

from models import MovieFacet, SearchSource, SourceType
from pipeline.evaluator import EvaluationEngine
from search.base import SearchProvider, SearchQuery

logger = logging.getLogger(__name__)


class PipelineRunner:
    """검색 → 평가 → 저장 파이프라인."""

    def __init__(
        self,
        search_provider: SearchProvider,
        evaluator: EvaluationEngine,
        db: Session,
    ):
        self.search_provider = search_provider
        self.evaluator = evaluator
        self.db = db

    async def run(self, query: str | SearchQuery, **_kwargs) -> dict:
        """query → facet dict 반환. 오류 시 빈 facet + 로깅."""
        sq = SearchQuery.from_text(query) if isinstance(query, str) else query
        query = sq.title  # 이후 로직은 title 문자열 사용
        try:
            # 1. 검색
            docs = await self.search_provider.search(sq)
            logger.info(f"[pipeline] {query} → {len(docs)}개 소스 검색")

            # 2. 평가 (facet JSON 생성)
            facet = await self.evaluator.evaluate(query, docs)
            logger.info(f"[pipeline] {query} → facet 생성 (confidence={facet.get('confidence')})")

            # 3. DB 저장 (소스 메타 + facet)
            source_count = await self._save_sources(query, docs)
            facet_id = await self._save_facet(query, facet, source_count)

            logger.info(f"[pipeline] {query} → 저장 완료 (facet_id={facet_id})")
            return {
                "movie_query": query,
                "facet": facet,
                "source_count": source_count,
                "facet_id": facet_id,
            }
        except Exception as e:
            logger.error(f"[pipeline] {query} 오류: {e}", exc_info=True)
            from pipeline.facets import empty_facet, attach_coverage
            empty = attach_coverage(empty_facet(), [])
            return {
                "movie_query": query,
                "facet": empty,
                "source_count": 0,
                "facet_id": None,
                "error": str(e),
            }

    async def _save_sources(self, query: str, docs) -> int:
        """검색 소스 메타 저장 (원문은 버림)."""
        count = 0
        for doc in docs:
            try:
                source = SearchSource(
                    movie_query=query,
                    url=doc.url,
                    title=doc.title,
                    source_domain=doc.source_domain,
                    source_type=doc.source_type,
                    trust_score=doc.trust_score,
                )
                self.db.add(source)
                count += 1
            except Exception as e:
                logger.warning(f"[runner] 소스 저장 실패 {doc.url}: {e}")

        self.db.commit()
        return count

    async def _save_facet(self, query: str, facet: dict, source_count: int) -> int:
        """평가 결과(facet) 저장."""
        try:
            movie_facet = MovieFacet(
                movie_query=query,
                facet_json=facet,
                llm_engine="ollama",
                source_count=source_count,
            )
            self.db.add(movie_facet)
            self.db.commit()
            return movie_facet.id
        except Exception as e:
            logger.error(f"[runner] facet 저장 실패 {query}: {e}")
            self.db.rollback()
            return None
