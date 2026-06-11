"""tests/test_omdb_provider.py — OmdbProvider 단위 테스트 (httpx + quota mock)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from search.base import SearchQuery, SourceType
from search.omdb_provider import OmdbProvider, _build_text


@pytest.fixture
def provider():
    return OmdbProvider()


def _sq(title="Parasite", **kwargs) -> SearchQuery:
    return SearchQuery(title=title, **kwargs)


def _omdb_hit(**overrides) -> dict:
    base = {
        "Response": "True",
        "Title": "Parasite",
        "Year": "2019",
        "Genre": "Comedy, Drama, Thriller",
        "Plot": "Greed and class discrimination threaten the newly formed symbiotic relationship.",
        "Director": "Bong Joon Ho",
        "Actors": "Song Kang-ho, Lee Sun-kyun",
        "Country": "South Korea",
        "imdbID": "tt6751668",
    }
    base.update(overrides)
    return base


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
    assert provider.provider_name == "omdb"


def test_build_text_full():
    data = _omdb_hit()
    text = _build_text(data)
    assert "Comedy" in text
    assert "Greed" in text
    assert "Bong Joon Ho" in text
    assert "Song Kang-ho" in text


def test_build_text_na_fields():
    text = _build_text({"Genre": "N/A", "Plot": "N/A", "Director": "N/A", "Actors": "N/A"})
    assert text == ""


@pytest.mark.asyncio
async def test_search_by_imdb_id(provider):
    sq = _sq(imdb_id="tt6751668")
    client = _mock_client(_omdb_hit())

    with patch("search.omdb_provider.httpx.AsyncClient", return_value=client), \
         patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=True), \
         patch("search.omdb_provider._omdb_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(sq)

    assert len(docs) == 1
    d = docs[0]
    assert d.source_domain == "omdbapi.com"
    assert d.source_type == SourceType.synopsis
    assert d.trust_score == 0.82
    assert "tt6751668" in d.url
    # imdb_id 조회 → title 폴백 없이 1회 호출
    assert client.get.call_count == 1


@pytest.mark.asyncio
async def test_search_by_title_fallback(provider):
    sq = _sq("Parasite", production_year=2019)
    client = _mock_client(_omdb_hit())

    with patch("search.omdb_provider.httpx.AsyncClient", return_value=client), \
         patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=True), \
         patch("search.omdb_provider._omdb_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(sq)

    assert len(docs) == 1
    call_params = client.get.call_args[1]["params"]
    assert call_params.get("t") == "Parasite"
    assert call_params.get("y") == "2019"


@pytest.mark.asyncio
async def test_search_quota_exceeded_returns_empty(provider):
    sq = _sq("Parasite")

    with patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=False):
        docs = await provider.search(sq)

    assert docs == []


@pytest.mark.asyncio
async def test_search_response_false_returns_empty(provider):
    client = _mock_client({"Response": "False", "Error": "Movie not found!"})

    with patch("search.omdb_provider.httpx.AsyncClient", return_value=client), \
         patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=True), \
         patch("search.omdb_provider._omdb_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(_sq("AlienFilmXYZ"))

    assert docs == []


@pytest.mark.asyncio
async def test_search_no_api_key_returns_empty(provider):
    with patch("search.omdb_provider.settings.OMDB_API_KEY", ""):
        docs = await provider.search(_sq("Parasite"))

    assert docs == []
