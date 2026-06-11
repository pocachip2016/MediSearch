@../CLAUDE.md

# MediSearch — 영화 Facet 파이프라인 에이전트

## 프로젝트 구조
```
MediSearch/
├── backend/          # FastAPI + 멀티소스 앙상블 파이프라인 (Python)
│   ├── search/       # SearchProvider ABC + 6개 provider
│   ├── pipeline/     # MultiSourceRunner + EvaluationEngine + facet merge
│   ├── shared/       # config, mediax_db, quota, limiter
│   ├── models.py     # SearchSource + MovieFacet (SQLAlchemy)
│   └── main.py       # FastAPI 진입점
├── docs/             # 설계 문서
└── docker-compose.yml
```

## 목표
멀티소스 앙상블 기반 영화 facet 추출 파이프라인.
여러 provider에서 수집한 문서를 Ollama LLM으로 평가 후 신뢰도 가중 병합.

## 핵심 원칙
**파이프라인**: 검색 → 평가 → 병합 → 원본 폐기

- **원본 미저장**: 검색된 원본(HTML, 원문) 저장 안 함
- **저장 대상**: 메타데이터(URL, 제목, 신뢰도) + 평가 결과(facet JSON)
- **앙상블**: 복수 provider 결과를 trust_score 가중 병합

## 빠른 시작 (Docker)
```bash
docker compose up          # port 8080
# 또는 로컬 개발
cd backend && uvicorn main:app --reload  # port 8000
```

## Provider 구성 (SEARCH_PROVIDERS)
| provider | 소스 | 신뢰도 | 비고 |
|----------|------|-------|------|
| `tmdb` | mediaX TMDB 캐시 DB | ~0.95 | vote_count 반영 |
| `kmdb` | mediaX KMDb 캐시 DB | 0.85 | 한국영화 공식 메타 |
| `playwright` | 나무위키 Headless | 0.85 | 동음이의어 자동 탐색 |
| `wikipedia` | 영문 위키 API | 0.75 | original_title 사용 |
| `kowiki` | 한국어 위키 API | 0.80 | disambiguation 필터 |
| `omdb` | OMDb API (IMDb) | 0.82 | 1000req/일, imdb_id 우선 |

docker-compose 기본값: `SEARCH_PROVIDERS=tmdb,kmdb,playwright,wikipedia,kowiki,omdb`

## API

### POST /api/movies/evaluate
```json
{
  "title": "올드보이",
  "production_year": 2003,
  "tmdb_id": 670,
  "imdb_id": "tt0364569",
  "original_title": "Oldboy",
  "require_web": false
}
```

응답에 `sources_detail` 포함:
```json
{
  "facet": {...},
  "sources_detail": [
    {"provider": "kowiki", "docs_count": 1, "trust": 0.80, "confidence": 0.7, "evaluated": true}
  ]
}
```

## 아키텍처 요약
```
POST /api/movies/evaluate
    ↓
MultiSourceRunner.run()
    Phase 1: 모든 provider 병렬 검색
    Phase 2: provider별 Ollama 평가 (EvaluationEngine)
    merge_facets() → trust 가중 병합
    ↓
SaveSources + SaveFacet (메타만 저장)
    ↓
MovieEvaluateResponse (facet + sources_detail)
```

## Facet 스키마
- **enum 5**: primary_genre / conflict / ending_type / pacing_reaction / ending_reaction
- **vocab list 4**: sub_genre / theme / mood / emotional_aftertaste
- **score 11**: tension / immersion / boredom_risk / rewatch_value / attention / emotional_energy / violence / gore / sexual / spoiler / sentiment
- **파생**: safety_flags (is_violent/is_gory/is_sexual + age_suggestion)
- **신뢰도**: _coverage + confidence
- 상세: `docs/facet-schema.md`

## 주요 포트
FastAPI 8080 (Docker) · FastAPI 8000 (로컬) · Ollama 11434

## 환경변수 핵심
| 변수 | 기본값 | 비고 |
|------|--------|------|
| `SEARCH_PROVIDERS` | `""` | 콤마 구분, 비우면 SEARCH_PROVIDER 단일 |
| `OMDB_API_KEY` | `""` | OMDb 무료 키 필수 |
| `OMDB_DAILY_QUOTA` | `1000` | 하루 요청 한도 |
| `MEDIAX_DATABASE_URL` | `@host.docker.internal:5432` | mediaX Postgres |
| `OLLAMA_TASK_MODEL` | `qwen2.5:3b` | facet 추출 전용 |

## Where to look
- 상세 TODO: `@TODO.md`
- Facet 스키마 설계: `docs/facet-schema.md`
- verify 스크립트: `.claude/verify.sh`
