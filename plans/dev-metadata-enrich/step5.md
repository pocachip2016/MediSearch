# Step 5: meta-step5-runner — MetadataRunner

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/pipeline/multi_runner.py (러너 구조 원형)
- backend/tests/test_multi_runner.py (픽스처 패턴)

## 작업
- 신규 `backend/pipeline/metadata_runner.py`: `MetadataRunner.run(query, require_web=False) -> dict`
  - Phase 1: provider 병렬 검색 (multi_runner 동일 패턴)
  - Phase 2: doc.meta 있으면 validate_metadata(meta) 직접 채택 (LLM 미호출); 텍스트 doc만 extractor.extract (EvalGate 직렬)
  - story 폴백: 병합 후 story가 없고 synopsis_raw 후보가 있으면 rewrite_story 1회 호출
  - Phase 3: merge_metadata → _save_sources(SearchSource 재사용) + _save_meta(MovieMeta)
  - require_web 게이트 동일 지원 (skipped_reason="no_web")
- 신규 `tests/test_metadata_runner.py` — 핵심 단언: meta 있는 doc은 extractor 미호출 / 병합·저장 / providers_detail / no_web 조기 종료 / story 폴백 호출 조건

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step5
```

## 금지사항
- synopsis_raw·doc.text DB 저장 금지. 이유: 원본 미저장 — story(30자)만 저장.
- MultiSourceRunner 수정 금지. 이유: facet 흐름 격리.
