"""검색 계층 — SourceDocument + SearchProvider ABC (mediaX 패턴 차용).

SourceDocument.text는 파이프라인 통과용 임시 필드 → DB 저장 안 함.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum


class SourceType(str, Enum):
    """검색 소스 분류."""
    synopsis = "synopsis"
    expert_review = "expert_review"
    user_review = "user_review"
    other = "other"


@dataclass
class SearchQuery:
    """구조화된 검색 요청. ID가 있으면 title ILIKE 대신 정확 조회에 사용."""
    title: str
    production_year: int | None = None
    tmdb_id: int | None = None
    kmdb_docid: str | None = None
    kobis_movie_cd: str | None = None

    @classmethod
    def from_text(cls, text: str) -> "SearchQuery":
        return cls(title=text)


@dataclass
class SourceDocument:
    """검색 결과 문서 (파이프라인 통과용).

    text는 파이프라인 내 평가/요약에 사용되지만, DB에는 저장되지 않음.
    (원본 미저장 원칙)
    """
    url: str
    title: str
    text: str  # 파이프라인 임시 필드 → 저장 안 함
    source_domain: str  # e.g. "imdb.com", "namu.wiki"
    source_type: SourceType = SourceType.other
    trust_score: float = 1.0  # 0.0~1.0


class SearchProvider(ABC):
    """검색 제공자 추상 기본 클래스 (mediaX WebSearchProvider 패턴)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """제공자 식별자 (e.g., 'fixture', 'playwright')."""
        pass

    @abstractmethod
    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """영화 검색 → SourceDocument 리스트 반환.

        Args:
            query: 구조화된 검색 요청 (ID 필드 있으면 정확 조회)
            num: 반환할 최대 결과 수
        """
        pass
