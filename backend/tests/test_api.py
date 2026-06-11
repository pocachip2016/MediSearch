"""tests/test_api.py — FastAPI 엔드포인트 테스트."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


def _enrich_result(**kwargs):
    base = {
        "movie_query": "기생충",
        "metadata": {
            "content_type": "movie",
            "production_year": 2019,
            "genres": ["드라마"],
            "directors": ["봉준호"],
            "cast": [{"name": "송강호", "role": "기택"}],
            "story": "반지하 가족의 계급 투쟁",
            "countries": ["한국"],
            "original_title": "Parasite",
            "runtime_minutes": 132,
            "keywords": [],
            "series": None,
            "_provenance": {"genres": ["omdb"]},
            "_coverage": {"source_count": 1, "by_type": {}, "has_expert": False, "has_user": False},
            "confidence": 0.63,
        },
        "source_count": 3,
        "meta_id": 1,
        "skipped_reason": None,
        "providers_detail": [
            {"provider": "omdb", "docs_count": 1, "trust": 0.82, "confidence": None, "evaluated": False, "structured": True}
        ],
    }
    base.update(kwargs)
    return base


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


# ── POST /api/movies/enrich ──────────────────────────────────

class TestEnrichEndpoint:
    def test_enrich_basic(self, client):
        """기본 enrich 요청 → metadata + meta_id 반환."""
        with patch("main.MetadataRunner") as MockRunner:
            runner_instance = MagicMock()
            runner_instance.run = AsyncMock(return_value=_enrich_result())
            MockRunner.return_value = runner_instance

            resp = client.post("/api/movies/enrich", json={"title": "기생충"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["movie_query"] == "기생충"
        assert data["metadata"]["content_type"] == "movie"
        assert data["metadata"]["production_year"] == 2019
        assert data["meta_id"] == 1

    def test_enrich_requires_title_or_query(self, client):
        """title/query 없으면 422."""
        resp = client.post("/api/movies/enrich", json={})
        assert resp.status_code == 422

    def test_enrich_with_content_type_hint(self, client):
        """content_type=series 힌트 SearchQuery에 전달됨."""
        with patch("main.MetadataRunner") as MockRunner:
            runner_instance = MagicMock()
            runner_instance.run = AsyncMock(return_value=_enrich_result(
                movie_query="오징어 게임",
            ))
            MockRunner.return_value = runner_instance

            resp = client.post("/api/movies/enrich", json={
                "title": "오징어 게임",
                "content_type": "series",
                "imdb_id": "tt10919420",
            })

        assert resp.status_code == 200
        # runner.run 호출 시 SearchQuery.content_type 확인
        call_sq = runner_instance.run.call_args[0][0]
        assert call_sq.content_type == "series"

    def test_enrich_no_web_skipped(self, client):
        """require_web=True + 웹소스 없으면 skipped_reason=no_web."""
        with patch("main.MetadataRunner") as MockRunner:
            runner_instance = MagicMock()
            runner_instance.run = AsyncMock(return_value=_enrich_result(
                skipped_reason="no_web", source_count=0, meta_id=None,
            ))
            MockRunner.return_value = runner_instance

            resp = client.post("/api/movies/enrich", json={
                "title": "기생충",
                "require_web": True,
            })

        assert resp.status_code == 200
        assert resp.json()["skipped_reason"] == "no_web"

    def test_enrich_content_id_passed_through(self, client):
        """content_id는 응답에 그대로 반환."""
        with patch("main.MetadataRunner") as MockRunner:
            runner_instance = MagicMock()
            runner_instance.run = AsyncMock(return_value=_enrich_result())
            MockRunner.return_value = runner_instance

            resp = client.post("/api/movies/enrich", json={
                "title": "기생충",
                "content_id": 42,
            })

        assert resp.json()["content_id"] == 42
