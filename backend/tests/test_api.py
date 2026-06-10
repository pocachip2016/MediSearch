"""tests/test_api.py — FastAPI 엔드포인트 테스트."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_root(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "MediSearch API" in response.json()["message"]


@patch("main.PipelineRunner")
@patch("main.EvaluationEngine")
@patch("main.FixtureProvider")
def test_evaluate_movie_success(mock_provider_cls, mock_evaluator_cls, mock_runner_cls, client):
    """POST /api/movies/evaluate 성공 케이스."""
    # mock runner 설정
    mock_runner = MagicMock()
    mock_runner.run = AsyncMock(return_value={
        "movie_query": "기생충",
        "facet": {
            "primary_genre": "드라마",
            "tension": 0.8,
        },
        "source_count": 2,
        "facet_id": 1,
    })
    mock_runner_cls.return_value = mock_runner

    response = client.post("/api/movies/evaluate", json={"query": "기생충"})
    assert response.status_code == 200
    data = response.json()
    assert data["movie_query"] == "기생충"
    assert data["source_count"] == 2
    assert data["facet_id"] == 1
