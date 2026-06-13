"""tests/test_evaluator.py — EvaluationEngine 단위 테스트 (Ollama mock)."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pipeline.evaluator import EvaluationEngine, _build_prompt
from pipeline.facets import ENUM_VOCAB, SCORE_FIELDS, empty_facet
from search.base import SourceDocument, SourceType


# ── 픽스처 ─────────────────────────────────────────────────

@pytest.fixture
def sample_docs():
    return [
        SourceDocument(
            url="https://namu.wiki/w/기생충",
            title="기생충 (영화)",
            text="봉준호 감독의 2019년 작품. 반지하 가족과 부유한 박 사장 가족의 이야기. 칸 황금종려상 수상.",
            source_domain="namu.wiki",
            source_type=SourceType.synopsis,
            trust_score=0.9,
        ),
        SourceDocument(
            url="https://imdb.com/title/tt6751668",
            title="Parasite (2019) - IMDB",
            text="A masterpiece of social commentary. Bong Joon-ho crafts tension perfectly. Score: 8.5/10.",
            source_domain="imdb.com",
            source_type=SourceType.expert_review,
            trust_score=0.95,
        ),
    ]


@pytest.fixture
def valid_llm_response():
    """Ollama가 반환하는 유효한 facet JSON."""
    return {
        "primary_genre": "드라마",
        "conflict": "계급갈등",  # 통제어휘 외 → None으로 정규화
        "ending_type": "열린결말",
        "pacing_reaction": "적절하다",
        "ending_reaction": "호불호갈림",
        "sub_genre": ["범죄스릴러", "블랙코미디"],
        "theme": ["계급", "복수", "가족"],
        "mood": ["긴장", "어두움"],
        "emotional_aftertaste": ["여운", "씁쓸함"],
        "micro_genre": ["계급드라마", "가족갈등"],
        "premise": "반지하 가족이 부유한 가정에 침투하면서 벌어지는 계급 갈등.",
        "one_liner": "완벽한 긴장감과 사회 비판이 공존하는 걸작.",
        "tension": 0.9,
        "immersion": 0.95,
        "boredom_risk": 0.1,
        "rewatch_value": 0.8,
        "attention_required": 0.85,
        "emotional_energy_required": 0.75,
        "violence": 0.4,
        "gore": 0.3,
        "sexual_content": 0.05,
        "spoiler_sensitivity": 0.7,
        "sentiment_score": 0.85,
    }


# ── _build_prompt ──────────────────────────────────────────

def test_build_prompt_contains_movie_query(sample_docs):
    prompt = _build_prompt("기생충", sample_docs)
    assert "기생충" in prompt


def test_build_prompt_contains_sources(sample_docs):
    prompt = _build_prompt("기생충", sample_docs)
    assert "나무위키" in prompt or "기생충 (영화)" in prompt
    assert "Parasite (2019)" in prompt


def test_build_prompt_contains_all_score_fields(sample_docs):
    prompt = _build_prompt("기생충", sample_docs)
    for field in SCORE_FIELDS:
        assert field in prompt, f"score 필드 '{field}' 가 프롬프트에 없음"


def test_build_prompt_contains_enum_vocab(sample_docs):
    prompt = _build_prompt("기생충", sample_docs)
    for key in ENUM_VOCAB:
        assert key in prompt


# ── EvaluationEngine ──────────────────────────────────────

class TestEvaluationEngine:
    def test_init_uses_task_model(self):
        engine = EvaluationEngine()
        from shared.config import settings
        assert engine.model == settings.OLLAMA_TASK_MODEL

    def test_init_custom_model(self):
        engine = EvaluationEngine(model="llama3.2:3b")
        assert engine.model == "llama3.2:3b"

    @pytest.mark.asyncio
    async def test_evaluate_returns_valid_facet(self, sample_docs, valid_llm_response):
        engine = EvaluationEngine()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(valid_llm_response)}
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await engine.evaluate("기생충", sample_docs)

        assert result["primary_genre"] == "드라마"
        assert result["ending_type"] == "열린결말"
        assert isinstance(result["tension"], float)
        assert 0.0 <= result["tension"] <= 1.0
        assert "_coverage" in result
        assert "confidence" in result

    @pytest.mark.asyncio
    async def test_evaluate_coverage_reflects_sources(self, sample_docs, valid_llm_response):
        engine = EvaluationEngine()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(valid_llm_response)}
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await engine.evaluate("기생충", sample_docs)

        coverage = result["_coverage"]
        assert coverage["source_count"] == 2
        assert coverage["has_synopsis"] is True
        assert coverage["has_expert"] is True

    @pytest.mark.asyncio
    async def test_evaluate_empty_docs_returns_empty_facet(self):
        engine = EvaluationEngine()
        result = await engine.evaluate("기생충", [])

        expected = empty_facet()
        for key in SCORE_FIELDS:
            assert result[key] == expected[key]
        assert result["_coverage"]["source_count"] == 0
        assert result["confidence"] == 0.0

    @pytest.mark.asyncio
    async def test_evaluate_ollama_infra_error_propagates(self, sample_docs):
        """인프라 실패(연결거부)는 빈 facet으로 삼키지 않고 전파 — 빈 success 영속 차단."""
        import httpx
        from pipeline.ollama_client import OllamaUnavailableError

        engine = EvaluationEngine()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            with pytest.raises(OllamaUnavailableError):
                await engine.evaluate("기생충", sample_docs)

    @pytest.mark.asyncio
    async def test_evaluate_invalid_json_returns_empty_facet(self, sample_docs):
        engine = EvaluationEngine()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": "이건 JSON이 아닙니다"}
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await engine.evaluate("기생충", sample_docs)

        assert result["primary_genre"] is None

    @pytest.mark.asyncio
    async def test_evaluate_out_of_vocab_enum_becomes_none(self, sample_docs):
        """통제어휘 외 enum 값은 None으로 정규화."""
        engine = EvaluationEngine()
        bad_response = {"primary_genre": "뮤지컬"}  # 허용 안 됨
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(bad_response)}
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await engine.evaluate("테스트영화", sample_docs)

        assert result["primary_genre"] is None

    @pytest.mark.asyncio
    async def test_evaluate_safety_flags_derived(self, sample_docs):
        """violence >= 0.5 → is_violent = True."""
        engine = EvaluationEngine()
        violent_response = {"violence": 0.8, "gore": 0.6, "sexual_content": 0.0}
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"response": json.dumps(violent_response)}
        mock_resp.raise_for_status = MagicMock()

        with patch("pipeline.ollama_client.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await engine.evaluate("액션영화", sample_docs)

        flags = result["safety_flags"]
        assert flags["is_violent"] is True
        assert flags["is_gory"] is True
        assert flags["is_sexual"] is False
        assert flags["age_suggestion"] == "청소년관람불가"


class TestGenreHint:
    """_build_prompt genre_hint 그라운딩."""

    def _doc(self):
        from search.base import SourceDocument, SourceType
        return SourceDocument(
            title="테스트", text="줄거리", url="http://test",
            source_domain="test", source_type=SourceType.synopsis, trust_score=0.9,
        )

    def test_genre_hint_included_in_prompt(self):
        prompt = _build_prompt("녹턴", [self._doc()], genre_hint=["다큐멘터리", "음악"])
        assert "공식 장르(TMDB): 다큐멘터리, 음악" in prompt
        assert "primary_genre는 이를 우선 고려" in prompt

    def test_genre_hint_none_not_in_prompt(self):
        prompt = _build_prompt("녹턴", [self._doc()], genre_hint=None)
        assert "공식 장르" not in prompt
        assert "TMDB" not in prompt

    def test_genre_hint_empty_list_not_in_prompt(self):
        prompt = _build_prompt("녹턴", [self._doc()], genre_hint=[])
        assert "공식 장르" not in prompt

    @pytest.mark.asyncio
    async def test_evaluate_passes_genre_hint_to_prompt(self, sample_docs):
        """evaluate()에 genre_hint 전달 시 프롬프트에 반영됨."""
        engine = EvaluationEngine()
        captured: list[str] = []

        async def mock_call_ollama(prompt: str):
            captured.append(prompt)
            return None  # empty_facet 반환 경로

        engine._call_ollama = mock_call_ollama
        await engine.evaluate("녹턴", sample_docs, genre_hint=["다큐멘터리"])
        assert captured, "프롬프트 캡처 실패"
        assert "다큐멘터리" in captured[0]
