"""pipeline/multi_runner.py — 멀티소스 앙상블 파이프라인.

각 provider 독립 검색·평가 → merge_facets() 신뢰도 가중 병합.
원본 폐기 원칙 동일 준수.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from models import MovieFacet, SearchSource
from pipeline.evaluator import EvaluationEngine
from pipeline.facet_merge import merge_facets
from pipeline.facets import attach_coverage, empty_facet
from search.base import SearchProvider, SearchQuery

logger = logging.getLogger(__name__)


class MultiSourceRunner:
    """N개 provider → 앙상블 facet 반환.

    실행 흐름:
        for each provider:
            docs = provider.search(query)
            facet = evaluator.evaluate(query, docs)
            entries.append((facet, avg_trust))
        merged = merge_facets(entries)
        save sources + merged facet
    """

    def __init__(
        self,
        providers: list[SearchProvider],
        evaluator: EvaluationEngine,
        db: Session,
    ):
        self.providers = providers
        self.evaluator = evaluator
        self.db = db

    async def run(self, query: str | SearchQuery, require_namu: bool = False) -> dict:
        sq = SearchQuery.from_text(query) if isinstance(query, str) else query

        # ── Phase 1: 모든 provider 검색 (평가 전 수행) ────────────────────────
        docs_by_provider: dict[str, list] = {}
        providers_detail: list[dict] = []

        for provider in self.providers:
            try:
                docs = await provider.search(sq)
            except Exception as e:
                logger.warning(f"[multi] {provider.provider_name} 검색 실패: {e}")
                docs = []
            docs_by_provider[provider.provider_name] = docs
            if docs:
                logger.info(f"[multi] {provider.provider_name} → {len(docs)}개")
            else:
                logger.info(f"[multi] {provider.provider_name} → 0개 (건너뜀)")

            # 검색 결과 저장
            providers_detail.append({
                "provider": provider.provider_name,
                "docs_count": len(docs),
                "status": "ok" if docs else "empty",
                "trust": None,
                "confidence": None,
                "evaluated": False,
            })

        # ── require_namu 조기 종료: 웹 소스(namu+wiki) 둘 다 없을 때만 생략 ─────
        web_has_docs = bool(
            docs_by_provider.get("playwright") or docs_by_provider.get("wikipedia")
        )
        if require_namu and not web_has_docs:
            logger.info(f"[multi] {sq.title!r} — 웹 소스 없음, 조기 종료 (require_web)")
            return {
                "movie_query": sq.title,
                "facet": empty_facet(),
                "source_count": 0,
                "facet_id": None,
                "skipped_reason": "no_web",
                "providers_detail": providers_detail,
            }

        # ── Phase 2: provider별 Ollama 평가 ───────────────────────────────────
        all_docs = []
        entries: list[tuple[dict, float]] = []
        provider_detail_map: dict[str, dict] = {d["provider"]: d for d in providers_detail}
        source_types: list[str] = []

        for provider in self.providers:
            docs = docs_by_provider.get(provider.provider_name, [])
            if not docs:
                continue

            all_docs.extend(docs)
            source_types.extend(d.source_type.value for d in docs)
            p_trust = sum(d.trust_score for d in docs) / len(docs)

            try:
                facet = await self.evaluator.evaluate(sq.title, docs)
                entries.append((facet, p_trust))
                logger.info(
                    f"[multi] {provider.provider_name} → 평가 완료 "
                    f"(trust={p_trust:.2f}, confidence={facet.get('confidence')})"
                )
                if provider.provider_name in provider_detail_map:
                    provider_detail_map[provider.provider_name].update({
                        "trust": round(p_trust, 3),
                        "confidence": facet.get("confidence"),
                        "evaluated": True,
                    })
            except Exception as e:
                logger.warning(f"[multi] {provider.provider_name} 평가 실패: {e}")

        if not entries:
            logger.warning(f"[multi] {sq.title!r} — 모든 provider 실패, 빈 facet 반환")
            merged = attach_coverage(empty_facet(), [])
        else:
            merged = merge_facets(entries, source_types)
            logger.info(
                f"[multi] {sq.title!r} → {len(entries)}개 소스 병합 "
                f"(confidence={merged.get('confidence')})"
            )

        source_count = await self._save_sources(sq.title, all_docs)
        facet_id = await self._save_facet(sq.title, merged, source_count)

        return {
            "movie_query": sq.title,
            "facet": merged,
            "source_count": source_count,
            "facet_id": facet_id,
            "providers_detail": providers_detail,
        }

    async def _save_sources(self, query: str, docs) -> int:
        count = 0
        for doc in docs:
            try:
                self.db.add(SearchSource(
                    movie_query=query,
                    url=doc.url,
                    title=doc.title,
                    source_domain=doc.source_domain,
                    source_type=doc.source_type,
                    trust_score=doc.trust_score,
                ))
                count += 1
            except Exception as e:
                logger.warning(f"[multi] 소스 저장 실패 {doc.url}: {e}")
        self.db.commit()
        return count

    async def _save_facet(self, query: str, facet: dict, source_count: int) -> int | None:
        try:
            mf = MovieFacet(
                movie_query=query,
                facet_json=facet,
                llm_engine="ollama",
                source_count=source_count,
            )
            self.db.add(mf)
            self.db.commit()
            return mf.id
        except Exception as e:
            logger.error(f"[multi] facet 저장 실패 {query!r}: {e}")
            self.db.rollback()
            return None
