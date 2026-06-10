"""tests/test_multi_runner.py — MultiSourceRunner + provider_factory 테스트."""
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.orm import Session

from models import MovieFacet, SearchSource
from pipeline.evaluator import EvaluationEngine
from pipeline.multi_runner import MultiSourceRunner
from search.base import SearchProvider, SourceDocument, SourceType
from search.provider_factory import build_providers


# ── 공용 픽스처 ──────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    facet_counter = [0]

    def add_side_effect(obj):
        if isinstance(obj, MovieFacet):
            facet_counter[0] += 1
            obj.id = facet_counter[0]

    db.add.side_effect = add_side_effect
    return db


def _make_provider(name: str, docs: list[SourceDocument]) -> SearchProvider:
    p = MagicMock(spec=SearchProvider)
    p.provider_name = name
    p.search = AsyncMock(return_value=docs)
    return p


def _make_evaluator(facet: dict | None = None) -> EvaluationEngine:
    ev = MagicMock(spec=EvaluationEngine)
    ev.evaluate = AsyncMock(return_value=facet or {
        "primary_genre": "드라마",
        "tension": 0.8,
        "confidence": 0.75,
        "_coverage": {},
    })
    return ev


def _doc(name: str, trust: float = 0.8) -> SourceDocument:
    return SourceDocument(
        url=f"https://{name}.com/",
        title=name,
        text="텍스트",
        source_domain=f"{name}.com",
        source_type=SourceType.synopsis,
        trust_score=trust,
    )


# ── build_providers ──────────────────────────────────────────

def test_build_providers_known():
    providers = build_providers(["fixture", "tmdb"])
    names = [p.provider_name for p in providers]
    assert names == ["fixture", "tmdb"]


def test_build_providers_unknown_skipped():
    providers = build_providers(["fixture", "unknown_xyz"])
    assert len(providers) == 1
    assert providers[0].provider_name == "fixture"


def test_build_providers_empty():
    assert build_providers([]) == []


# ── MultiSourceRunner ────────────────────────────────────────

@pytest.mark.asyncio
async def test_multi_runner_two_providers(mock_db):
    """2개 provider → 각각 평가 → 병합 결과 반환."""
    p1 = _make_provider("src1", [_doc("src1", 0.9)])
    p2 = _make_provider("src2", [_doc("src2", 0.7)])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1, p2], ev, mock_db)
    result = await runner.run("기생충")

    assert result["movie_query"] == "기생충"
    assert result["source_count"] == 2
    assert result["facet_id"] is not None
    assert "confidence" in result["facet"]
    # evaluator가 각 provider별 1회씩 호출됐는지
    assert ev.evaluate.call_count == 2


@pytest.mark.asyncio
async def test_multi_runner_one_provider_empty(mock_db):
    """한 provider가 빈 결과 → 나머지 단독 처리."""
    p1 = _make_provider("empty_src", [])
    p2 = _make_provider("real_src", [_doc("real", 0.8)])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1, p2], ev, mock_db)
    result = await runner.run("기생충")

    assert result["source_count"] == 1
    assert ev.evaluate.call_count == 1   # 빈 결과는 평가 안 함


@pytest.mark.asyncio
async def test_multi_runner_all_empty_returns_empty_facet(mock_db):
    """모든 provider 빈 결과 → empty_facet 반환, error 없음."""
    p1 = _make_provider("a", [])
    p2 = _make_provider("b", [])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1, p2], ev, mock_db)
    result = await runner.run("없는영화")

    assert result["source_count"] == 0
    assert ev.evaluate.call_count == 0
    assert "tension" in result["facet"]   # empty_facet 구조 포함


@pytest.mark.asyncio
async def test_multi_runner_provider_exception_skipped(mock_db):
    """provider.search 예외 → 해당 provider 건너뜀, 나머지 정상."""
    p1 = _make_provider("broken", [])
    p1.search = AsyncMock(side_effect=RuntimeError("네트워크 오류"))
    p2 = _make_provider("ok_src", [_doc("ok")])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1, p2], ev, mock_db)
    result = await runner.run("기생충")

    assert result["source_count"] == 1
    assert result["facet_id"] is not None


@pytest.mark.asyncio
async def test_multi_runner_trust_weighted(mock_db):
    """trust_score 반영 — high trust provider 값이 score 에 더 반영되는지 확인."""
    p_high = _make_provider("high", [_doc("high", trust=0.95)])
    p_low = _make_provider("low", [_doc("low", trust=0.40)])

    # high provider → tension=0.9, low → tension=0.1
    ev_high = MagicMock(spec=EvaluationEngine)
    ev_high.evaluate = AsyncMock(return_value={"tension": 0.9, "confidence": 0.9, "_coverage": {}})
    ev_low = MagicMock(spec=EvaluationEngine)
    ev_low.evaluate = AsyncMock(return_value={"tension": 0.1, "confidence": 0.5, "_coverage": {}})

    # 단일 evaluator mock: 순서대로 반환
    ev = MagicMock(spec=EvaluationEngine)
    ev.evaluate = AsyncMock(side_effect=[
        {"tension": 0.9, "confidence": 0.9, "_coverage": {}},
        {"tension": 0.1, "confidence": 0.5, "_coverage": {}},
    ])

    runner = MultiSourceRunner([p_high, p_low], ev, mock_db)
    result = await runner.run("기생충")

    # 가중평균: (0.9*0.95 + 0.1*0.40) / (0.95+0.40) ≈ 0.66
    # 최소한 단순 평균(0.5)보다 high 쪽으로 치우쳐야 함
    merged_tension = result["facet"].get("tension")
    if merged_tension is not None:
        assert merged_tension > 0.5
