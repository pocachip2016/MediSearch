from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator
from sqlalchemy.orm import Session
import logging

from pipeline.evaluator import EvaluationEngine
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

# Ollama 평가 직렬화 게이트
eval_gate = EvalGate(
    max_concurrent=settings.MAX_CONCURRENT_EVALS,
    queue_timeout_s=settings.EVAL_QUEUE_TIMEOUT_S,
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
    content_id: int | None = None  # mediaX 콘텐츠 ID — 응답에 echo

    @model_validator(mode="after")
    def require_title_or_query(self) -> "MovieEvaluateRequest":
        if not self.query and not self.title:
            raise ValueError("query 또는 title 중 하나는 필수입니다.")
        return self

    def to_search_query(self) -> "SearchQuery":
        from search.base import SearchQuery
        t = self.title or self.query
        return SearchQuery(
            title=t,
            production_year=self.production_year,
            tmdb_id=self.tmdb_id,
            kmdb_docid=self.kmdb_docid,
            kobis_movie_cd=self.kobis_movie_cd,
        )


class MovieEvaluateResponse(BaseModel):
    movie_query: str
    facet: dict
    source_count: int
    facet_id: int | None = None
    content_id: int | None = None
    error: str | None = None


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
            result = await runner.run(sq)
    except EvalBusyError:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=429,
            detail="Evaluation queue timeout — server busy",
        )

    return MovieEvaluateResponse(**result, content_id=req.content_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
