# MediSearch — TODO

## Now

## Next
- [ ] PostgreSQL 전환 (현재 SQLite POC → 프로덕션 DB)
- [ ] Scrapy 통합 검토
- [ ] 추가 크롤러 (IMDb, Rotten Tomatoes)

## Later
- [ ] QuotaManager 구현
- [ ] 폴백 체인 (Brave → SerpAPI → Custom Scraper → Ollama)
- [ ] 모니터링 대시보드
- [ ] Docker 컨테이너화 (완료) → Kubernetes 검토

## Done
- [x] docker-compose mediaX DB 연결 (host.docker.internal + 60s retry, _init_failed 제거)
- [x] PlaywrightProvider 동음이의어 자동 서브페이지 탐색 (_DISAMBIG_JS + URL 큐 방식)
- [x] 한국어 위키백과(kowiki) + OMDb provider 추가 (커버리지 확대, DailyQuotaGuard)
- [x] no_namu → no_web 로직 확장 (playwright/wikipedia/kowiki/omdb 웹 소스 통합)
- [x] API 응답 sources_detail 추가 (provider별 docs_count/trust/confidence/evaluated)
- [x] 멀티소스 앙상블 기반 구축 (TMDB/KMDb provider + trust 가중 facet 병합 엔진, Step A+B)
- [x] Playwright 실제 크롤링 검증 (Namu.Wiki /search 차단 확인 → 직접 URL 방식으로 전환, integration 테스트 8/8)
- [x] 데이터 파이프라인 & DB 스키마 설계 (SearchSource/MovieFacet, SQLite, 원본 미저장 원칙)
- [x] Headless Browser 라이브러리 선택 → Playwright 채택
- [x] 기본 검색 요청 프로토콜 설계 (SearchProvider ABC + POST /api/movies/evaluate)
- [x] EvaluationEngine (Ollama qwen2.5:7b, few-shot 프롬프트, score 11개 추출)
- [x] PipelineRunner end-to-end (search→evaluate→save)
- [x] Docker 배포 (port 8080, docker-compose)
- [x] MultiSourceRunner + SEARCH_PROVIDERS 멀티소스 앙상블 통합 (Step C)
- [x] score 필드 정확도 개선 (few-shot 프롬프트 + 0/0.5/1 앵커 추가)
