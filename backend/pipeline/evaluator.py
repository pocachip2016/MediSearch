"""pipeline/evaluator.py — Ollama 기반 영화 facet 평가 엔진.

SourceDocument 리스트 → validate_movie_facet 통과 facet dict.
원본 텍스트는 평가 후 소멸 (원본 미저장 원칙).
"""
from __future__ import annotations

import logging
from typing import Optional

from pipeline.facets import (
    ENUM_VOCAB,
    LIST_VOCAB,
    SCORE_FIELDS,
    attach_coverage,
    empty_facet,
    validate_movie_facet,
)
from pipeline.ollama_client import generate_json
from search.base import SourceDocument
from shared.config import settings

logger = logging.getLogger(__name__)

_MAX_TEXT_PER_DOC = 1200  # 문서당 텍스트 최대 길이


# calibrated few-shot 예시 (score 앵커 참조용)
_FEW_SHOT_EXAMPLES = """## 출력 예시 (실제 분석 기준 참고)

### 예시 A — 기생충 (2019, 사회드라마 · 고긴장 · 중간폭력)
{"primary_genre":"드라마","conflict":"사회갈등","ending_type":"비극","pacing_reaction":"적절하다","ending_reaction":"호불호갈림","sub_genre":["범죄스릴러","블랙코미디"],"theme":["계급","복수","가족"],"mood":["긴장","어두움"],"emotional_aftertaste":["여운","씁쓸함"],"tension":0.85,"immersion":0.95,"boredom_risk":0.05,"rewatch_value":0.75,"attention_required":0.85,"emotional_energy_required":0.8,"violence":0.45,"gore":0.25,"sexual_content":0.05,"spoiler_sensitivity":0.9,"sentiment_score":0.7,"micro_genre":["계급드라마"],"premise":"반지하 가족이 부유층 집에 침투하며 벌어지는 계급 갈등","one_liner":"완벽한 긴장감과 사회 비판이 공존하는 걸작"}

### 예시 B — 라라랜드 (2016, 로맨스 · 저긴장 · 폭력없음)
{"primary_genre":"로맨스","conflict":"내적갈등","ending_type":"열린결말","pacing_reaction":"적절하다","ending_reaction":"호불호갈림","sub_genre":["성장물"],"theme":["사랑","성장","상실"],"mood":["감성","로맨틱"],"emotional_aftertaste":["여운","씁쓸함"],"tension":0.2,"immersion":0.75,"boredom_risk":0.2,"rewatch_value":0.85,"attention_required":0.35,"emotional_energy_required":0.55,"violence":0.0,"gore":0.0,"sexual_content":0.1,"spoiler_sensitivity":0.45,"sentiment_score":0.8,"micro_genre":["뮤지컬로맨스"],"premise":"꿈을 좇는 두 남녀의 사랑과 이별","one_liner":"아름답고 쓸쓸한, 꿈에 관한 러브레터"}
"""


def _build_prompt(movie_query: str, docs: list[SourceDocument], genre_hint: list[str] | None = None) -> str:
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

    genre_hint_line = (
        f"\n## 장르 그라운딩\n참고 — 이 작품의 공식 장르(TMDB): {', '.join(genre_hint)}. "
        "primary_genre는 이를 우선 고려하되, 줄거리가 명백히 다른 장르를 가리키면 줄거리를 따르라.\n"
        if genre_hint else ""
    )

    return f"""당신은 영화 분석 AI입니다. 아래 소스 텍스트를 바탕으로 영화 "{movie_query}"의 분석 데이터를 JSON으로 출력하세요.

## 소스 텍스트
{sources_text}

## 출력 JSON 스키마

### enum 필드 (정확히 아래 허용값 중 하나만, 해당 없으면 null):
{enum_hints}

### list 필드 (아래 허용값에서 해당하는 것 복수 선택, 빈 배열 가능):
{list_hints}

### score 필드 — 반드시 0.0~1.0 실수로 입력 (null 사용 절대 금지):
- tension: 긴장감/스릴 [0=전혀없음, 0.5=보통, 1=극한긴장]
- immersion: 몰입도 [0=지루함, 0.5=보통, 1=완전몰입]
- boredom_risk: 지루함 위험도 [0=전혀안지루함, 0.5=보통, 1=매우지루함]
- rewatch_value: 재시청 의향 [0=보기싫음, 0.5=보통, 1=꼭다시봄]
- attention_required: 집중 필요도 [0=배경시청가능, 0.5=보통, 1=완전집중필수]
- emotional_energy_required: 감정 소모도 [0=가볍게시청, 0.5=보통, 1=감정적으로소진]
- violence: 폭력성 [0=없음, 0.5=격투장면, 1=극단적폭력]
- gore: 잔인함 [0=없음, 0.5=부상·유혈, 1=고어극]
- sexual_content: 성적표현 [0=없음, 0.5=간접암시, 1=노골적]
- spoiler_sensitivity: 스포일러 민감도 [0=상관없음, 0.5=보통, 1=치명적]
- sentiment_score: 전체 감성 [0=매우부정적, 0.5=중립, 1=매우긍정적]

출력할 score 필드명: {score_list}

### 기타:
  "micro_genre": 자유 태그 리스트 (최대 4개, 한국어)
  "premise": 한 줄 줄거리 요약 (한국어, 최대 200자)
  "one_liner": 감성 한줄평 (한국어, 최대 100자)

{_FEW_SHOT_EXAMPLES}
{genre_hint_line}
## 출력 규칙
1. score 11개 필드는 모두 반드시 0.0~1.0 실수로 입력. null/누락 절대 금지.
2. 소스 정보가 부족해도 장르·내용 맥락으로 추정값을 제공할 것.
3. 순수 JSON 하나만 출력. 마크다운·설명 불필요.

위 모든 필드를 포함한 JSON 객체 하나만 출력하세요."""


class EvaluationEngine:
    """Ollama를 호출해 SourceDocument 리스트로부터 MovieFacet JSON을 생성."""

    def __init__(self, model: str | None = None, base_url: str | None = None):
        # reasoning 모델(qwen3) 회피 — 구조화 태스크는 TASK_MODEL 사용
        self.model = model or settings.OLLAMA_TASK_MODEL
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")

    async def evaluate(
        self, movie_query: str, docs: list[SourceDocument],
        genre_hint: list[str] | None = None,
    ) -> dict:
        """SourceDocument 리스트 → 검증된 facet dict.

        실패 시 empty_facet() 반환 — 파이프라인을 중단하지 않는다.
        """
        source_types = [doc.source_type.value for doc in docs]

        if not docs:
            logger.warning(f"[evaluator] 소스 없음: {movie_query}")
            return attach_coverage(empty_facet(), source_types)

        prompt = _build_prompt(movie_query, docs, genre_hint=genre_hint)
        raw = await self._call_ollama(prompt)

        if raw is None:
            logger.warning(f"[evaluator] LLM 응답 없음, empty_facet 반환: {movie_query}")
            return attach_coverage(empty_facet(), source_types)

        facet = validate_movie_facet(raw)
        return attach_coverage(facet, source_types)

    async def _call_ollama(self, prompt: str) -> Optional[dict]:
        """Ollama 호출 — ollama_client.generate_json 위임."""
        return await generate_json(
            prompt,
            model=self.model,
            base_url=self.base_url,
            temperature=0.1,
        )
