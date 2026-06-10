# MediSearch — Design & Architecture Docs

## 핵심 원칙 (설계의 바탕)
**검색 → 평가 → 생성 → 원본 폐기**
- 원본 소스(HTML, 원문) 로컬 저장 금지
- 메타데이터(URL, 제목, 날짜, 신뢰도) 저장
- 평가 결과(요약, 추출값, LLM 점수) 저장
- 데이터 재필요 시 URL 기반 재검색

## 설계 문서 인덱스

### Phase 1: Headless Browser Foundation
- [ ] `01-browser-selection.md` — Playwright vs Selenium 선택 기준
- [ ] `02-browser-architecture.md` — Browser 추상화 계층 설계

### Phase 2: Data Pipeline (핵심)
- [ ] `03-data-pipeline.md` — 검색→평가→생성 파이프라인 & DB 스키마
- [ ] `04-models.md` — SearchResult, ProcessedData 데이터 모델

### Phase 3: Web Search Integration
- [ ] `05-websearch-agent-spec.md` — WebSearch 에이전트 스펙
- [ ] `06-scrapy-evaluation.md` — Scrapy 통합 검토 결과

### Phase 4: Fallback Chain & Quality
- [ ] `07-quota-manager-design.md` — 쿼터 관리 시스템
- [ ] `08-fallback-chain-spec.md` — Brave → SerpAPI → Custom → Ollama
- [ ] `09-evaluator-design.md` — 정보 평가 & 신뢰도 점수

### Phase 5: Monitoring
- [ ] `10-monitoring-dashboard.md` — 모니터링 대시보드 설계

## 빠른 참조
- **데이터 정책**: 원본 미저장, 메타데이터 + 결과 저장
- **Browser 제어**: 최소한의 리소스, 동시성 제어, 재시도 로직
- **Scraping 윤리**: robots.txt 준수, Rate limiting, User-Agent 헤더
- **에러 처리**: 각 단계별 폴백 체인 정의

## 작성 중인 문서
- 프로토타입 결과는 여기에 정리하세요
