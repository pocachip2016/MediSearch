"""pipeline/multi_runner.py — 멀티소스 앙상블 파이프라인.

각 provider 독립 검색·평가 → merge_facets() 신뢰도 가중 병합.
원본 폐기 원칙 동일 준수.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from models import MovieFacet, MovieMeta, SearchSource
from pipeline._events import EventCallback, doc_previews, emit
from pipeline.evaluator import EvaluationEngine
from pipeline.facet_merge import merge_facets
from pipeline.facets import attach_coverage, empty_facet
from pipeline.metadata_extractor import MetadataExtractionEngine
from pipeline.metadata_merge import merge_metadata
from pipeline.ollama_client import OllamaUnavailableError
from pipeline.metadata_schema import (
    attach_coverage as attach_meta_coverage,
    empty_metadata,
    validate_metadata,
)
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
        extractor: MetadataExtractionEngine | None = None,
    ):
        self.providers = providers
        self.evaluator = evaluator
        self.db = db
        self.extractor = extractor

    def _lookup_cache_meta(self, sq: SearchQuery) -> "MovieMeta | None":
        if self.db is None:
            return None
        cutoff = datetime.utcnow() - timedelta(days=30)
        q = self.db.query(MovieMeta).filter(MovieMeta.created_at >= cutoff)
        if sq.tmdb_id:
            return q.filter(MovieMeta.tmdb_id == sq.tmdb_id).order_by(MovieMeta.created_at.desc()).first()
        return q.filter(MovieMeta.movie_query == sq.title).order_by(MovieMeta.created_at.desc()).first()

    def _lookup_cache_facet(self, sq: SearchQuery) -> "MovieFacet | None":
        if self.db is None:
            return None
        cutoff = datetime.utcnow() - timedelta(days=30)
        q = self.db.query(MovieFacet).filter(MovieFacet.created_at >= cutoff)
        if sq.tmdb_id:
            return q.filter(MovieFacet.tmdb_id == sq.tmdb_id).order_by(MovieFacet.created_at.desc()).first()
        return q.filter(MovieFacet.movie_query == sq.title).order_by(MovieFacet.created_at.desc()).first()

    async def run(
        self,
        query: str | SearchQuery,
        require_namu: bool = False,
        on_event: EventCallback = None,
        persist: bool = True,
        force_refresh: bool = False,
        include_meta: bool = False,
    ) -> dict:
        sq = SearchQuery.from_text(query) if isinstance(query, str) else query

        if not force_refresh:
            row = self._lookup_cache_facet(sq)
            if row is not None:
                logger.info(f"[multi] {sq.title!r} — 캐시 히트 (facet_id={row.id})")
                result: dict = {
                    "movie_query": sq.title,
                    "facet": row.facet_json,
                    "source_count": row.source_count,
                    "facet_id": row.id,
                    "cached": True,
                    "providers_detail": [],
                }
                if include_meta and self.extractor:
                    meta_row = self._lookup_cache_meta(sq)
                    result["metadata"] = meta_row.meta_json if meta_row else None
                    result["meta_id"] = meta_row.id if meta_row else None
                return result

        await emit(on_event, "search_start", {
            "providers": [p.provider_name for p in self.providers],
            "query": {"title": sq.title, "tmdb_id": sq.tmdb_id, "imdb_id": sq.imdb_id},
        })

        # ── Phase 1: 모든 provider 동시 검색, provider_search 이벤트 도착순 emit ─
        search_results = await asyncio.gather(
            *[self._search_one(p, sq, on_event) for p in self.providers]
        )
        docs_by_provider: dict[str, list] = dict(search_results)
        providers_detail: list[dict] = [
            {
                "provider": name,
                "docs_count": len(docs),
                "status": "ok" if docs else "empty",
                "trust": None,
                "confidence": None,
                "evaluated": False,
            }
            for name, docs in search_results
        ]

        # ── require_namu 조기 종료: 웹 소스(namu+wiki) 둘 다 없을 때만 생략 ─────
        # "playwright"는 namu(httpx) 전환 이전 레거시 키 호환용
        web_has_docs = bool(
            docs_by_provider.get("namu")
            or docs_by_provider.get("playwright")
            or docs_by_provider.get("wikipedia")
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
        await emit(on_event, "eval_start", {})

        all_docs = []
        entries: list[tuple[dict, float]] = []
        provider_detail_map: dict[str, dict] = {d["provider"]: d for d in providers_detail}
        source_types: list[str] = []

        # TMDB 권위 장르 — Phase 2 전 1회 추출, 모든 provider 평가에 동일 힌트 전달
        tmdb_docs = docs_by_provider.get("tmdb", [])
        genre_hint: list[str] | None = next(
            (doc.meta.get("genres") for doc in tmdb_docs if doc.meta and doc.meta.get("genres")),
            None,
        )

        for provider in self.providers:
            docs = docs_by_provider.get(provider.provider_name, [])
            if not docs:
                continue

            all_docs.extend(docs)
            source_types.extend(d.source_type.value for d in docs)
            p_trust = sum(d.trust_score for d in docs) / len(docs)

            try:
                facet = await self.evaluator.evaluate(sq.title, docs, genre_hint=genre_hint)
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
                await emit(on_event, "provider_eval", {
                    "provider": provider.provider_name,
                    "trust": round(p_trust, 3),
                    "confidence": facet.get("confidence"),
                    "facet": facet,
                })
            except OllamaUnavailableError:
                raise  # 인프라 불능 — 전체 run 실패시켜 빈 facet success 영속 차단
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

        await emit(on_event, "merge", {
            "confidence": merged.get("confidence"),
            "coverage": merged.get("_coverage"),
        })

        source_count = await self._save_sources(sq.title, all_docs, persist=persist)
        facet_id = await self._save_facet(sq.title, merged, source_count, tmdb_id=sq.tmdb_id, persist=persist)

        result: dict = {
            "movie_query": sq.title,
            "facet": merged,
            "source_count": source_count,
            "confidence": merged.get("confidence"),
            "facet_id": facet_id,
            "providers_detail": providers_detail,
        }
        if include_meta and self.extractor:
            merged_meta, meta_id = await self._extract_and_save_meta(sq, docs_by_provider, persist=persist)
            result["metadata"] = merged_meta
            result["meta_id"] = meta_id
        return result

    async def _extract_and_save_meta(
        self,
        sq: SearchQuery,
        docs_by_provider: dict[str, list],
        persist: bool = True,
    ) -> tuple[dict, "int | None"]:
        """Phase 1 docs를 재사용해 메타 추출 — 추가 provider 검색 없음."""
        entries: list[tuple[dict, float]] = []
        provider_names: list[str] = []
        source_types: list[str] = []
        synopsis_raws: list[str] = []
        all_text_docs: list = []
        text_provider_names: list[str] = []
        text_trust_scores: list[float] = []

        for provider in self.providers:
            docs = docs_by_provider.get(provider.provider_name, [])
            if not docs:
                continue
            source_types.extend(d.source_type.value for d in docs)
            p_trust = sum(d.trust_score for d in docs) / len(docs)
            structured_docs = [d for d in docs if d.meta is not None]
            text_docs = [d for d in docs if d.meta is None]
            if structured_docs:
                for d in structured_docs:
                    meta = validate_metadata(d.meta)
                    entries.append((meta, d.trust_score))
                    provider_names.append(provider.provider_name)
                    raw = (d.meta or {}).get("synopsis_raw")
                    if raw:
                        synopsis_raws.append(raw)
            if text_docs:
                all_text_docs.extend(text_docs)
                text_provider_names.append(provider.provider_name)
                text_trust_scores.append(p_trust)

        if all_text_docs:
            try:
                meta = await self.extractor.extract(sq.title, all_text_docs)
                avg_trust = sum(text_trust_scores) / len(text_trust_scores)
                entries.append((meta, avg_trust))
                provider_names.append(text_provider_names[0])
            except OllamaUnavailableError:
                raise  # 인프라 불능 — 빈 meta success 영속 차단
            except Exception as e:
                logger.warning(f"[multi] include_meta text 추출 실패: {e}")

        if not entries:
            empty = empty_metadata()
            empty["_provenance"] = {}
            merged = attach_meta_coverage(empty, [])
        else:
            merged = merge_metadata(entries, source_types, provider_names)

        if not merged.get("story") and synopsis_raws:
            try:
                story = await self.extractor.rewrite_story(sq.title, synopsis_raws)
                if story:
                    merged["story"] = story
            except Exception as e:
                logger.warning(f"[multi] include_meta story 재작성 실패: {e}")

        meta_id = await self._save_meta(sq.title, merged, tmdb_id=sq.tmdb_id, persist=persist)
        return merged, meta_id

    async def _save_meta(
        self, query: str, meta: dict, tmdb_id: "int | None" = None, persist: bool = True
    ) -> "int | None":
        if not persist:
            return None
        try:
            mm = MovieMeta(
                movie_query=query,
                meta_json=meta,
                llm_engine="ollama",
                source_count=0,
                tmdb_id=tmdb_id,
            )
            self.db.add(mm)
            self.db.commit()
            return mm.id
        except Exception as e:
            logger.error(f"[multi] meta 저장 실패 {query!r}: {e}")
            self.db.rollback()
            return None

    async def _search_one(
        self, provider: SearchProvider, sq: SearchQuery, on_event: EventCallback
    ) -> tuple[str, list]:
        """단일 provider 검색 + 도착 즉시 provider_search 이벤트 emit."""
        try:
            docs = await provider.search(sq)
        except Exception as e:
            logger.warning(f"[multi] {provider.provider_name} 검색 실패: {e}")
            docs = []
        if docs:
            logger.info(f"[multi] {provider.provider_name} → {len(docs)}개")
        else:
            logger.info(f"[multi] {provider.provider_name} → 0개 (건너뜀)")
        await emit(on_event, "provider_search", {
            "provider": provider.provider_name,
            "docs_count": len(docs),
            "status": "ok" if docs else "empty",
            "docs": doc_previews(docs),
        })
        return provider.provider_name, docs

    async def _save_sources(self, query: str, docs, persist: bool = True) -> int:
        if not persist:
            return len(docs)
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

    async def _save_facet(self, query: str, facet: dict, source_count: int, tmdb_id: int | None = None, persist: bool = True) -> int | None:
        if not persist:
            return None
        try:
            mf = MovieFacet(
                movie_query=query,
                facet_json=facet,
                llm_engine="ollama",
                source_count=source_count,
                tmdb_id=tmdb_id,
            )
            self.db.add(mf)
            self.db.commit()
            return mf.id
        except Exception as e:
            logger.error(f"[multi] facet 저장 실패 {query!r}: {e}")
            self.db.rollback()
            return None
