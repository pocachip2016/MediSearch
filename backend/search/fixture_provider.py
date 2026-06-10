"""POC용 고정 fixture 검색 제공자.

data/fixtures/*.json에서 샘플 데이터 로드.
실제 headless browser는 동일 SearchProvider 인터페이스로 교체.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType

logger = logging.getLogger(__name__)

# fixtures 디렉토리 경로
FIXTURES_DIR = Path(__file__).parent.parent / "data" / "fixtures"


class FixtureProvider(SearchProvider):
    """고정 샘플 데이터 기반 검색 제공자."""

    def __init__(self):
        self.data: Dict[str, List[dict]] = {}
        self._load_fixtures()

    def _load_fixtures(self) -> None:
        """data/fixtures/*.json 로드."""
        if not FIXTURES_DIR.exists():
            logger.warning(f"Fixtures 디렉토리 없음: {FIXTURES_DIR}")
            return

        for json_file in FIXTURES_DIR.glob("*.json"):
            try:
                with open(json_file) as f:
                    data = json.load(f)
                    # data 형식: {movie_title: [{...source...}, ...]}
                    self.data.update(data)
                logger.info(f"✓ Fixture 로드: {json_file.name}")
            except Exception as e:
                logger.error(f"❌ Fixture 로드 실패 {json_file}: {e}")

    @property
    def provider_name(self) -> str:
        return "fixture"

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """영화 제목으로 fixture 데이터 반환."""
        sources = self.data.get(query.title, [])

        if not sources:
            logger.warning(f"Fixture 데이터 없음: {query.title}")
            return []

        # num 개까지 반환
        docs = []
        for src in sources[:num]:
            doc = SourceDocument(
                url=src.get("url", ""),
                title=src.get("title", ""),
                text=src.get("text", ""),
                source_domain=src.get("source_domain", ""),
                source_type=SourceType(src.get("source_type", "other")),
                trust_score=float(src.get("trust_score", 1.0)),
            )
            docs.append(doc)

        logger.info(f"✓ Fixture 검색: {query.title} → {len(docs)}개 결과")
        return docs
