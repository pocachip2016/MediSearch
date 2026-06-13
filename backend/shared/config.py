"""전역 설정 — pydantic-settings 기반 환경변수 관리."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # MediSearch own tables (ms_*) — same media_ax DB, PostgreSQL
    DATABASE_URL: str = (
        "postgresql+psycopg2://media_ax:x31sFEebPbyFtHMf7S6O1Ost@host.docker.internal:5432/media_ax"
    )

    # mediaX Postgres (읽기 전용) — TMDB/KMDb 캐시 소스
    # Docker 컨테이너 → host.docker.internal, 호스트 직접 실행 → localhost
    MEDIAX_DATABASE_URL: str = (
        "postgresql+psycopg2://media_ax:media_ax@host.docker.internal:5432/media_ax"
    )

    # Search 계층 (단일) — fixture | playwright
    SEARCH_PROVIDER: str = "fixture"  # "playwright"로 변경 시 실제 웹 크롤링
    # 앙상블 멀티소스 (콤마 구분) — 비우면 SEARCH_PROVIDER 단일 동작
    # 예: "tmdb,kmdb,playwright"
    SEARCH_PROVIDERS: str = ""

    # 트랙 분리 — 대화형(즉답) vs backfill(배치)
    # INTERACTIVE: playwright 제외 — 빠른 구조화+API provider만 (~1–2초)
    INTERACTIVE_PROVIDERS: str = "tmdb,kmdb,omdb,wikipedia,kowiki"
    # BACKFILL: 전체 포함 (playwright+Ollama) — 배치 워커 전용
    BACKFILL_PROVIDERS: str = "tmdb,kmdb,playwright,wikipedia,kowiki,omdb"

    # LLM — Ollama 로컬 (POC 기본)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:4b"
    # 구조화 태스크(facet 추출/분류) 전용 — reasoning 모델(qwen3) 회피
    OLLAMA_TASK_MODEL: str = "qwen2.5:7b"
    # 평가 엔진 폴백 체인 (콤마 구분) — 향후 무료 LLM 추가 자리
    LLM_ENGINE: str = "ollama"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # 동시성/throttle — Ollama/Namu.wiki 부하 제어
    MAX_CONCURRENT_EVALS: int = 1  # Ollama 직렬화 (1 = 완전 직렬)
    EVAL_QUEUE_TIMEOUT_S: int = 300  # 대기열 타임아웃 (초과 시 429)
    NAMU_MIN_INTERVAL_S: float = 20.0  # Namu.wiki 최소 간격 (초/요청)
    WIKI_MIN_INTERVAL_S: float = 1.0   # en.wikipedia.org API 최소 간격 (초/요청)
    WIKI_TIMEOUT_S: float = 10.0       # Wikipedia API 요청 타임아웃
    KO_WIKI_MIN_INTERVAL_S: float = 1.0
    KO_WIKI_TIMEOUT_S: float = 10.0
    OMDB_API_KEY: str = ""
    OMDB_DAILY_QUOTA: int = 1000       # 무료 tier 하루 한도
    OMDB_MIN_INTERVAL_S: float = 1.0
    OMDB_TIMEOUT_S: float = 10.0


settings = Settings()
