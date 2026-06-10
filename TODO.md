# MediSearch — TODO

## Now
- [ ] Playwright 실제 크롤링 검증 (Namu.Wiki 셀렉터 확인 + 다양한 영화 테스트)
- [ ] score 필드 정확도 개선 (qwen2.5:7b few-shot 프롬프트 튜닝)
- [ ] mediaX 연동 (MediSearch → mediaX WebSearch 폴백 체인 통합)

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
- [x] 데이터 파이프라인 & DB 스키마 설계 (SearchSource/MovieFacet, SQLite, 원본 미저장 원칙)
- [x] Headless Browser 라이브러리 선택 → Playwright 채택
- [x] 기본 검색 요청 프로토콜 설계 (SearchProvider ABC + POST /api/movies/evaluate)
- [x] EvaluationEngine (Ollama qwen2.5:7b, few-shot 프롬프트, score 11개 추출)
- [x] PipelineRunner end-to-end (search→evaluate→save)
- [x] Docker 배포 (port 8080, docker-compose)
