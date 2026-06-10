"""shared/mediax_db.py — mediaX Postgres 읽기 전용 연결.

TMDB/KMDb 캐시 테이블을 raw SQL로만 읽는다 (mediaX 모델 import 금지 → 결합도 최소).
연결 실패 시 None 세션을 반환해 provider가 graceful하게 빈 결과를 내도록 한다.

Docker 컨테이너에서는 host.docker.internal, 호스트 직접 실행 시 localhost로
자동 폴백한다.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from shared.config import settings

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_SessionFactory: Optional[sessionmaker] = None
_init_failed = False


def _candidate_urls() -> list[str]:
    """설정 URL + host.docker.internal↔localhost 폴백 후보."""
    primary = settings.MEDIAX_DATABASE_URL
    urls = [primary]
    if "host.docker.internal" in primary:
        urls.append(primary.replace("host.docker.internal", "localhost"))
    elif "localhost" in primary:
        urls.append(primary.replace("localhost", "host.docker.internal"))
    return urls


def _init_engine() -> Optional[sessionmaker]:
    """엔진/세션 팩토리 lazy 초기화. 실패 시 None (한 번만 시도)."""
    global _engine, _SessionFactory, _init_failed

    if _SessionFactory is not None:
        return _SessionFactory
    if _init_failed:
        return None

    for url in _candidate_urls():
        try:
            engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_recycle=300,
                connect_args={"connect_timeout": 5},
            )
            # 연결 검증
            with engine.connect():
                pass
            _engine = engine
            _SessionFactory = sessionmaker(
                autocommit=False, autoflush=False, bind=engine
            )
            logger.info(f"[mediax_db] 연결 성공: {url.split('@')[-1]}")
            return _SessionFactory
        except Exception as e:
            logger.warning(f"[mediax_db] 연결 실패 ({url.split('@')[-1]}): {e}")

    _init_failed = True
    logger.error("[mediax_db] 모든 후보 URL 연결 실패 — mediaX 소스 비활성")
    return None


def get_mediax_session() -> Optional[Session]:
    """mediaX 읽기 전용 세션 반환. 연결 불가 시 None.

    호출자는 None 체크 후 빈 결과를 반환해야 한다 (graceful degradation).
    사용 후 반드시 close() 할 것.
    """
    factory = _init_engine()
    if factory is None:
        return None
    return factory()


def reset_mediax_engine() -> None:
    """테스트용 — 엔진 캐시 초기화."""
    global _engine, _SessionFactory, _init_failed
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None
    _init_failed = False
