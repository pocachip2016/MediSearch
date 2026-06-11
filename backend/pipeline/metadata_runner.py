"""pipeline/metadata_runner.py — 멀티소스 메타 보강 파이프라인.

하이브리드 추출 흐름:
  Phase 1: provider 병렬 검색
  Phase 2: doc.meta 있으면 직접 채택 (LLM 0회), 텍스트 doc만 MetadataExtractionEngine 호출
           story 폴백: 병합 후 story 없고 synopsis_raw 후보 있으면 rewrite_story 1회
  Phase 3: merge_metadata → SearchSource 저장 + MovieMeta 저장

원본 미저장 원칙: synopsis_raw·doc.text·doc.meta는 파이프라인 통과 후 폐기.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy.orm import Session

from models import MovieMeta, SearchSource
from pipeline.metadata_extractor import MetadataExtractionEngine
from pipeline.metadata_merge import merge_metadata
from pipeline.metadata_schema import attach_coverage, empty_metadata, validate_metadata
from search.base import SearchProvider, SearchQuery

logger = logging.getLogger(__name__)

_WEB_PROVIDERS = {"playwright", "wikipedia", "kowiki"}


class MetadataRunner:
    """N개 provider → 앙상블 기본 메타 반환."""

    def __init__(
        self,
        providers: list[SearchProvider],
        extractor: MetadataExtractionEngine,
        db: Session,
    ):
        self.providers = providers
        self.extractor = extractor
        self.db = db

    async def run(
        self, query: str | SearchQuery, require_web: bool = False
    ) -> dict:
        sq = SearchQuery.from_text(query) if isinstance(query, str) else query

        # ── Phase 1: 병렬 검색 ───────────────────────────────
        docs_by_provider: dict[str, list] = {}
        providers_detail: list[dict] = []

        results = await asyncio.gather(
            *[self._safe_search(p, sq) for p in self.providers],
            return_exceptions=False,
        )
        for provider, docs in zip(self.providers, results):
            docs_by_provider[provider.provider_name] = docs
            providers_detail.append({
                "provider": provider.provider_name,
                "docs_count": len(docs),
                "trust": None,
                "confidence": None,
                "evaluated": False,
                "structured": False,
            })
            logger.info(f"[meta_runner] {provider.provider_name} → {len(docs)}개")

        # ── require_web 조기 종료 ────────────────────────────
        web_has_docs = any(
            bool(docs_by_provider.get(p)) for p in _WEB_PROVIDERS
        )
        if require_web and not web_has_docs:
            logger.info(f"[meta_runner] {sq.title!r} — 웹 소스 없음, 조기 종료")
            empty = empty_metadata()
            empty["_provenance"] = {}
            empty = attach_coverage(empty, [])
            return {
                "movie_query": sq.title,
                "metadata": empty,
                "source_count": 0,
                "meta_id": None,
                "skipped_reason": "no_web",
                "providers_detail": providers_detail,
            }

        # ── Phase 2: 하이브리드 추출 ─────────────────────────
        all_docs = []
        entries: list[tuple[dict, float]] = []
        provider_names: list[str] = []
        source_types: list[str] = []
        synopsis_raws: list[str] = []   # story 폴백용

        detail_map: dict[str, dict] = {d["provider"]: d for d in providers_detail}

        for provider in self.providers:
            docs = docs_by_provider.get(provider.provider_name, [])
            if not docs:
                continue

            all_docs.extend(docs)
            source_types.extend(d.source_type.value for d in docs)
            p_trust = sum(d.trust_score for d in docs) / len(docs)

            # 구조화 doc: meta가 있는 doc이 하나라도 있으면 구조화 경로
            structured_docs = [d for d in docs if d.meta is not None]
            text_docs = [d for d in docs if d.meta is None]

            if structured_docs:
                # 구조화 소스: validate_metadata 직접 채택, 병합은 meta들 평균 trust
                for d in structured_docs:
                    meta = validate_metadata(d.meta)
                    entries.append((meta, d.trust_score))
                    provider_names.append(provider.provider_name)
                    # synopsis_raw 수집 (story 폴백용)
                    raw = (d.meta or {}).get("synopsis_raw")
                    if raw:
                        synopsis_raws.append(raw)
                detail_map[provider.provider_name].update({
                    "trust": round(p_trust, 3),
                    "evaluated": False,
                    "structured": True,
                })

            if text_docs:
                # 텍스트 소스: LLM 추출
                try:
                    meta = await self.extractor.extract(sq.title, text_docs)
                    entries.append((meta, p_trust))
                    provider_names.append(provider.provider_name)
                    detail_map[provider.provider_name].update({
                        "trust": round(p_trust, 3),
                        "confidence": meta.get("confidence"),
                        "evaluated": True,
                    })
                except Exception as e:
                    logger.warning(f"[meta_runner] {provider.provider_name} 추출 실패: {e}")

        # ── Phase 3: 병합 ────────────────────────────────────
        if not entries:
            logger.warning(f"[meta_runner] {sq.title!r} — 모든 provider 실패")
            empty = empty_metadata()
            empty["_provenance"] = {}
            merged = attach_coverage(empty, [])
        else:
            merged = merge_metadata(entries, source_types, provider_names)

        # story 폴백: 병합 후 story 없고 구조화 소스 synopsis_raw 있으면 LLM 재작성
        if not merged.get("story") and synopsis_raws:
            try:
                story = await self.extractor.rewrite_story(sq.title, synopsis_raws)
                if story:
                    merged["story"] = story
                    logger.info(f"[meta_runner] {sq.title!r} — story 폴백 재작성 완료")
            except Exception as e:
                logger.warning(f"[meta_runner] story 재작성 실패: {e}")

        source_count = await self._save_sources(sq.title, all_docs)
        meta_id = await self._save_meta(sq.title, merged, source_count)

        return {
            "movie_query": sq.title,
            "metadata": merged,
            "source_count": source_count,
            "meta_id": meta_id,
            "skipped_reason": None,
            "providers_detail": providers_detail,
        }

    async def _safe_search(self, provider: SearchProvider, sq: SearchQuery) -> list:
        try:
            return await provider.search(sq)
        except Exception as e:
            logger.warning(f"[meta_runner] {provider.provider_name} 검색 실패: {e}")
            return []

    async def _save_sources(self, query: str, docs: list) -> int:
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
                logger.warning(f"[meta_runner] 소스 저장 실패 {doc.url}: {e}")
        self.db.commit()
        return count

    async def _save_meta(self, query: str, meta: dict, source_count: int) -> int | None:
        try:
            mm = MovieMeta(
                movie_query=query,
                meta_json=meta,
                llm_engine="ollama",
                source_count=source_count,
            )
            self.db.add(mm)
            self.db.commit()
            return mm.id
        except Exception as e:
            logger.error(f"[meta_runner] meta 저장 실패 {query!r}: {e}")
            self.db.rollback()
            return None
