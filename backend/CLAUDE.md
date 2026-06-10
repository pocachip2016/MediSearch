@../../CLAUDE.md

# MediSearch Backend

## 스택
- **Framework**: FastAPI
- **Browser Automation**: Playwright (기본) / Selenium (검토)
- **Web Scraping**: Scrapy (검토 중)
- **Task Queue**: Celery + Redis (선택)
- **Database**: PostgreSQL (선택)

## 데이터 흐름 (핵심 원칙 적용)
```
User Request
    ↓
[Browser Search] → HTML/Content (임시)
    ↓
[Evaluate/Extract] → SearchResult(URL, title, date, trust_score)
    ↓
[LLM Summarize] → ProcessedData(summary, fields, evaluation)
    ↓
[Save Result] ✅ / [Discard Source] ❌
    ↓
User Response
```
**원본(HTML/원문) 미저장, 평가 결과만 저장**

## 주요 모듈 (계획)
```
backend/
├── main.py                 # FastAPI 진입점
├── agents/
│   ├── web_search.py      # WebSearch 에이전트
│   └── browser.py         # Headless Browser 제어
├── scrapers/
│   ├── playwright_scraper.py
│   ├── selenium_scraper.py
│   └── scrapy_integration.py
├── pipeline/
│   ├── evaluator.py       # 정보 평가 로직
│   ├── summarizer.py      # LLM 요약
│   └── extractor.py       # 데이터 추출
├── api/
│   ├── routes/
│   │   └── search.py
│   └── models/
│       ├── search_request.py
│       ├── search_result.py
│       └── processed_data.py
├── services/
│   ├── quota_manager.py
│   ├── fallback_chain.py
│   └── result_manager.py   # 결과 저장 (원본 미저장)
└── config.py
```

## 다음 단계
1. requirements.txt 작성
2. main.py 기본 구조
3. Headless Browser 프로토타입
