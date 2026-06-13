"""pipeline/ollama_client.py — 공용 Ollama JSON 생성 클라이언트.

evaluator, metadata_extractor 등이 공유. 직접 호출 금지 — 각 엔진을 통해 사용.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from shared.config import settings

logger = logging.getLogger(__name__)


class OllamaUnavailableError(RuntimeError):
    """Ollama 인프라 실패 — 모델 미설치(404)·연결거부·타임아웃 등.

    '정당한 빈/파싱불가 응답'(모델은 돌았으나 결과 무의미)과 구분한다.
    이 예외는 swallow 금지 — 파이프라인을 실패시켜 빈 facet의 'success' 영속을 막는다.
    """


async def generate_json(
    prompt: str,
    *,
    model: str | None = None,
    num_predict: int = 1024,
    temperature: float = 0.1,
    base_url: str | None = None,
) -> Optional[dict]:
    """Ollama /api/generate 호출 → dict 또는 None.

    Args:
        prompt: 전체 프롬프트 문자열
        model: 사용할 모델 (None → settings.OLLAMA_TASK_MODEL)
        num_predict: 최대 출력 토큰
        temperature: 샘플링 온도
        base_url: Ollama 서버 URL (None → settings.OLLAMA_URL)
    """
    _model = model or settings.OLLAMA_TASK_MODEL
    _base = (base_url or settings.OLLAMA_URL).rstrip("/")
    payload = {
        "model": _model,
        "prompt": prompt,
        "format": "json",
        "stream": False,
        "options": {"temperature": temperature, "num_predict": num_predict},
    }
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(f"{_base}/api/generate", json=payload)
            resp.raise_for_status()
            text = resp.json().get("response", "")
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        # 인프라 실패(404 모델 미설치·연결거부·타임아웃) — 전파해 파이프라인 실패 처리
        logger.error(f"[ollama_client] Ollama 불능: {e!r} (model={_model})")
        raise OllamaUnavailableError(f"{e!r} (model={_model})") from e
    # 여기부터는 모델이 실제 응답함 — 빈/파싱불가는 정당한 degrade(None 반환)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning(f"[ollama_client] JSON 파싱 실패(빈 응답 취급): {e}")
        return None
