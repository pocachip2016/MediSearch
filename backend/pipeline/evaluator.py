"""pipeline/evaluator.py — Ollama 기반 영화 facet 평가 엔진.

SourceDocument 리스트 → validate_movie_facet 통과 facet dict.
원본 텍스트는 평가 후 소멸 (원본 미저장 원칙).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import httpx

from pipeline.facets import (
    ENUM_VOCAB,
    LIST_VOCAB,
    SCORE_FIELDS,
    attach_coverage,
    empty_facet,
    validate_movie_facet,
)
from search.base import SourceDocument
from shared.config import settings

logger = logging.getLogger(__name__)

_MAX_TEXT_PER_DOC = 800  # 문서당 텍스트 최대 길이 (토큰 절약)


def _build_prompt(movie_query: str, docs: list[SourceDocument]) -> str:
    sources_text = ""
    for i, doc in enumerate(docs, 1):
        snippet = (doc.text or "")[:_MAX_TEXT_PER_DOC]
        sources_text += f"\n[소스 {i}] ({doc.source_type.value}) {doc.title}\n{snippet}\n"

    enum_hints = "\n".join(
        f'  "{k}": 다음 중 하나 (해당 없으면 null) — {v}' for k, v in ENUM_VOCAB.items()
    )
    list_hints = "\n".join(
        f'  "{k}": 다음 중 해당하는 것 복수 선택 — {v}' for k, v in LIST_VOCAB.items()
    )
    score_list = ", ".join(SCORE_FIELDS)

    return f"""당신은 영화 분석 AI입니다. 아래 소스 텍스트를 바탕으로 영화 "{movie_query}"의 분석 데이터를 JSON으로 출력하세요.

## 소스 텍스트
{sources_text}

## 출력 JSON 스키마

### enum 필드 (정확히 아래 허용값 중 하나만, 해당 없으면 null):
{enum_hints}

### list 필드 (아래 허용값에서 해당하는 것 복수 선택, 빈 배열 가능):
{list_hints}

### score 필드 (0.0~1.0 실수, 정보 부족 시 null):
각 필드 설명:
- tension: 긴장감/스릴 강도 (높을수록 긴장됨)
- immersion: 몰입도 (높을수록 집중하게 됨)
- boredom_risk: 지루함 위험도 (높을수록 지루할 수 있음)
- rewatch_value: 재시청 의향 (높을수록 다시 보고 싶음)
- attention_required: 집중 필요도 (높을수록 집중해야 함)
- emotional_energy_required: 감정 소모도 (높을수록 감정적으로 소진됨)
- violence: 폭력성 (높을수록 폭력적)
- gore: 잔인함 (높을수록 잔인한 장면 많음)
- sexual_content: 성적 콘텐츠 (높을수록 성적 표현 있음)
- spoiler_sensitivity: 스포일러 민감도 (높을수록 스포가 치명적)
- sentiment_score: 전체 감성 점수 (높을수록 긍정적)

출력할 score 필드명: {score_list}

### 기타:
  "micro_genre": 자유 태그 리스트 (최대 4개, 한국어)
  "premise": 한 줄 줄거리 요약 (한국어, 최대 200자)
  "one_liner": 감성 한줄평 (한국어, 최대 100자)

## 출력 예시 (형식만 참고, 값은 실제 분석 기반으로):
{{"primary_genre": "드라마", "conflict": "사회갈등", "ending_type": "열린결말", "pacing_reaction": "적절하다", "ending_reaction": "만족", "sub_genre": ["범죄스릴러"], "theme": ["계급", "복수"], "mood": ["긴장", "어두움"], "emotional_aftertaste": ["여운"], "tension": 0.85, "immersion": 0.9, "boredom_risk": 0.1, "rewatch_value": 0.75, "attention_required": 0.8, "emotional_energy_required": 0.7, "violence": 0.4, "gore": 0.2, "sexual_content": 0.0, "spoiler_sensitivity": 0.7, "sentiment_score": 0.8, "micro_genre": ["계급드라마"], "premise": "줄거리 요약", "one_liner": "한줄평"}}

위 모든 필드를 포함한 JSON 객체 하나만 출력하세요. 설명이나 마크다운 없이 순수 JSON만."""


class EvaluationEngine:
    """Ollama를 호출해 SourceDocument 리스트로부터 MovieFacet JSON을 생성."""

    def __init__(self, model: str | None = None, base_url: str | None = None):
        # reasoning 모델(qwen3) 회피 — 구조화 태스크는 TASK_MODEL 사용
        self.model = model or settings.OLLAMA_TASK_MODEL
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")

    async def evaluate(
        self, movie_query: str, docs: list[SourceDocument]
    ) -> dict:
        """SourceDocument 리스트 → 검증된 facet dict.

        실패 시 empty_facet() 반환 — 파이프라인을 중단하지 않는다.
        """
        source_types = [doc.source_type.value for doc in docs]

        if not docs:
            logger.warning(f"[evaluator] 소스 없음: {movie_query}")
            return attach_coverage(empty_facet(), source_types)

        prompt = _build_prompt(movie_query, docs)
        raw = await self._call_ollama(prompt)

        if raw is None:
            logger.warning(f"[evaluator] LLM 응답 없음, empty_facet 반환: {movie_query}")
            return attach_coverage(empty_facet(), source_types)

        facet = validate_movie_facet(raw)
        return attach_coverage(facet, source_types)

    async def _call_ollama(self, prompt: str) -> Optional[dict]:
        """Ollama /api/generate 호출 → dict 또는 None."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1024},
        }
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{self.base_url}/api/generate", json=payload
                )
                resp.raise_for_status()
                text = resp.json().get("response", "")
                return json.loads(text)
        except httpx.HTTPError as e:
            logger.error(f"[evaluator] Ollama HTTP 오류: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"[evaluator] LLM JSON 파싱 실패: {e}")
        except Exception as e:
            logger.error(f"[evaluator] 예외: {e}")
        return None
