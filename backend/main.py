from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import logging

from pipeline.evaluator import EvaluationEngine
from pipeline.multi_runner import MultiSourceRunner
from pipeline.runner import PipelineRunner
from search.fixture_provider import FixtureProvider
from search.playwright_provider import PlaywrightProvider
from search.provider_factory import build_providers
from shared.database import init_db, get_db
from shared.config import settings

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


# ── 요청/응답 모델 ────────────────────────────────────────

class MovieEvaluateRequest(BaseModel):
    query: str


class MovieEvaluateResponse(BaseModel):
    movie_query: str
    facet: dict
    source_count: int
    facet_id: int | None = None
    error: str | None = None


# ── 라우트 ────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "MediSearch"}


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

    result = await runner.run(req.query)
    return MovieEvaluateResponse(**result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
