# Step 6: meta-step6-api — /api/movies/enrich 엔드포인트 + 문서

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/main.py (evaluate 엔드포인트 패턴)
- backend/tests/test_api.py

## 작업
- `main.py`: `MovieEnrichRequest(MovieEvaluateRequest 필드 + content_type)`, `MovieEnrichResponse(movie_query, metadata, source_count, meta_id, content_id, sources_detail, skipped_reason, error)`, `POST /api/movies/enrich` 라우트 (eval_gate/429 동일)
- `tests/test_api.py`: enrich 케이스 추가 (mock runner 패턴)
- `.claude/verify.sh`: meta-step1~6 케이스 정리
- `CLAUDE.md`: API 섹션에 enrich 추가, OLLAMA_TASK_MODEL 표기 7b 현행화
- `TODO.md`: Done 반영

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step6
```

## 금지사항
- 신규 docs 파일 생성 금지. 이유: 워크스페이스 규칙 — 기존 문서 갱신만.
