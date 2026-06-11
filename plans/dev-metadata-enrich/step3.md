# Step 3: meta-step3-merge — trust 가중 메타 병합

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/pipeline/facet_merge.py (_mad_filter, _LIST_TRUST_RATIO 패턴)
- backend/pipeline/metadata_schema.py

## 작업
- 신규 `backend/pipeline/metadata_merge.py`: `merge_metadata(entries: list[tuple[dict, float]], source_types) -> dict`
  - content_type/air_status/total_seasons/total_episodes/production_year: 정확값 trust 합 투표
  - runtime_minutes: MAD 필터 → trust 가중 중앙값
  - genres/countries/directors: Σtrust ≥ 34% 채택 (정규화 맵 적용 후)
  - cast: trust 내림차순 union, name exact dedup (ko/en 교차 매칭 안 함)
  - story/original_title/first_air_date/last_air_date: best-trust
  - keywords: 빈도 상위 N
  - networks: union
  - `_provenance`: field→[provider명] 자동 생성
  - `attach_coverage` 재사용
- 신규 `tests/test_metadata_merge.py` (test_facet_merge.py 스타일)

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step3
```

## 금지사항
- 연도/시즌 수 평균 계산 금지. 이유: 범주값 — 투표만.
- facet_merge.py 동작 변경 금지 (import 재사용만).
