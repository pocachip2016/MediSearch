"""tests/test_runner.py — PipelineRunner end-to-end 통합 테스트."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from models import MovieFacet, SearchSource
from pipeline.evaluator import EvaluationEngine
from pipeline.runner import PipelineRunner
from search.base import SearchProvider, SourceDocument, SourceType


# ── 픽스처 ─────────────────────────────────────────────────

@pytest.fixture
def mock_db():
    """Mock SQLAlchemy Session."""
    db = MagicMock(spec=Session)
    db.add = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    return db


@pytest.fixture
def mock_search_provider():
    """Mock SearchProvider."""
    provider = MagicMock(spec=SearchProvider)
    provider.provider_name = "test_provider"

    async def mock_search(query: str, num: int = 5):
        return [
            SourceDocument(
                url="https://test.com/1",
                title="Test Source 1",
                text="Test content 1",
                source_domain="test.com",
                source_type=SourceType.synopsis,
                trust_score=0.9,
            ),
            SourceDocument(
                url="https://test.com/2",
                title="Test Source 2",
                text="Test content 2",
                source_domain="test.com",
                source_type=SourceType.user_review,
                trust_score=0.8,
            ),
        ]

    provider.search = mock_search
    return provider


@pytest.fixture
def mock_evaluator():
    """Mock EvaluationEngine."""
    evaluator = MagicMock(spec=EvaluationEngine)

    async def mock_evaluate(query: str, docs):
        return {
            "primary_genre": "드라마",
            "tension": 0.8,
            "immersion": 0.9,
            "boredom_risk": 0.1,
            "rewatch_value": 0.7,
            "attention_required": 0.75,
            "emotional_energy_required": 0.6,
            "violence": 0.3,
            "gore": 0.2,
            "sexual_content": 0.0,
            "spoiler_sensitivity": 0.6,
            "sentiment_score": 0.8,
            "confidence": 0.85,
            "_coverage": {"source_count": 2},
        }

    evaluator.evaluate = mock_evaluate
    return evaluator


@pytest.fixture
def runner(mock_search_provider, mock_evaluator, mock_db):
    return PipelineRunner(mock_search_provider, mock_evaluator, mock_db)


# ── 테스트 ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_runner_full_pipeline(runner, mock_db):
    """end-to-end 파이프라인: search → evaluate → save."""
    # mock_db의 add 호출 시마다 ID 부여 (MovieFacet)
    facet_counter = 0

    def add_side_effect(obj):
        nonlocal facet_counter
        if isinstance(obj, MovieFacet):
            facet_counter += 1
            obj.id = facet_counter

    mock_db.add.side_effect = add_side_effect

    result = await runner.run("테스트영화")

    assert result["movie_query"] == "테스트영화"
    assert result["facet"]["primary_genre"] == "드라마"
    assert result["source_count"] == 2
    assert result["facet_id"] == 1
    assert "error" not in result

    # SearchSource 저장 확인 (2개)
    source_add_calls = [
        call for call in mock_db.add.call_args_list
        if isinstance(call[0][0], SearchSource)
    ]
    assert len(source_add_calls) == 2

    # MovieFacet 저장 확인
    facet_add_calls = [
        call for call in mock_db.add.call_args_list
        if isinstance(call[0][0], MovieFacet)
    ]
    assert len(facet_add_calls) == 1


@pytest.mark.asyncio
async def test_runner_evaluator_error_returns_empty_facet(runner, mock_db):
    """evaluator 오류 시 empty_facet + error 필드."""
    async def mock_error_evaluate(query, docs):
        raise ValueError("평가 엔진 오류")

    runner.evaluator.evaluate = mock_error_evaluate

    result = await runner.run("오류영화")

    assert result["movie_query"] == "오류영화"
    assert result["source_count"] == 0
    assert result["facet_id"] is None
    assert "error" in result
    assert "평가 엔진 오류" in result["error"]


@pytest.mark.asyncio
async def test_runner_save_sources_commits(runner, mock_db):
    """검색 소스 저장 후 commit 호출."""
    facet_counter = 0

    def add_side_effect(obj):
        nonlocal facet_counter
        if isinstance(obj, MovieFacet):
            facet_counter += 1
            obj.id = facet_counter

    mock_db.add.side_effect = add_side_effect

    await runner.run("커밋테스트")

    # commit 호출 확인 (최소 2회: source 저장 후 + facet 저장 후)
    assert mock_db.commit.call_count >= 2
