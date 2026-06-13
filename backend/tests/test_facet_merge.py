"""tests/test_facet_merge.py — merge_facets 단위 테스트."""
import pytest
from pipeline.facet_merge import merge_facets
from pipeline.facets import validate_movie_facet


def _f(**kwargs) -> dict:
    base = validate_movie_facet({})
    base.update(kwargs)
    return base


# ── 빈 입력 / 패스스루 ─────────────────────────────────────

def test_empty_input_returns_empty_facet():
    result = merge_facets([])
    assert result["tension"] is None
    assert result["primary_genre"] is None
    assert "_coverage" in result
    assert result["confidence"] == 0.0


def test_single_entry_passthrough():
    facet = _f(tension=0.8, primary_genre="스릴러")
    result = merge_facets([(facet, 0.9)])
    assert result["tension"] == 0.8
    assert result["primary_genre"] == "스릴러"
    assert "_coverage" in result


# ── score 가중평균 ─────────────────────────────────────────

def test_score_weighted_average():
    """tension: 0.6 (trust 0.8) + 0.9 (trust 0.4) → (0.6·0.8 + 0.9·0.4) / 1.2."""
    f1 = _f(tension=0.6)
    f2 = _f(tension=0.9)
    result = merge_facets([(f1, 0.8), (f2, 0.4)])
    expected = round((0.6 * 0.8 + 0.9 * 0.4) / 1.2, 4)
    assert result["tension"] == pytest.approx(expected, abs=1e-4)


def test_score_null_excluded_from_average():
    """None 소스는 가중평균 제외 → tension=0.6 그대로."""
    f1 = _f(tension=0.6)
    f2 = validate_movie_facet({})   # tension=None
    result = merge_facets([(f1, 0.5), (f2, 0.9)])
    assert result["tension"] == pytest.approx(0.6, abs=1e-4)


# ── enum 가중투표 ──────────────────────────────────────────

def test_enum_trust_vote():
    """스릴러(0.9) vs 드라마(0.5) → 스릴러 선택."""
    f1 = _f(primary_genre="스릴러")
    f2 = _f(primary_genre="드라마")
    result = merge_facets([(f1, 0.9), (f2, 0.5)])
    assert result["primary_genre"] == "스릴러"


# ── list vocab trust 임계 ─────────────────────────────────

def test_list_vocab_above_threshold_included():
    """성장(1.0), 복수(0.5): total=0.9, threshold=0.306 → 둘 다 채택."""
    f1 = _f(theme=["성장", "복수"])
    f2 = _f(theme=["성장"])
    result = merge_facets([(f1, 0.5), (f2, 0.4)])
    assert "성장" in result["theme"]
    assert "복수" in result["theme"]


def test_list_vocab_below_threshold_excluded():
    """복수(0.2): total=1.0, threshold=0.34 → 미채택."""
    f1 = _f(theme=["성장", "복수"])   # trust 0.2
    f2 = _f(theme=["성장"])           # trust 0.8
    result = merge_facets([(f1, 0.2), (f2, 0.8)])
    assert "성장" in result["theme"]
    assert "복수" not in result["theme"]


def test_list_vocab_abstaining_source_not_diluted():
    """theme 미제공 소스(0.7)가 분모를 키워 제공 소스(0.3)를 탈락시키지 않음.

    회귀: 분모를 total_trust(1.0)로 쓰면 threshold=0.34 > 0.3 으로 탈락하던 버그.
    분모를 기여 소스(0.3)로 한정하면 threshold=0.102 → 채택.
    2소스라 구조 outlier 제거(≥3) 미발동.
    """
    f1 = _f(theme=["성장"])             # theme 제공, trust 0.3
    f2 = _f(primary_genre="드라마")      # theme 미제공(abstain), trust 0.7
    result = merge_facets([(f1, 0.3), (f2, 0.7)])
    assert "성장" in result["theme"]


# ── 구조 outlier 제거 ────────────────────────────────────

def test_structural_outlier_removed_with_three_sources():
    """3소스 중 장르·테마가 전혀 다른 1개 → 배제 후 나머지 2개로 병합."""
    f_a1 = _f(primary_genre="액션", theme=["생존", "전쟁"], tension=0.8)
    f_a2 = _f(primary_genre="액션", theme=["생존"],         tension=0.7)
    f_out = _f(primary_genre="코미디", theme=["우정", "성장"], tension=0.1)

    result = merge_facets(
        [(f_a1, 0.9), (f_a2, 0.85), (f_out, 0.7)],
        source_types=["synopsis", "synopsis", "user_review"],
    )
    # outlier 배제 → 액션 2개로 병합
    assert result["primary_genre"] == "액션"
    expected = round((0.8 * 0.9 + 0.7 * 0.85) / (0.9 + 0.85), 4)
    assert result["tension"] == pytest.approx(expected, abs=1e-4)


def test_structural_outlier_not_removed_with_two_sources():
    """2소스이면 outlier 제거 없음 → 양쪽 trust 투표로 결정."""
    f1 = _f(primary_genre="액션", tension=0.8)
    f2 = _f(primary_genre="코미디", tension=0.1)
    result = merge_facets([(f1, 0.9), (f2, 0.5)])
    assert result["primary_genre"] == "액션"   # 액션(0.9) > 코미디(0.5)


# ── coverage ─────────────────────────────────────────────

def test_coverage_attached_with_source_types():
    f = _f(tension=0.5)
    result = merge_facets([(f, 0.9)], source_types=["synopsis"])
    assert result["_coverage"]["source_count"] == 1
    assert result["_coverage"]["has_synopsis"] is True
    assert result["confidence"] > 0.0


def test_coverage_empty_when_no_source_types():
    f = _f(tension=0.5)
    result = merge_facets([(f, 0.9)])
    assert result["_coverage"]["source_count"] == 0
    assert result["confidence"] == 0.0
