# MediSearch — TODO

## Now
- [ ] 데이터 파이프라인 & DB 스키마 설계 (원본 미저장 원칙 반영)
  - SearchResult 테이블: url, title, published_at, trust_score, source
  - ProcessedData 테이블: summary, extracted_fields, evaluation_score, search_result_id
- [ ] Headless Browser 라이브러리 선택 (Playwright vs Selenium)
- [ ] 기본 검색 요청 프로토콜 설계

## Next
- [ ] Scrapy 통합 검토
- [ ] WebSearch 에이전트 프로토타입
- [ ] 기본 API 엔드포인트 구현

## Later
- [ ] QuotaManager 구현
- [ ] 폴백 체인 (Brave → SerpAPI → Custom Scraper → Ollama)
- [ ] 모니터링 대시보드
- [ ] 테스트 스윽
- [ ] Docker 컨테이너화

## Done
