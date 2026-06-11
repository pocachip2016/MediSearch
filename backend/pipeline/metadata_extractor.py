"""pipeline/metadata_extractor.py — 텍스트 소스에서 기본 메타 추출 (LLM).

MetadataExtractionEngine:
  - extract(title, docs) → validate_metadata 통과 dict
  - rewrite_story(title, synopsis_texts) → str|None (30자 내외 스토리)

프롬프트 원칙: 추정·일반지식 보충 절대 금지 — 텍스트 명시 정보만, 없으면 null.
"""
from __future__ import annotations

import logging
from typing import Optional

from pipeline.metadata_schema import validate_metadata, empty_metadata
from pipeline.ollama_client import generate_json
from search.base import SourceDocument
from shared.config import settings

logger = logging.getLogger(__name__)

_MAX_TEXT_LEN = 1200
_STORY_MAX_LEN = 60


def _build_extraction_prompt(title: str, docs: list[SourceDocument]) -> str:
    sources_block = "\n\n".join(
        f"[소스 {i+1}] ({doc.source_type.value}) {doc.title}\n{doc.text[:_MAX_TEXT_LEN]}"
        for i, doc in enumerate(docs)
    )
    return f"""당신은 영화/시리즈 메타데이터 추출 AI입니다.
아래 소스 텍스트에서 "{title}"의 사실 정보만 JSON으로 추출하세요.

## 소스 텍스트
{sources_block}

## 출력 JSON 스키마
- "content_type": "movie" 또는 "series" (불명확하면 null)
- "original_title": 원제 (없으면 null)
- "production_year": 제작/개봉 연도 정수 (없으면 null)
- "runtime_minutes": 러닝타임 분 단위 정수 (없으면 null)
- "countries": 제작 국가 리스트 (한국어 표기, 없으면 [])
- "genres": 장르 리스트 (한국어 표기, 없으면 [])
- "directors": 감독 이름 리스트 (없으면 [])
- "cast": [{{"name": 배우명, "role": 배역명 또는 null}}, ...] 최대 10명 (없으면 [])
- "story": 줄거리를 30자 내외 한국어 한 문장으로 재작성 (텍스트에 줄거리가 있을 때만, 없으면 null)
- "keywords": 핵심 키워드 리스트 최대 8개 (없으면 [])
- "series": content_type이 "series"일 때만 {{"total_seasons": 정수 또는 null, "total_episodes": 정수 또는 null, "first_air_date": "YYYY-MM-DD" 또는 null, "air_status": "ongoing" 또는 "ended" 또는 null, "networks": 방송사 리스트}}, 아니면 null

## 출력 규칙 (반드시 준수)
1. 소스 텍스트에 명시된 정보만 추출하세요. 추정·일반지식 보충 절대 금지 — 텍스트에 없으면 null/빈 배열.
2. 인명은 텍스트 표기 그대로 (번역 금지).
3. story는 30자 내외 한 문장 — 길면 잘라내고, 없으면 null.
4. 순수 JSON 하나만 출력하세요.
"""


def _build_rewrite_prompt(title: str, synopsis_texts: list[str]) -> str:
    combined = "\n\n".join(t[:_MAX_TEXT_LEN] for t in synopsis_texts[:3])
    return f""""{title}"의 줄거리를 아래 내용을 바탕으로 30자 내외 한국어 한 문장으로 재작성하세요.
추정·각색 금지. 텍스트에 없는 내용 추가 금지.
결과 JSON: {{"story": "재작성된 한 문장"}}

## 원본 내용
{combined}
"""


class MetadataExtractionEngine:
    """텍스트 SourceDocument 목록에서 기본 메타를 LLM으로 추출."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.model = model or settings.OLLAMA_TASK_MODEL
        self.base_url = base_url or settings.OLLAMA_URL

    async def extract(
        self, title: str, docs: list[SourceDocument]
    ) -> dict:
        """텍스트 docs → validate_metadata 통과 dict."""
        if not docs:
            return empty_metadata()

        prompt = _build_extraction_prompt(title, docs)
        raw = await generate_json(
            prompt,
            model=self.model,
            base_url=self.base_url,
            temperature=0.0,
            num_predict=1024,
        )
        if not raw:
            logger.warning(f"[metadata_extractor] LLM 응답 없음: {title!r}")
            return empty_metadata()

        return validate_metadata(raw)

    async def rewrite_story(
        self, title: str, synopsis_texts: list[str]
    ) -> Optional[str]:
        """구조화 소스 synopsis_raw 목록 → 30자 내외 story 재작성."""
        if not synopsis_texts:
            return None

        prompt = _build_rewrite_prompt(title, synopsis_texts)
        raw = await generate_json(
            prompt,
            model=self.model,
            base_url=self.base_url,
            temperature=0.0,
            num_predict=128,
        )
        if not raw:
            return None

        story = raw.get("story", "")
        if not isinstance(story, str) or not story.strip():
            return None
        return story.strip()[:_STORY_MAX_LEN]
