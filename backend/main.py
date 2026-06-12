from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
import logging

from pipeline.evaluator import EvaluationEngine
from pipeline.metadata_extractor import MetadataExtractionEngine
from pipeline.metadata_runner import MetadataRunner
from pipeline.multi_runner import MultiSourceRunner
from pipeline.runner import PipelineRunner
from search.fixture_provider import FixtureProvider
from search.playwright_provider import PlaywrightProvider
from search.provider_factory import build_providers
from shared.database import init_db, get_db
from shared.config import settings
from shared.limiter import EvalGate, EvalBusyError

app = FastAPI(
    title="MediSearch",
    description="Headless Browser WebSearch Agent",
    version="0.1.0",
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# DB 초기화
init_db()

# Ollama 평가 직렬화 게이트 (배치 evaluate 전용)
eval_gate = EvalGate(
    max_concurrent=settings.MAX_CONCURRENT_EVALS,
    queue_timeout_s=settings.EVAL_QUEUE_TIMEOUT_S,
)

# 대화형 enrich 전용 게이트 — 배치 evaluate와 분리하여 블로킹 방지
enrich_gate = EvalGate(
    max_concurrent=1,
    queue_timeout_s=90,
)

# ── 요청/응답 모델 ────────────────────────────────────────

class MovieEvaluateRequest(BaseModel):
    # 레거시 자유 텍스트 — 구조화 필드가 없을 때 사용
    query: str | None = None
    # 구조화 필드 (ID가 있으면 title ILIKE 대신 정확 조회)
    title: str | None = None
    production_year: int | None = None
    tmdb_id: int | None = None
    kmdb_docid: str | None = None
    kobis_movie_cd: str | None = None
    original_title: str | None = None  # 영문 위키/OMDb 검색 키 (해외영화)
    imdb_id: str | None = None          # OMDb 정확 조회용 (tt1234567 형식)
    content_type: str | None = None   # "movie"|"series" 힌트 — OMDB type= 파라미터에 사용
    content_id: int | None = None  # mediaX 콘텐츠 ID — 응답에 echo
    require_namu: bool = False  # (레거시 alias) 웹 소스 없으면 평가 생략
    require_web: bool = False   # True: 나무위키/영문위키 둘 다 없으면 Ollama 평가 생략

    @model_validator(mode="after")
    def require_title_or_query(self) -> "MovieEvaluateRequest":
        if not self.query and not self.title:
            raise ValueError("query 또는 title 중 하나는 필수입니다.")
        return self

    @property
    def need_web(self) -> bool:
        """require_web 또는 레거시 require_namu 중 하나라도 True면 웹 게이트 적용."""
        return self.require_web or self.require_namu

    def to_search_query(self) -> "SearchQuery":
        from search.base import SearchQuery
        t = self.title or self.query
        return SearchQuery(
            title=t,
            original_title=self.original_title,
            production_year=self.production_year,
            tmdb_id=self.tmdb_id,
            imdb_id=self.imdb_id,
            kmdb_docid=self.kmdb_docid,
            kobis_movie_cd=self.kobis_movie_cd,
            content_type=self.content_type,
        )


class MovieEvaluateResponse(BaseModel):
    movie_query: str
    facet: dict
    source_count: int
    facet_id: int | None = None
    content_id: int | None = None
    error: str | None = None
    skipped_reason: str | None = None  # "no_web": 웹 소스 없어 평가 생략
    sources_detail: list[dict] | None = None  # provider별 {provider, docs_count, trust, confidence, evaluated}


class MovieEnrichRequest(BaseModel):
    """메타 보강 요청 — evaluate와 동일 필드 + content_type 힌트."""
    query: str | None = None
    title: str | None = None
    production_year: int | None = None
    tmdb_id: int | None = None
    kmdb_docid: str | None = None
    kobis_movie_cd: str | None = None
    original_title: str | None = None
    imdb_id: str | None = None
    content_id: int | None = None
    content_type: str | None = None  # "movie"|"series" 힌트
    require_web: bool = False
    fast: bool = False  # True: 구조화 provider(tmdb/kmdb/omdb)만 사용, LLM 0회, ~1.5s

    @model_validator(mode="after")
    def require_title_or_query(self) -> "MovieEnrichRequest":
        if not self.query and not self.title:
            raise ValueError("query 또는 title 중 하나는 필수입니다.")
        return self

    def to_search_query(self) -> "SearchQuery":
        from search.base import SearchQuery
        t = self.title or self.query
        return SearchQuery(
            title=t,
            original_title=self.original_title,
            production_year=self.production_year,
            tmdb_id=self.tmdb_id,
            imdb_id=self.imdb_id,
            kmdb_docid=self.kmdb_docid,
            kobis_movie_cd=self.kobis_movie_cd,
            content_type=self.content_type,
        )


class MovieEnrichResponse(BaseModel):
    movie_query: str
    metadata: dict
    source_count: int
    meta_id: int | None = None
    content_id: int | None = None
    error: str | None = None
    skipped_reason: str | None = None
    sources_detail: list[dict] | None = None


# ── 라우트 ────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "MediSearch"}


@app.get("/api/stats")
async def stats(db: Session = Depends(get_db)):
    """평가 통계 + DB 행 수."""
    from models import SearchSource, MovieFacet
    from datetime import datetime

    source_count = db.query(SearchSource).count()
    facet_count = db.query(MovieFacet).count()

    return {
        "service": "MediSearch",
        "timestamp": datetime.utcnow().isoformat(),
        "sources_total": source_count,
        "facets_total": facet_count,
    }


@app.get("/")
async def root():
    return {"message": "MediSearch API v0.1.0", "docs": "/docs"}


@app.post("/api/movies/evaluate")
async def evaluate_movie(
    req: MovieEvaluateRequest,
    db=Depends(get_db),
):
    """영화 평가 파이프라인 실행: search → evaluate → save."""
    evaluator = EvaluationEngine()

    provider_names = [p.strip() for p in settings.SEARCH_PROVIDERS.split(",") if p.strip()]
    if provider_names:
        # 멀티소스 앙상블
        providers = build_providers(provider_names)
        runner: PipelineRunner | MultiSourceRunner = MultiSourceRunner(providers, evaluator, db)
    else:
        # 단일 provider (기존 경로)
        if settings.SEARCH_PROVIDER == "playwright":
            search_provider = PlaywrightProvider(headless=True, timeout_ms=15000)
        else:
            search_provider = FixtureProvider()
        runner = PipelineRunner(search_provider, evaluator, db)

    sq = req.to_search_query()

    try:
        async with eval_gate:
            result = await runner.run(sq, require_namu=req.need_web)
    except EvalBusyError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail="Evaluation queue timeout — server busy",
        )

    return MovieEvaluateResponse(
        **result,
        content_id=req.content_id,
        sources_detail=result.get("providers_detail")
    )


@app.post("/api/movies/enrich", response_model=MovieEnrichResponse)
async def enrich_movie(req: MovieEnrichRequest, db=Depends(get_db)):
    """멀티소스 앙상블로 영화/시리즈 기본 메타 보강.

    mediaX 캐시 미스 시 메타 보완용. 구조화 provider(omdb/tmdb/kmdb)는 LLM 없이
    직접 추출, 텍스트 provider(namu/wiki/kowiki)는 Ollama 추출.
    """
    provider_names_str = settings.SEARCH_PROVIDERS or settings.SEARCH_PROVIDER
    all_names = [p.strip() for p in provider_names_str.split(",") if p.strip()]
    # fast=True: 구조화(로컬DB+외부구조화) provider만 — LLM 0회, ~1.5s
    _STRUCTURED = {"tmdb", "kmdb", "omdb"}
    provider_names = [n for n in all_names if n in _STRUCTURED] if req.fast else all_names
    providers = build_providers(provider_names)

    extractor = MetadataExtractionEngine()
    runner = MetadataRunner(providers, extractor, db)

    sq = req.to_search_query()

    try:
        async with enrich_gate:
            result = await runner.run(sq, require_web=req.require_web)
    except EvalBusyError:
        raise HTTPException(
            status_code=429,
            detail="Evaluation queue timeout — server busy",
        )
    except Exception as e:
        return MovieEnrichResponse(
            movie_query=sq.title,
            metadata={},
            source_count=0,
            content_id=req.content_id,
            error=str(e),
        )

    return MovieEnrichResponse(
        movie_query=result["movie_query"],
        metadata=result["metadata"],
        source_count=result["source_count"],
        meta_id=result.get("meta_id"),
        content_id=req.content_id,
        skipped_reason=result.get("skipped_reason"),
        sources_detail=result.get("providers_detail"),
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
