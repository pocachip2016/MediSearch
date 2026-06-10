"""tests/test_score_calibration.py — _build_prompt few-shot 구조 검증."""
from pipeline.evaluator import _build_prompt, _FEW_SHOT_EXAMPLES
from pipeline.facets import SCORE_FIELDS
from search.base import SourceDocument, SourceType


def _sample_docs():
    return [
        SourceDocument(
            url="https://example.com/test",
            title="테스트 영화",
            text="테스트 줄거리",
            source_domain="example.com",
            source_type=SourceType.synopsis,
            trust_score=0.8,
        )
    ]


def test_prompt_contains_null_prohibition():
    """null 금지 규칙이 프롬프트에 포함돼야 함."""
    prompt = _build_prompt("테스트영화", _sample_docs())
    assert "null" in prompt and ("금지" in prompt or "절대" in prompt)


def test_prompt_contains_score_anchors():
    """0.5= 앵커가 score 필드별로 포함돼야 함."""
    prompt = _build_prompt("테스트영화", _sample_docs())
    assert "0.5=" in prompt
    assert "[0=" in prompt
    assert "1=" in prompt


def test_prompt_contains_parasite_example():
    """기생충 few-shot 예시가 프롬프트에 포함돼야 함."""
    prompt = _build_prompt("테스트영화", _sample_docs())
    assert "기생충" in prompt
    assert "사회갈등" in prompt


def test_prompt_contains_lalaland_example():
    """라라랜드 few-shot 예시가 프롬프트에 포함돼야 함."""
    prompt = _build_prompt("테스트영화", _sample_docs())
    assert "라라랜드" in prompt
    assert "로맨스" in prompt


def test_prompt_contains_all_score_fields():
    """11개 score 필드 이름이 모두 프롬프트에 포함돼야 함."""
    prompt = _build_prompt("테스트영화", _sample_docs())
    for field in SCORE_FIELDS:
        assert field in prompt, f"score 필드 '{field}' 프롬프트에 없음"


def test_few_shot_examples_have_calibrated_scores():
    """few-shot 예시 A(기생충)의 tension이 0.8 이상, violence가 0.5 미만임을 확인."""
    assert '"tension":0.85' in _FEW_SHOT_EXAMPLES
    assert '"violence":0.45' in _FEW_SHOT_EXAMPLES


def test_few_shot_examples_cover_diverse_genres():
    """두 예시가 고긴장(기생충)과 저긴장(라라랜드)을 모두 포함해야 함."""
    assert '"tension":0.85' in _FEW_SHOT_EXAMPLES   # 기생충 — 고긴장
    assert '"tension":0.2' in _FEW_SHOT_EXAMPLES    # 라라랜드 — 저긴장


def test_prompt_max_text_per_doc_increased():
    """텍스트 길이 상향(1200자) 확인: 긴 소스도 전부 포함."""
    from pipeline.evaluator import _MAX_TEXT_PER_DOC
    assert _MAX_TEXT_PER_DOC >= 1200
