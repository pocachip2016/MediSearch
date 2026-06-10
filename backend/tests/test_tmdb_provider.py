"""tests/test_tmdb_provider.py — TmdbProvider 단위 테스트 (mediaX 세션 mock)."""
import datetime
from unittest.mock import MagicMock, patch

import pytest

from search.tmdb_provider import TmdbProvider, _trust_score
from search.base import SourceType


@pytest.fixture
def provider():
    return TmdbProvider()


def test_provider_name(provider):
    assert provider.provider_name == "tmdb"


def test_trust_score_scaling():
    assert _trust_score(0) == 0.7
    assert _trust_score(None) == 0.7
    assert _trust_score(10000) == 0.95
    assert _trust_score(20000) == 0.95  # cap


def _mock_session(rows):
    session = MagicMock()
    session.execute.return_value.fetchall.return_value = rows
    return session


@pytest.mark.asyncio
async def test_search_maps_rows(provider):
    rows = [
        ("기생충", "전원백수 기택 가족...", 20693, 34.6, datetime.date(2019, 5, 30)),
    ]
    with patch("search.tmdb_provider.get_mediax_session", return_value=_mock_session(rows)):
        docs = await provider.search("기생충")

    assert len(docs) == 1
    d = docs[0]
    assert d.title == "기생충 (2019)"
    assert d.source_domain == "themoviedb.org"
    assert d.source_type == SourceType.synopsis
    assert d.trust_score == 0.95  # vote_count 20693 → cap
    assert "기택" in d.text


@pytest.mark.asyncio
async def test_search_no_session_returns_empty(provider):
    with patch("search.tmdb_provider.get_mediax_session", return_value=None):
        docs = await provider.search("기생충")
    assert docs == []


@pytest.mark.asyncio
async def test_search_query_error_returns_empty(provider):
    session = MagicMock()
    session.execute.side_effect = Exception("db error")
    with patch("search.tmdb_provider.get_mediax_session", return_value=session):
        docs = await provider.search("기생충")
    assert docs == []
    session.close.assert_called_once()


@pytest.mark.asyncio
async def test_search_null_release_date(provider):
    rows = [("무제", "줄거리", 5, 1.0, None)]
    with patch("search.tmdb_provider.get_mediax_session", return_value=_mock_session(rows)):
        docs = await provider.search("무제")
    assert docs[0].title == "무제 (?)"
