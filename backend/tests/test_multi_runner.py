"""tests/test_multi_runner.py — MultiSourceRunner + provider_factory 테스트."""
import asyncio
from datetime import datetime, timedelta
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
    # 기본 캐시 미스 — 캐시 히트 테스트에서는 개별 override
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None
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


# ── provider track separation ────────────────────────────────

def test_interactive_providers_excludes_playwright(monkeypatch):
    """INTERACTIVE_PROVIDERS는 playwright를 포함하지 않아야 한다."""
    monkeypatch.setattr("shared.config.settings.INTERACTIVE_PROVIDERS", "tmdb,kmdb,omdb,wikipedia,kowiki")
    monkeypatch.setattr("shared.config.settings.SEARCH_PROVIDERS", "")
    from main import _get_interactive_provider_names
    names = _get_interactive_provider_names()
    assert "playwright" not in names
    assert "tmdb" in names


def test_backfill_providers_includes_playwright(monkeypatch):
    """BACKFILL_PROVIDERS는 playwright를 포함해야 한다."""
    monkeypatch.setattr("shared.config.settings.BACKFILL_PROVIDERS", "tmdb,kmdb,playwright,wikipedia,kowiki,omdb")
    monkeypatch.setattr("shared.config.settings.SEARCH_PROVIDERS", "")
    from main import _get_backfill_provider_names
    names = _get_backfill_provider_names()
    assert "playwright" in names
    assert "tmdb" in names


def test_backfill_fallback_to_search_providers(monkeypatch):
    """BACKFILL_PROVIDERS 비어있으면 SEARCH_PROVIDERS 폴백."""
    monkeypatch.setattr("shared.config.settings.BACKFILL_PROVIDERS", "")
    monkeypatch.setattr("shared.config.settings.SEARCH_PROVIDERS", "fixture,playwright")
    from main import _get_backfill_provider_names
    names = _get_backfill_provider_names()
    assert names == ["fixture", "playwright"]


def test_interactive_fallback_to_search_providers(monkeypatch):
    """INTERACTIVE_PROVIDERS 비어있으면 SEARCH_PROVIDERS 폴백."""
    monkeypatch.setattr("shared.config.settings.INTERACTIVE_PROVIDERS", "")
    monkeypatch.setattr("shared.config.settings.SEARCH_PROVIDERS", "fixture,tmdb")
    from main import _get_interactive_provider_names
    names = _get_interactive_provider_names()
    assert names == ["fixture", "tmdb"]


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
async def test_multi_runner_on_event_fired(mock_db):
    """on_event 콜백이 search_start / provider_search / eval_start / provider_eval / merge 순으로 호출됨."""
    collected: list[str] = []

    async def cb(event_type: str, payload: dict):
        collected.append(event_type)

    p1 = _make_provider("src1", [_doc("src1", 0.9)])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1], ev, mock_db)
    await runner.run("기생충", on_event=cb)

    assert collected[0] == "search_start"
    assert "provider_search" in collected
    assert "eval_start" in collected
    assert "provider_eval" in collected
    assert collected[-1] == "merge"


@pytest.mark.asyncio
async def test_multi_runner_persist_false_no_db_write(mock_db):
    """persist=False 시 DB add 호출 없음(facet_id=None)."""
    p1 = _make_provider("src1", [_doc("src1", 0.9)])
    ev = _make_evaluator()

    runner = MultiSourceRunner([p1], ev, mock_db)
    result = await runner.run("기생충", persist=False)

    assert result["facet_id"] is None
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_multi_runner_concurrent_search(mock_db):
    """느린 provider가 빠른 provider의 SSE 방출을 막지 않음 (동시 실행 검증)."""
    arrival_order: list[str] = []

    slow = MagicMock(spec=SearchProvider)
    slow.provider_name = "slow"

    async def slow_search(q, num=5):
        await asyncio.sleep(0.05)
        arrival_order.append("slow")
        return [_doc("slow")]
    slow.search = slow_search

    fast = MagicMock(spec=SearchProvider)
    fast.provider_name = "fast"

    async def fast_search(q, num=5):
        arrival_order.append("fast")
        return [_doc("fast")]
    fast.search = fast_search

    ev = _make_evaluator()
    runner = MultiSourceRunner([slow, fast], ev, mock_db)

    events: list[str] = []

    async def cb(event_type, payload):
        if event_type == "provider_search":
            events.append(payload["provider"])

    await runner.run("테스트", on_event=cb)

    # 동시 실행: fast가 slow보다 먼저 완료·이벤트 방출
    assert "fast" in events and "slow" in events
    assert events.index("fast") < events.index("slow")


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


# ── derived-cache 테스트 ──────────────────────────────────────────────────────

def _make_fresh_facet(tmdb_id=96316, movie_query="기생충"):
    row = MagicMock(spec=MovieFacet)
    row.id = 42
    row.tmdb_id = tmdb_id
    row.movie_query = movie_query
    row.facet_json = {"primary_genre": "드라마", "tension": 0.8, "_coverage": {}}
    row.source_count = 3
    row.created_at = datetime.utcnow() - timedelta(days=1)
    return row


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_facet(mock_db):
    """DB에 fresh facet → 파이프라인 스킵, cached=True 반환."""
    fresh = _make_fresh_facet()
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = fresh

    ev = MagicMock(spec=EvaluationEngine)
    runner = MultiSourceRunner([], ev, mock_db)
    result = await runner.run("기생충", force_refresh=False)

    assert result["cached"] is True
    assert result["facet_id"] == 42
    ev.evaluate.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_runs_pipeline(mock_db):
    """캐시 미스(None) → 파이프라인 실행."""
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None

    p = MagicMock(spec=SearchProvider)
    p.provider_name = "fixture"
    p.search = AsyncMock(return_value=[])
    ev = MagicMock(spec=EvaluationEngine)
    runner = MultiSourceRunner([p], ev, mock_db)
    result = await runner.run("기생충")

    assert result.get("cached", False) is False


@pytest.mark.asyncio
async def test_force_refresh_skips_cache(mock_db):
    """force_refresh=True → fresh 캐시 있어도 파이프라인 실행."""
    fresh = _make_fresh_facet()
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = fresh

    p = MagicMock(spec=SearchProvider)
    p.provider_name = "fixture"
    p.search = AsyncMock(return_value=[])
    ev = MagicMock(spec=EvaluationEngine)
    runner = MultiSourceRunner([p], ev, mock_db)
    result = await runner.run("기생충", force_refresh=True)

    assert result.get("cached", False) is False
