"""MediSearch 저장 모델.

핵심 원칙: 검색 → 평가 → 생성 → **원본 폐기**.
- SearchSource: 검색 소스의 *메타데이터만* 저장. 원문(HTML/본문) 컬럼 없음 (의도적).
- MovieFacet: 로컬 평가로 생성된 facet(Content Understanding Profile)만 저장.
"""
from datetime import datetime
import enum

from sqlalchemy import (
    Column, DateTime, Enum, Float, Integer, JSON, String, Text,
)

from shared.database import Base


class SourceType(str, enum.Enum):
    """검색 소스 분류."""
    synopsis = "synopsis"          # 줄거리
    expert_review = "expert_review"  # 전문가 감상평
    user_review = "user_review"    # 일반 감상평
    other = "other"


class SearchSource(Base):
    """검색된 소스의 메타데이터 (원문 미저장).

    원본 텍스트는 파이프라인 통과 후 폐기되며, 재필요 시 url로 재검색한다.
    """
    __tablename__ = "search_sources"

    id = Column(Integer, primary_key=True)
    movie_query = Column(String(300), index=True, nullable=False)
    url = Column(String(1000), nullable=False)
    title = Column(String(500), nullable=True)
    source_domain = Column(String(200), nullable=True)  # e.g. imdb.com, namu.wiki
    source_type = Column(Enum(SourceType), default=SourceType.other, nullable=False)
    trust_score = Column(Float, default=1.0)  # 0.0~1.0
    retrieved_at = Column(DateTime, default=datetime.utcnow)
    # NOTE: 원문 텍스트 컬럼 없음 — 원본 미저장 원칙


class MovieFacet(Base):
    """로컬 평가로 생성된 영화 facet (생성 데이터만 저장)."""
    __tablename__ = "movie_facets"

    id = Column(Integer, primary_key=True)
    movie_query = Column(String(300), index=True, nullable=False)
    facet_json = Column(JSON, nullable=False)  # validate_movie_facet 통과 결과
    sentiment_score = Column(Float, nullable=True)  # 0.0~1.0
    llm_engine = Column(String(50), nullable=True)  # 사용된 엔진명
    source_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class MovieMeta(Base):
    """멀티소스 앙상블로 보강한 영화/시리즈 기본 메타 (생성 데이터만 저장).

    원문 시놉시스 저장 안 함 — story(≤60자 재작성)만.
    """
    __tablename__ = "movie_meta"

    id = Column(Integer, primary_key=True)
    movie_query = Column(String(300), index=True, nullable=False)
    meta_json = Column(JSON, nullable=False)   # validate_metadata 통과 결과
    llm_engine = Column(String(50), nullable=True)
    source_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
