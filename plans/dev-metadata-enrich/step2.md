# Step 2: meta-step2-provider-meta — 구조화 provider meta 채우기

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/search/omdb_provider.py
- backend/search/kmdb_provider.py
- backend/search/tmdb_provider.py
- backend/pipeline/metadata_schema.py (step1 산출)

## 작업
- `omdb_provider.py`: 응답 JSON → `doc.meta` 매핑 — content_type(Type), production_year(Year 앞 4자리), runtime_minutes("123 min" 파싱), genres(Genre split), directors(Director split), cast(Actors split, role null), countries(Country split), original_title(Title), synopsis_raw(Plot — 임시, 저장 안 됨), series.total_seasons(totalSeasons). `query.content_type=="series"`면 검색 `type=series` (현재 movie 하드코딩 수정).
- `kmdb_provider.py`: production_year(prod_year), countries([nation]), genres(genre split), content_type "movie", synopsis_raw(synopsis). directors 컬럼 존재 시 SELECT 추가.
- `tmdb_provider.py`: production_year(release_date.year), content_type "movie", synopsis_raw(overview).
- 텍스트 provider 3종(playwright/wikipedia/kowiki)은 무변경 (meta=None → LLM 경로).
- 기존 provider 테스트 3종에 doc.meta 단언 추가.

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step2
```

## 금지사항
- 추가 네트워크/DB 호출 금지. 이유: 이미 받은 응답에서 meta만 분기.
- doc.text 빌드 로직 변경 금지. 이유: facet 흐름 회귀 방지.
