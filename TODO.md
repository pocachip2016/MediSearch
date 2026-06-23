# MediSearch — TODO

## Now
- [ ] confidence 기반 품질 게이트 도입 검토 (현재는 source_count만 사용)

## Next
- [ ] Scrapy 통합 검토 (서버렌더 신규 소스 — IMDb 등, namu는 불가)
- [ ] 추가 크롤러 (IMDb, Rotten Tomatoes)

## Later
- [ ] QuotaManager 구현
- [ ] 폴백 체인 (Brave → SerpAPI → Custom Scraper → Ollama)
- [ ] 모니터링 대시보드
- [ ] Docker 컨테이너화 (완료) → Kubernetes 검토

## Done
- [x] **tmdb-authoritative-genre** TMDB genre_ids 노출 + metadata TMDB-first + facet 장르 그라운딩, 라이브 검증 3건 + 1,045건 백필 (2026-06-13)
- [x] **facet-confidence-contract** top-level confidence 미러 추가 — MovieEvaluateResponse + multi_runner result dict, mediaX 계약 불일치 해소 (2026-06-13)
- [x] **llm-unavailable-guard** 모델 14b→7b + OllamaUnavailableError 인프라 실패 전파 가드 (2026-06-13)
- [x] **merge-fix** trust 가중 list 병합 분모를 기여 소스로 한정 — abstain 소스 희석 제거, metadata_merge+facet_merge 동시 (2026-06-13)
- [x] **D3** mediaX tmdb_movie_meta 테이블 + copyright guard — 0053 마이그레이션, _apply_copyright_guard(story 제거) (2026-06-13)
- [x] **D2** include_meta 결합 플래그 — MultiSourceRunner.run(include_meta=True), Phase 1 docs 재사용 메타 추출 (2026-06-13)
- [x] **D1** MediSearch postgres 재빌드 — SQLite→postgres 통일, ms_* 테이블 3개 (2026-06-13)
- [x] derived-cache (facet/meta lookup, TTL 30일 — force_refresh 지원)
- [x] PostgreSQL 전환 → mediax-db-migration (ms_* 테이블 + tmdb_id 키)
- [x] SSE 스트림 엔드포인트 (POST /api/movies/{evaluate,enrich}/stream) + 프론트 UI (GET /trace, GET /ui)
- [x] **ui-2 · SSE 엔드포인트 + /trace 서빙** — `/api/movies/{evaluate,enrich}/stream` (asyncio.Queue), `/trace` FileResponse, headless 쿼리 파싱
- [x] **ui-3 · 프론트 단일 페이지** — `frontend/index.html` 폼·타임라인·EventSource·JSON viewer, 브라우저 실행 확인
- [x] 메타 보강 파이프라인 (POST /api/movies/enrich) — 하이브리드 추출(구조화 provider 직접, 텍스트 LLM), trust 가중 병합, story 30자 재작성, MovieMeta 저장
- [x] docker-compose mediaX DB 연결 (host.docker.internal + 60s retry, _init_failed 제거)
- [x] PlaywrightProvider 동음이의어 자동 서브페이지 탐색 (_DISAMBIG_JS + URL 큐 방식)
- [x] 한국어 위키백과(kowiki) + OMDb provider 추가 (커버리지 확대, DailyQuotaGuard)
- [x] no_namu → no_web 로직 확장 (playwright/wikipedia/kowiki/omdb 웹 소스 통합)
- [x] API 응답 sources_detail 추가 (provider별 docs_count/trust/confidence/evaluated)
- [x] 멀티소스 앙상블 기반 구축 (TMDB/KMDb provider + trust 가중 facet 병합 엔진, Step A+B)
- [x] **N3** 오염 스캔 스크립트 `scan_namu_contamination.py` (dry-run + `--apply`)
- [x] **N2** DDG 검색 폴백 `_resolve_via_search` — 동음이의 자동 해소, 연도 스코어링
- [x] **N1** httpx+bs4 NamuHttpProvider 신규, playwright 전면 제거, 제목 검증 게이트, 테스트 10/10
- [x] Playwright 실제 크롤링 검증 (Namu.Wiki /search 차단 확인 → 직접 URL 방식으로 전환, integration 테스트 8/8)
- [x] 데이터 파이프라인 & DB 스키마 설계 (SearchSource/MovieFacet, SQLite, 원본 미저장 원칙)
- [x] Headless Browser 라이브러리 선택 → Playwright 채택
- [x] 기본 검색 요청 프로토콜 설계 (SearchProvider ABC + POST /api/movies/evaluate)
- [x] EvaluationEngine (Ollama qwen2.5:7b, few-shot 프롬프트, score 11개 추출)
- [x] PipelineRunner end-to-end (search→evaluate→save)
- [x] Docker 배포 (port 8080, docker-compose)
- [x] MultiSourceRunner + SEARCH_PROVIDERS 멀티소스 앙상블 통합 (Step C)
- [x] score 필드 정확도 개선 (few-shot 프롬프트 + 0/0.5/1 앵커 추가)
