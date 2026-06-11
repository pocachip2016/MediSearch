"""tests/test_kmdb_provider.py — KmdbProvider 단위 테스트 (마크업 정제 + mock)."""
from unittest.mock import MagicMock, patch

import pytest

from search.kmdb_provider import KmdbProvider, clean_markup
from search.base import SearchQuery, SourceType


@pytest.fixture
def provider():
    return KmdbProvider()


def _sq(title="기생충", **kwargs) -> SearchQuery:
    return SearchQuery(title=title, **kwargs)


def test_provider_name(provider):
    assert provider.provider_name == "kmdb"


def test_clean_markup():
    assert clean_markup("!HS 기생충 !HE") == "기생충"
    assert clean_markup("파라노말  !HS 기생충 !HE") == "파라노말 기생충"
    assert clean_markup(None) == ""
    assert clean_markup("") == ""
    assert clean_markup("일반제목") == "일반제목"


def _mock_session(rows):
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = rows
    return session


@pytest.mark.asyncio
async def test_search_prefers_exact_after_clean(provider):
    """정제 후 정확매칭(기생충)을 부분매칭(마약기생충)보다 우선."""
    rows = [
        ("마약 !HS 기생충 !HE", "마약 줄거리", 2019, "한국", "범죄"),
        ("!HS 기생충 !HE", "전원백수 기택 가족...", 2019, "한국", "드라마"),
    ]
    with patch("search.kmdb_provider.get_mediax_session", return_value=_mock_session(rows)):
        docs = await provider.search(_sq("기생충"))

    assert len(docs) == 1
    assert docs[0].title == "기생충 (2019)"
    assert docs[0].source_domain == "kmdb.or.kr"
    assert docs[0].source_type == SourceType.synopsis
    assert docs[0].trust_score == 0.85
    assert "기택" in docs[0].text


@pytest.mark.asyncio
async def test_search_partial_fallback(provider):
    """정확매칭 없으면 부분매칭 폴백."""
    rows = [("마약 !HS 기생충 !HE", "마약 줄거리", 2019, "한국", "범죄")]
    with patch("search.kmdb_provider.get_mediax_session", return_value=_mock_session(rows)):
        docs = await provider.search(_sq("기생충"))
    assert len(docs) == 1
    assert docs[0].title == "마약 기생충 (2019)"


@pytest.mark.asyncio
async def test_search_no_session_returns_empty(provider):
    with patch("search.kmdb_provider.get_mediax_session", return_value=None):
        docs = await provider.search(_sq("기생충"))
    assert docs == []


@pytest.mark.asyncio
async def test_search_query_error_returns_empty(provider):
    session = MagicMock()
    session.execute.side_effect = Exception("db error")
    with patch("search.kmdb_provider.get_mediax_session", return_value=session):
        docs = await provider.search(_sq("기생충"))
    assert docs == []
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_search_by_docid_uses_docid_query(provider):
    """kmdb_docid 있을 때 docid 정확조회 쿼리 사용 확인."""
    rows = [("!HS 기생충 !HE", "시놉시스", 2019, "한국", "드라마")]
    session = _mock_session(rows)
    with patch("search.kmdb_provider.get_mediax_session", return_value=session):
        docs = await provider.search(_sq("기생충", kmdb_docid="K-20191234"))

    assert len(docs) == 1
    call_text = str(session.execute.call_args[0][0])
    assert "docid = :docid" in call_text


@pytest.mark.asyncio
async def test_search_doc_meta_populated(provider):
    """KmdbProvider search() 결과에 구조화 meta가 채워져야 함."""
    rows = [("!HS 기생충 !HE", "전원백수 기택 가족...", 2019, "한국", "드라마,스릴러")]
    with patch("search.kmdb_provider.get_mediax_session", return_value=_mock_session(rows)):
        docs = await provider.search(_sq("기생충"))

    meta = docs[0].meta
    assert meta is not None
    assert meta["content_type"] == "movie"
    assert meta["production_year"] == 2019
    assert "한국" in meta["countries"]
    assert "드라마" in meta["genres"]
    assert "스릴러" in meta["genres"]
