"""전역 설정 — pydantic-settings 기반 환경변수 관리."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database — POC 로컬 기본 SQLite
    DATABASE_URL: str = "sqlite:///./medisearch_dev.db"

    # Search 계층 — fixture | playwright
    SEARCH_PROVIDER: str = "fixture"  # "playwright"로 변경 시 실제 웹 크롤링

    # LLM — Ollama 로컬 (POC 기본)
    OLLAMA_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen3:4b"
    # 구조화 태스크(facet 추출/분류) 전용 — reasoning 모델(qwen3) 회피
    OLLAMA_TASK_MODEL: str = "qwen2.5:3b"
    # 평가 엔진 폴백 체인 (콤마 구분) — 향후 무료 LLM 추가 자리
    LLM_ENGINE: str = "ollama"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()
