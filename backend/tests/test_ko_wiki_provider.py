"""tests/test_ko_wiki_provider.py — KoreanWikiProvider 단위 테스트 (httpx mock)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from search.base import SearchQuery, SourceType
from search.ko_wiki_provider import KoreanWikiProvider


@pytest.fixture
def provider():
    return KoreanWikiProvider()


def _sq(title="기생충", **kwargs) -> SearchQuery:
    return SearchQuery(title=title, **kwargs)


def _wiki_response(page_id: str, title: str, extract: str) -> dict:
    return {"query": {"pages": {page_id: {"title": title, "extract": extract}}}}


def _mock_client(json_data: dict, status: int = 200):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def test_provider_name(provider):
    assert provider.provider_name == "kowiki"


def test_candidate_titles_no_year(provider):
    sq = _sq("기생충")
    titles = provider._candidate_titles(sq)
    assert titles == ["기생충", "기생충 (영화)"]


def test_candidate_titles_with_year(provider):
    sq = _sq("기생충", production_year=2019)
    titles = provider._candidate_titles(sq)
    assert "기생충 (2019년 영화)" in titles
    assert titles[0] == "기생충"


@pytest.mark.asyncio
async def test_search_success(provider):
    extract = "봉준호 감독의 2019년 영화. 전원백수 기택 가족이 고소득 박 사장 가족과 얽히는 이야기." * 3
    data = _wiki_response("123", "기생충 (영화)", extract)
    client = _mock_client(data)

    with patch("search.ko_wiki_provider.httpx.AsyncClient", return_value=client), \
         patch("search.ko_wiki_provider._ko_wiki_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(_sq("기생충"))

    assert len(docs) == 1
    d = docs[0]
    assert d.source_domain == "ko.wikipedia.org"
    assert d.source_type == SourceType.synopsis
    assert d.trust_score == 0.80
    assert "ko.wikipedia.org/wiki/" in d.url


@pytest.mark.asyncio
async def test_search_disambiguation_skipped(provider):
    extract = "다른 뜻에 대해서는 기생충 (동음이의어) 문서를 참조하십시오."
    data = _wiki_response("999", "기생충", extract)
    client = _mock_client(data)

    with patch("search.ko_wiki_provider.httpx.AsyncClient", return_value=client), \
         patch("search.ko_wiki_provider._ko_wiki_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(_sq("기생충"))

    assert docs == []


@pytest.mark.asyncio
async def test_search_page_not_found(provider):
    data = {"query": {"pages": {"-1": {"missing": True}}}}
    client = _mock_client(data)

    with patch("search.ko_wiki_provider.httpx.AsyncClient", return_value=client), \
         patch("search.ko_wiki_provider._ko_wiki_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(_sq("존재하지않는영화제목XYZ"))

    assert docs == []


@pytest.mark.asyncio
async def test_search_http_error_returns_empty(provider):
    client = _mock_client({}, status=503)

    with patch("search.ko_wiki_provider.httpx.AsyncClient", return_value=client), \
         patch("search.ko_wiki_provider._ko_wiki_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(_sq("기생충"))

    assert docs == []
