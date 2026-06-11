# Step 1: meta-step1-schema — 메타 스키마 + 기반 확장

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/pipeline/facets.py (validate/empty/coverage 패턴 원형)
- backend/search/base.py
- backend/models.py

## 작업
- 신규 `backend/pipeline/metadata_schema.py`:
  - `validate_metadata(raw: dict|None) -> dict`, `empty_metadata() -> dict`
  - 필드: content_type(movie|series), original_title, production_year(1880~now+2 clamp), runtime_minutes(1~600 clamp), countries[], genres[], directors[](≤5), cast[{name,role|null}](≤10), story(≤60자 clamp — **30자 내외 LLM 재작성 스토리**, 원문 시놉시스 저장 금지), keywords[](≤8), series{total_seasons,total_episodes,first_air_date,last_air_date,air_status(ongoing|ended),networks[]}
  - 입력 raw의 `synopsis_raw` 등 임시 키는 validate에서 제거 (파이프라인 내부 전용)
  - `GENRE_NORMALIZE_MAP`(en→ko), `COUNTRY_NORMALIZE_MAP`
  - coverage는 facets.py의 `attach_coverage`/`coverage_confidence` import 재사용
- 수정 `backend/search/base.py`: `SourceDocument.meta: dict|None = None`, `SearchQuery.content_type: str|None = None`
- 수정 `backend/models.py`: `MovieMeta` 테이블 (MovieFacet 미러 — movie_query, meta_json, llm_engine, source_count, created_at)
- 신규 `tests/test_metadata_schema.py`

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step1
```

## 금지사항
- 기존 facet 흐름 동작 변경 금지. 이유: meta 필드는 기본값 None으로 무영향이어야 함.
- 긴 줄거리/시놉시스 원문 저장 금지. 이유: 원본 미저장 원칙 — 30자 내외 재작성(story)만 저장.
