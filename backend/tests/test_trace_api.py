"""tests/test_trace_api.py — SSE 스트림 엔드포인트 + /trace 라우트 테스트."""
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def _make_runner(events: list[tuple[str, dict]], result: dict):
    """on_event 콜백을 호출한 뒤 result를 반환하는 mock runner 인스턴스를 반환."""
    mock = MagicMock()

    async def fake_run(query, **kwargs):
        on_event = kwargs.get("on_event")
        if on_event:
            for ev_type, payload in events:
                await on_event(ev_type, payload)
        return result

    mock.run = fake_run
    return mock


def _collect_sse(client, method: str, url: str, **kwargs) -> list[dict]:
    """SSE 스트림에서 data 라인을 파싱해 이벤트 목록으로 반환."""
    events = []
    with client.stream(method, url, **kwargs) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    events.append(json.loads(line[5:].strip()))
                except json.JSONDecodeError:
                    pass
    return events


# ── /api/movies/evaluate/stream ───────────────────────────────────────────────

_EVAL_EVENTS = [
    ("search_start", {"providers": ["fixture"], "query": {"title": "기생충"}}),
    ("provider_search", {"provider": "fixture", "docs_count": 2, "status": "ok", "docs": []}),
    ("eval_start", {"providers": ["fixture"]}),
    ("provider_eval", {"provider": "fixture", "trust": 0.9, "confidence": 0.7, "facet": {}}),
    ("merge", {"confidence": 0.7, "coverage": ["fixture"]}),
]
_EVAL_RESULT = {
    "movie_query": "기생충",
    "facet": {"primary_genre": "드라마", "tension": 0.8},
    "source_count": 1,
    "facet_id": 1,
    "providers_detail": [{"provider": "fixture", "docs_count": 2, "trust": 0.9, "confidence": 0.7, "evaluated": True}],
}


@patch("main.build_providers", return_value=[])
@patch("main.EvaluationEngine")
@patch("main.MultiSourceRunner")
def test_evaluate_stream_content_type(mock_runner_cls, mock_eval_cls, mock_build, client):
    mock_runner_cls.return_value = _make_runner(_EVAL_EVENTS, _EVAL_RESULT)
    with client.stream("POST", "/api/movies/evaluate/stream", json={"title": "기생충"}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


@patch("main.build_providers", return_value=[])
@patch("main.EvaluationEngine")
@patch("main.MultiSourceRunner")
def test_evaluate_stream_events(mock_runner_cls, mock_eval_cls, mock_build, client):
    mock_runner_cls.return_value = _make_runner(_EVAL_EVENTS, _EVAL_RESULT)
    events = _collect_sse(client, "POST", "/api/movies/evaluate/stream", json={"title": "기생충"})
    types = [e["type"] for e in events]
    assert "search_start" in types
    assert "merge" in types
    assert "done" in types
    done_ev = next(e for e in events if e["type"] == "done")
    assert done_ev["payload"]["movie_query"] == "기생충"


@patch("main.build_providers", return_value=[])
@patch("main.EvaluationEngine")
@patch("main.MultiSourceRunner")
def test_evaluate_stream_headless_param(mock_runner_cls, mock_eval_cls, mock_build, client):
    mock_runner_cls.return_value = _make_runner([], _EVAL_RESULT)
    with client.stream("POST", "/api/movies/evaluate/stream?headless=false", json={"title": "기생충"}) as resp:
        assert resp.status_code == 200
    mock_build.assert_called_once()
    _, kwargs = mock_build.call_args
    assert kwargs.get("headless") is False


# ── /api/movies/enrich/stream ─────────────────────────────────────────────────

_ENRICH_EVENTS = [
    ("search_start", {"providers": ["omdb"], "query": {"title": "기생충"}}),
    ("provider_search", {"provider": "omdb", "docs_count": 1, "status": "ok", "docs": []}),
    ("extract_start", {"providers": ["omdb"]}),
    ("merge", {"confidence": 0.63, "coverage": ["omdb"]}),
]
_ENRICH_RESULT = {
    "movie_query": "기생충",
    "metadata": {"content_type": "movie", "production_year": 2019, "genres": ["드라마"]},
    "source_count": 1,
    "meta_id": 1,
    "skipped_reason": None,
    "providers_detail": [{"provider": "omdb", "docs_count": 1, "trust": 0.82, "confidence": None, "evaluated": False, "structured": True}],
}


@patch("main.build_providers", return_value=[])
@patch("main.MetadataExtractionEngine")
@patch("main.MetadataRunner")
def test_enrich_stream_content_type(mock_runner_cls, mock_ext_cls, mock_build, client):
    mock_runner_cls.return_value = _make_runner(_ENRICH_EVENTS, _ENRICH_RESULT)
    with client.stream("POST", "/api/movies/enrich/stream", json={"title": "기생충"}) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers["content-type"]


@patch("main.build_providers", return_value=[])
@patch("main.MetadataExtractionEngine")
@patch("main.MetadataRunner")
def test_enrich_stream_events(mock_runner_cls, mock_ext_cls, mock_build, client):
    mock_runner_cls.return_value = _make_runner(_ENRICH_EVENTS, _ENRICH_RESULT)
    events = _collect_sse(client, "POST", "/api/movies/enrich/stream", json={"title": "기생충"})
    types = [e["type"] for e in events]
    assert "search_start" in types
    assert "merge" in types
    assert "done" in types
    done_ev = next(e for e in events if e["type"] == "done")
    assert done_ev["payload"]["movie_query"] == "기생충"


@patch("main.build_providers", return_value=[])
@patch("main.MetadataExtractionEngine")
@patch("main.MetadataRunner")
def test_enrich_stream_error_propagated(mock_runner_cls, mock_ext_cls, mock_build, client):
    """runner에서 예외 발생 시 type=error 이벤트가 스트림에 포함돼야 한다."""
    mock_runner = MagicMock()

    async def fail_run(query, **kwargs):
        raise RuntimeError("test error")

    mock_runner.run = fail_run
    mock_runner_cls.return_value = mock_runner

    events = _collect_sse(client, "POST", "/api/movies/enrich/stream", json={"title": "오류영화"})
    types = [e["type"] for e in events]
    assert "error" in types
    err_ev = next(e for e in events if e["type"] == "error")
    assert "test error" in err_ev["payload"]["message"]


# ── GET /trace ─────────────────────────────────────────────────────────────────

def test_trace_ui_returns_html(client):
    resp = client.get("/trace")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "EventSource" in resp.text or "fetch" in resp.text


def test_trace_ui_contains_stream_endpoints(client):
    resp = client.get("/trace")
    # URL은 JS 템플릿 리터럴로 동적 생성 (/api/movies/${mode}/stream)
    assert "/api/movies/" in resp.text
    assert "/stream" in resp.text
    # evaluate/enrich 모드 탭이 존재해야 함
    assert "evaluate" in resp.text
    assert "enrich" in resp.text


# ── GET /ui ───────────────────────────────────────────────────────────────────

def test_main_ui_returns_html(client):
    resp = client.get("/ui")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


def test_main_ui_contains_stream_endpoints(client):
    resp = client.get("/ui")
    assert "/api/movies/" in resp.text
    assert "/stream" in resp.text
    assert "evaluate" in resp.text
    assert "enrich" in resp.text


def test_main_ui_has_timeline_and_result(client):
    resp = client.get("/ui")
    assert "파이프라인" in resp.text
    assert "결과" in resp.text
    assert "score-bar" in resp.text or "confidence" in resp.text
