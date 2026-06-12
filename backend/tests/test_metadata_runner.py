"""tests/test_metadata_runner.py — MetadataRunner 단위 테스트."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.orm import Session

from models import MovieMeta, SearchSource
from pipeline.metadata_extractor import MetadataExtractionEngine
from pipeline.metadata_runner import MetadataRunner
from search.base import SearchProvider, SourceDocument, SourceType


# ── 공용 픽스처 ──────────────────────────────────────────────

@pytest.fixture
def mock_db():
    db = MagicMock(spec=Session)
    meta_counter = [0]

    def add_side_effect(obj):
        if isinstance(obj, MovieMeta):
            meta_counter[0] += 1
            obj.id = meta_counter[0]

    db.add.side_effect = add_side_effect
    # 기본 캐시 미스 — 캐시 히트 테스트에서는 개별 override
    db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None
    return db


def _make_provider(name: str, docs: list[SourceDocument]) -> SearchProvider:
    p = MagicMock(spec=SearchProvider)
    p.provider_name = name
    p.search = AsyncMock(return_value=docs)
    return p


def _make_extractor(meta: dict | None = None) -> MetadataExtractionEngine:
    ex = MagicMock(spec=MetadataExtractionEngine)
    ex.extract = AsyncMock(return_value=meta or {
        "content_type": "movie",
        "production_year": 2019,
        "genres": ["드라마"],
        "directors": ["봉준호"],
        "cast": [],
        "confidence": 0.7,
        "_coverage": {"source_count": 1, "by_type": {}, "has_expert": False, "has_user": False},
        "countries": [], "original_title": None, "runtime_minutes": None,
        "story": None, "keywords": [], "series": None, "_provenance": {},
    })
    ex.rewrite_story = AsyncMock(return_value="요약된 스토리")
    return ex


def _text_doc(provider_name: str, trust: float = 0.8) -> SourceDocument:
    """meta=None → LLM 경로"""
    return SourceDocument(
        url=f"https://{provider_name}.com/",
        title=provider_name,
        text="텍스트",
        source_domain=f"{provider_name}.com",
        source_type=SourceType.synopsis,
        trust_score=trust,
    )


def _structured_doc(provider_name: str, trust: float = 0.85, synopsis_raw=None) -> SourceDocument:
    """meta 있음 → 구조화 경로"""
    meta = {
        "content_type": "movie",
        "production_year": 2019,
        "genres": ["드라마"],
        "directors": ["봉준호"],
        "countries": ["한국"],
        "synopsis_raw": synopsis_raw,
    }
    return SourceDocument(
        url=f"https://{provider_name}.com/",
        title=provider_name,
        text="텍스트",
        source_domain=f"{provider_name}.com",
        source_type=SourceType.synopsis,
        trust_score=trust,
        meta=meta,
    )


# ── 테스트 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_structured_doc_no_extractor_call(mock_db):
    """meta 있는 doc은 extractor.extract 호출 안 함."""
    p = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충")

    ex.extract.assert_not_called()
    assert result["metadata"]["content_type"] == "movie"
    assert result["providers_detail"][0]["structured"] is True


@pytest.mark.asyncio
async def test_text_doc_calls_extractor(mock_db):
    """meta 없는 텍스트 doc은 extractor.extract 호출."""
    p = _make_provider("namu", [_text_doc("namu")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    await runner.run("기생충")

    ex.extract.assert_called_once()
    assert ex.extract.call_args[0][0] == "기생충"


@pytest.mark.asyncio
async def test_mixed_provider_structured_and_text(mock_db):
    """구조화 + 텍스트 provider 혼합 — 각각 적절한 경로 처리."""
    p_structured = _make_provider("omdb", [_structured_doc("omdb")])
    p_text = _make_provider("namu", [_text_doc("namu")])
    ex = _make_extractor()

    runner = MetadataRunner([p_structured, p_text], ex, mock_db)
    result = await runner.run("기생충")

    # 구조화는 extractor 미호출, 텍스트는 1회
    assert ex.extract.call_count == 1
    assert result["source_count"] == 2


@pytest.mark.asyncio
async def test_all_empty_returns_empty_meta(mock_db):
    """모든 provider 빈 결과 → empty_metadata 반환, 에러 없음."""
    p1 = _make_provider("a", [])
    p2 = _make_provider("b", [])
    ex = _make_extractor()

    runner = MetadataRunner([p1, p2], ex, mock_db)
    result = await runner.run("없는영화")

    assert result["source_count"] == 0
    assert result["metadata"]["content_type"] is None
    ex.extract.assert_not_called()


@pytest.mark.asyncio
async def test_require_web_no_web_docs_skipped(mock_db):
    """require_web=True 이고 웹 소스 없으면 skipped_reason=no_web."""
    p_db = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p_db], ex, mock_db)
    result = await runner.run("기생충", require_web=True)

    assert result["skipped_reason"] == "no_web"
    assert result["source_count"] == 0
    ex.extract.assert_not_called()


@pytest.mark.asyncio
async def test_require_web_with_web_docs_proceeds(mock_db):
    """require_web=True 이고 namu/wiki 결과 있으면 정상 처리."""
    p_namu = _make_provider("playwright", [_text_doc("playwright")])
    ex = _make_extractor()

    runner = MetadataRunner([p_namu], ex, mock_db)
    result = await runner.run("기생충", require_web=True)

    assert result["skipped_reason"] is None
    ex.extract.assert_called_once()


@pytest.mark.asyncio
async def test_story_fallback_called_when_no_story(mock_db):
    """병합 후 story 없고 synopsis_raw 있으면 rewrite_story 호출."""
    p = _make_provider("omdb", [_structured_doc("omdb", synopsis_raw="긴 원문 시놉시스...")])

    # extractor 없이 구조화 경로이므로 extract는 불리지 않지만 rewrite_story는 불림
    ex = _make_extractor(meta={
        "content_type": "movie", "production_year": 2019,
        "story": None,  # story 없음 → 폴백 트리거
        "genres": [], "directors": [], "cast": [], "countries": [],
        "original_title": None, "runtime_minutes": None,
        "keywords": [], "series": None, "_provenance": {},
        "confidence": 0.5,
        "_coverage": {"source_count": 0, "by_type": {}, "has_expert": False, "has_user": False},
    })

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충")

    ex.rewrite_story.assert_called_once()
    assert result["metadata"].get("story") == "요약된 스토리"


@pytest.mark.asyncio
async def test_save_sources_called(mock_db):
    """검색 결과가 SearchSource로 저장됨."""
    p = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충")

    # SearchSource add 확인
    added = [c.args[0] for c in mock_db.add.call_args_list if isinstance(c.args[0], SearchSource)]
    assert len(added) >= 1


@pytest.mark.asyncio
async def test_meta_id_returned(mock_db):
    """MovieMeta 저장 후 meta_id 반환."""
    p = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충")

    assert result["meta_id"] is not None


@pytest.mark.asyncio
async def test_metadata_runner_on_event_fired(mock_db):
    """on_event 콜백이 search_start / provider_search / extract_start / merge 순으로 호출됨."""
    collected: list[str] = []

    async def cb(event_type: str, payload: dict):
        collected.append(event_type)

    p = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    await runner.run("기생충", on_event=cb)

    assert collected[0] == "search_start"
    assert "provider_search" in collected
    assert "extract_start" in collected
    assert "merge" in collected


@pytest.mark.asyncio
async def test_metadata_runner_persist_false_no_db_write(mock_db):
    """persist=False 시 DB add 호출 없음(meta_id=None)."""
    p = _make_provider("omdb", [_structured_doc("omdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충", persist=False)

    assert result["meta_id"] is None
    mock_db.add.assert_not_called()


@pytest.mark.asyncio
async def test_providers_detail_includes_structured_flag(mock_db):
    """providers_detail에 structured 플래그 포함."""
    p = _make_provider("tmdb", [_structured_doc("tmdb")])
    ex = _make_extractor()

    runner = MetadataRunner([p], ex, mock_db)
    result = await runner.run("기생충")

    detail = result["providers_detail"][0]
    assert detail["provider"] == "tmdb"
    assert detail["structured"] is True
    assert detail["evaluated"] is False


# ── derived-cache 테스트 ──────────────────────────────────────────────────────

def _make_fresh_meta(tmdb_id=96316, movie_query="기생충"):
    row = MagicMock(spec=MovieMeta)
    row.id = 99
    row.tmdb_id = tmdb_id
    row.movie_query = movie_query
    row.meta_json = {"content_type": "movie", "production_year": 2019, "genres": ["드라마"]}
    row.source_count = 2
    row.created_at = datetime.utcnow() - timedelta(days=1)
    return row


@pytest.mark.asyncio
async def test_cache_hit_returns_cached_meta(mock_db):
    """DB에 fresh meta → 파이프라인 스킵, cached=True 반환."""
    fresh = _make_fresh_meta()
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = fresh

    ext = MagicMock(spec=MetadataExtractionEngine)
    runner = MetadataRunner([], ext, mock_db)
    result = await runner.run("기생충", force_refresh=False)

    assert result["cached"] is True
    assert result["meta_id"] == 99
    ext.extract.assert_not_called()


@pytest.mark.asyncio
async def test_cache_miss_runs_pipeline(mock_db):
    """캐시 미스(None) → 파이프라인 실행."""
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None

    p = MagicMock(spec=SearchProvider)
    p.provider_name = "fixture"
    p.search = AsyncMock(return_value=[])
    ext = MagicMock(spec=MetadataExtractionEngine)
    runner = MetadataRunner([p], ext, mock_db)
    result = await runner.run("기생충")

    assert result.get("cached", False) is False


@pytest.mark.asyncio
async def test_force_refresh_skips_cache(mock_db):
    """force_refresh=True → fresh 캐시 있어도 파이프라인 실행."""
    fresh = _make_fresh_meta()
    mock_db.query.return_value.filter.return_value.filter.return_value.order_by.return_value.first.return_value = fresh

    p = MagicMock(spec=SearchProvider)
    p.provider_name = "fixture"
    p.search = AsyncMock(return_value=[])
    ext = MagicMock(spec=MetadataExtractionEngine)
    runner = MetadataRunner([p], ext, mock_db)
    result = await runner.run("기생충", force_refresh=True)

    assert result.get("cached", False) is False
