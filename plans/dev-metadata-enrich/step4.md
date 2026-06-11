# Step 4: meta-step4-extractor — Ollama 공용화 + LLM 추출/스토리 재작성 엔진

> GitHub: 미생성 | Milestone: dev-metadata-enrich

## 읽어야 할 파일
- backend/pipeline/evaluator.py (_call_ollama, _build_prompt 패턴)
- backend/tests/test_evaluator.py (httpx mock 패턴)

## 작업
- 신규 `backend/pipeline/ollama_client.py`: `async generate_json(prompt, model=None, num_predict=1024, temperature=0.0) -> dict|None` (evaluator._call_ollama 로직 이동)
- 수정 `evaluator.py`: `_call_ollama` → ollama_client 위임 (test_evaluator.py patch 경로 갱신)
- 신규 `backend/pipeline/metadata_extractor.py`: `MetadataExtractionEngine`
  - `extract(title, docs) -> dict` — 텍스트 소스에서 메타 추출. 프롬프트 핵심: **추정·일반지식 보충 절대 금지**, 텍스트 명시 정보만, 없으면 null. story 필드: "줄거리를 30자 내외 한국어 한 문장으로 재작성"
  - `rewrite_story(title, texts: list[str]) -> str|None` — 구조화 소스만 응답한 경우 폴백: synopsis_raw 모음 → 30자 내외 스토리 재작성 (1회 호출)
  - 모델: settings.OLLAMA_TASK_MODEL (운영 qwen2.5:7b)
- 신규 `tests/test_metadata_extractor.py`

## Acceptance Criteria
```bash
bash .claude/verify.sh meta-step4
```

## 금지사항
- facet 프롬프트(추정 허용) 스타일 재사용 금지. 이유: 메타는 환각이 치명적 — 추출 전용 규칙.
