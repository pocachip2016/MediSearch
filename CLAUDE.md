@../CLAUDE.md

# MediSearch — Headless Browser WebSearch Agent

## 프로젝트 구조
```
MediSearch/
├── backend/          # FastAPI + Headless Browser + Scrapy (Python)
├── docs/             # 설계 문서
└── docker-compose.yml
```

## 목표
Headless 브라우저를 활용한 WebSearch 에이전트 구현. mediaX의 WebSearch 4-provider 폴백 체인을 확장하여 Brave/SerpAPI 대신 Headless 브라우저 기반 스크래핑으로 검색 결과 수집.

## 핵심 원칙
**파이프라인**: 검색 → 로컬 평가 → 요약/새 데이터 생성 → 원본 폐기

- 검색 수행: Headless Browser / Scrapy로 정보 수집
- 로컬 평가: LLM/로직으로 수집 정보 평가
- 결과 생성: 요약, 추출, 새 데이터 구조화
- **원본 미저장**: 검색된 원본 소스(HTML, 원문)는 로컬 저장 안 함
- **저장 대상**: 메타데이터(URL, 제목, 날짜, 신뢰도) + 평가 결과(요약, 추출값, 점수)

## 빠른 시작
```bash
cd backend
cp .env.example .env  # API 키 입력
pip install -r requirements.txt
uvicorn main:app --reload
```

## POC 진행 현황 (영화 facet 파이프라인)
plan: `~/.claude/plans/robust-sauteeing-pike.md`

| Step | 내용 | 상태 |
|------|------|------|
| 1 | DB 모델 부트스트랩 (SearchSource/MovieFacet, SQLite) | ✅ |
| 2 | 검색 계층 fixture (SourceDocument, SearchProvider ABC) | ✅ |
| 3 | Facet 스키마 (타입 구동, MVP 1순위 전체) | ✅ |
| 4 | 평가 엔진 (Ollama → facet JSON) | ⏳ 다음 |
| 5 | 러너 + FastAPI + CLI end-to-end | 🔜 |

## 아키텍처 요약
```
backend/
├── shared/         # config(SQLite/Ollama), database(get_db)
├── models.py       # SearchSource(메타만) + MovieFacet
├── search/         # SearchProvider ABC + FixtureProvider
│   └── data/fixtures/sample_movies.json  (기생충, 씬시어리티)
└── pipeline/
    └── facets.py   # validate_movie_facet / facet_overlap_score
                    # safety_flags / coverage+confidence
```

## Facet 스키마 (1순위 MVP)
- **enum 5**: primary_genre / conflict / ending_type / pacing_reaction / ending_reaction
- **vocab list 4**: sub_genre / theme / mood / emotional_aftertaste
- **score 11**: tension / immersion / boredom_risk / rewatch_value / attention / emotional_energy / violence / gore / sexual / spoiler / sentiment
- **파생**: safety_flags (is_violent/is_gory/is_sexual + age_suggestion)
- **신뢰도**: _coverage + confidence (원본 폐기 원칙 보완)
- 상세: `docs/facet-schema.md`

## Step 4 시작 체크리스트
```bash
ollama list | grep llama3.2  # 모델 확인 (없으면 ollama pull llama3.2:3b)
cd ~/Work/MediSearch/backend
python3 -c "from pipeline.facets import validate_movie_facet; print('OK')"
```

## 주요 포트
FastAPI 8000 · Redis 6379 (선택) · Ollama 11434

## Where to look
- 상세 TODO: `@TODO.md`
- Facet 스키마 설계: `docs/facet-schema.md`
- POC plan: `~/.claude/plans/robust-sauteeing-pike.md`
