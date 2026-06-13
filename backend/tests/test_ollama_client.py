"""tests/test_ollama_client.py — Ollama 인프라 실패 가드.

핵심: 404(모델 미설치)·연결거부 같은 인프라 실패는 OllamaUnavailableError로 전파해
빈 facet 'success' 영속을 막는다. 모델이 돌았으나 빈/파싱불가 응답은 None(degrade).
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from pipeline.evaluator import EvaluationEngine
from pipeline.ollama_client import OllamaUnavailableError, generate_json
from search.base import SourceDocument, SourceType


def _patch_client(mock_resp):
    """httpx.AsyncClient.post → mock_resp 로 패치하는 컨텍스트 반환."""
    cm = patch("pipeline.ollama_client.httpx.AsyncClient")
    mock_client_cls = cm.start()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return cm


@pytest.mark.asyncio
async def test_404_raises_unavailable():
    """모델 미설치 404 → OllamaUnavailableError 전파 (None 아님)."""
    req = httpx.Request("POST", "http://ollama:11434/api/generate")
    resp = httpx.Response(404, request=req)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("404", request=req, response=resp)
    )
    cm = _patch_client(mock_resp)
    try:
        with pytest.raises(OllamaUnavailableError):
            await generate_json("prompt", model="qwen2.5:14b")
    finally:
        cm.stop()


@pytest.mark.asyncio
async def test_connect_error_raises_unavailable():
    """연결거부 → OllamaUnavailableError 전파."""
    cm = patch("pipeline.ollama_client.httpx.AsyncClient")
    mock_client_cls = cm.start()
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    try:
        with pytest.raises(OllamaUnavailableError):
            await generate_json("prompt")
    finally:
        cm.stop()


@pytest.mark.asyncio
async def test_unparseable_response_degrades_to_none():
    """모델은 응답했으나 JSON 파싱불가 → None(정당한 degrade), 예외 아님."""
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"response": "not-json-at-all"}
    cm = _patch_client(mock_resp)
    try:
        result = await generate_json("prompt")
        assert result is None
    finally:
        cm.stop()


@pytest.mark.asyncio
async def test_evaluator_propagates_unavailable():
    """EvaluationEngine.evaluate 는 인프라 실패를 삼키지 않고 전파."""
    docs = [SourceDocument(
        url="https://namu.wiki/w/x", title="x", text="줄거리 텍스트",
        source_domain="namu.wiki", source_type=SourceType.synopsis, trust_score=0.85,
    )]
    req = httpx.Request("POST", "http://ollama:11434/api/generate")
    resp = httpx.Response(404, request=req)
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("404", request=req, response=resp)
    )
    cm = _patch_client(mock_resp)
    try:
        engine = EvaluationEngine()
        with pytest.raises(OllamaUnavailableError):
            await engine.evaluate("테스트영화", docs)
    finally:
        cm.stop()
