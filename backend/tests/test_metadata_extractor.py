"""tests/test_metadata_extractor.py — MetadataExtractionEngine 단위 테스트.

httpx mock 패턴은 test_evaluator.py 방식과 동일:
  patch("pipeline.ollama_client.httpx.AsyncClient")
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from pipeline.metadata_extractor import MetadataExtractionEngine
from search.base import SearchQuery, SourceDocument, SourceType


# ── 픽스처 헬퍼 ─────────────────────────────────────────────
def _doc(text="나무위키 영화 본문...", source_type=SourceType.synopsis):
    return SourceDocument(
        url="https://namu.wiki/w/기생충",
        title="기생충",
        text=text,
        source_domain="namu.wiki",
        source_type=source_type,
        trust_score=0.85,
    )


def _mock_ollama(response_dict: dict):
    """Ollama 응답 mock."""
    resp = MagicMock()
    resp.json.return_value = {"response": json.dumps(response_dict)}
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    client.post = AsyncMock(return_value=resp)
    return client


@pytest.fixture
def engine():
    return MetadataExtractionEngine(model="test-model", base_url="http://localhost:11434")


# ── extract() ────────────────────────────────────────────────
class TestExtract:
    @pytest.mark.asyncio
    async def test_empty_docs_returns_empty(self, engine):
        result = await engine.extract("기생충", [])
        assert result["content_type"] is None
        assert result["genres"] == []

    @pytest.mark.asyncio
    async def test_llm_response_validated(self, engine):
        llm_out = {
            "content_type": "movie",
            "production_year": 2019,
            "genres": ["Drama", "Thriller"],  # 영문 → validate에서 그대로 통과
            "directors": ["봉준호"],
            "cast": [{"name": "송강호", "role": "기택"}],
            "story": "반지하 가족의 계급 투쟁",
            "countries": ["South Korea"],
        }
        client = _mock_ollama(llm_out)
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.extract("기생충", [_doc()])

        assert result["content_type"] == "movie"
        assert result["production_year"] == 2019
        assert result["directors"] == ["봉준호"]
        assert result["cast"][0]["name"] == "송강호"
        assert result["cast"][0]["role"] == "기택"
        assert result["story"] == "반지하 가족의 계급 투쟁"

    @pytest.mark.asyncio
    async def test_llm_none_returns_empty(self, engine):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=Exception("connection refused"))
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.extract("기생충", [_doc()])
        assert result["content_type"] is None

    @pytest.mark.asyncio
    async def test_story_clamped_to_60(self, engine):
        long_story = "x" * 100
        llm_out = {"story": long_story}
        client = _mock_ollama(llm_out)
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.extract("무제", [_doc()])
        assert len(result["story"]) <= 60

    @pytest.mark.asyncio
    async def test_series_fields_extracted(self, engine):
        llm_out = {
            "content_type": "series",
            "series": {
                "total_seasons": 2,
                "total_episodes": 16,
                "first_air_date": "2021-09-17",
                "air_status": "ended",
                "networks": ["Netflix"],
            }
        }
        client = _mock_ollama(llm_out)
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.extract("오징어 게임", [_doc()])
        assert result["content_type"] == "series"
        assert result["series"]["total_seasons"] == 2
        assert result["series"]["air_status"] == "ended"


# ── rewrite_story() ──────────────────────────────────────────
class TestRewriteStory:
    @pytest.mark.asyncio
    async def test_empty_texts_returns_none(self, engine):
        result = await engine.rewrite_story("기생충", [])
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_story_string(self, engine):
        llm_out = {"story": "반지하 4인 가족의 사기와 계급 갈등"}
        client = _mock_ollama(llm_out)
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.rewrite_story("기생충", ["긴 시놉시스 텍스트..."])
        assert result == "반지하 4인 가족의 사기와 계급 갈등"

    @pytest.mark.asyncio
    async def test_story_clamped_to_60(self, engine):
        llm_out = {"story": "x" * 100}
        client = _mock_ollama(llm_out)
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.rewrite_story("무제", ["텍스트"])
        assert result is not None
        assert len(result) <= 60

    @pytest.mark.asyncio
    async def test_llm_failure_returns_none(self, engine):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=None)
        client.post = AsyncMock(side_effect=Exception("timeout"))
        with patch("pipeline.ollama_client.httpx.AsyncClient", return_value=client):
            result = await engine.rewrite_story("무제", ["텍스트"])
        assert result is None
