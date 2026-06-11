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
            return json.loads(text)
    except httpx.HTTPError as e:
        logger.error(f"[ollama_client] HTTP 오류: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"[ollama_client] JSON 파싱 실패: {e}")
    except Exception as e:
        logger.error(f"[ollama_client] 예외: {e}")
    return None
