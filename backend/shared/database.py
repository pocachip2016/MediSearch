"""SQLAlchemy 엔진·세션·Base·get_db DI (mediaX shared/database.py 패턴)."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from shared.config import settings

_url = settings.DATABASE_URL
_kwargs = {}
if _url.startswith("sqlite"):
    _kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """모든 모델을 import한 뒤 테이블 생성 (POC 부트스트랩)."""
    import models  # noqa: F401  (모델 등록 트리거)

    Base.metadata.create_all(bind=engine)
