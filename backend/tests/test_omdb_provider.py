"""tests/test_omdb_provider.py — OmdbProvider 단위 테스트 (httpx + quota mock)."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from search.base import SearchQuery, SourceType
from search.omdb_provider import OmdbProvider, _build_text, _build_meta, _parse_runtime_minutes, _parse_year_int


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


@pytest.mark.asyncio
async def test_search_doc_meta_populated(provider):
    """search() 결과에 구조화 meta 필드가 채워져야 함."""
    sq = _sq(imdb_id="tt6751668")
    hit = _omdb_hit(Type="movie", Runtime="132 min", Country="South Korea")
    client = _mock_client(hit)

    with patch("search.omdb_provider.httpx.AsyncClient", return_value=client), \
         patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=True), \
         patch("search.omdb_provider._omdb_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(sq)

    assert len(docs) == 1
    meta = docs[0].meta
    assert meta is not None
    assert meta["content_type"] == "movie"
    assert meta["production_year"] == 2019
    assert meta["runtime_minutes"] == 132
    assert "Bong Joon Ho" in meta["directors"]
    assert "Song Kang-ho" == meta["cast"][0]["name"]
    assert meta["cast"][0]["role"] is None


@pytest.mark.asyncio
async def test_search_series_type_param(provider):
    """content_type=series 힌트 → OMDb 검색 type=series 사용."""
    sq = _sq("Squid Game", content_type="series")
    hit = _omdb_hit(Title="Squid Game", Type="series", totalSeasons="2")
    client = _mock_client(hit)

    with patch("search.omdb_provider.httpx.AsyncClient", return_value=client), \
         patch("search.omdb_provider.settings.OMDB_API_KEY", "testkey"), \
         patch("search.omdb_provider._omdb_quota.consume", return_value=True), \
         patch("search.omdb_provider._omdb_throttle.wait", new_callable=AsyncMock):
        docs = await provider.search(sq)

    call_params = client.get.call_args[1]["params"]
    assert call_params.get("type") == "series"
    assert docs[0].meta["series"]["total_seasons"] == 2


class TestBuildMeta:
    def test_movie_type(self):
        data = _omdb_hit(Type="movie")
        m = _build_meta(data, None)
        assert m["content_type"] == "movie"

    def test_series_type(self):
        data = _omdb_hit(Type="series", totalSeasons="3")
        m = _build_meta(data, None)
        assert m["content_type"] == "series"
        assert m["series"]["total_seasons"] == 3

    def test_year_parse(self):
        data = _omdb_hit(Year="2003")
        m = _build_meta(data, None)
        assert m["production_year"] == 2003

    def test_year_range(self):
        data = _omdb_hit(Year="2021–2024")
        m = _build_meta(data, None)
        assert m["production_year"] == 2021

    def test_runtime_parse(self):
        data = _omdb_hit(Runtime="132 min")
        m = _build_meta(data, None)
        assert m["runtime_minutes"] == 132

    def test_na_fields_empty(self):
        data = {"Response": "True", "Title": "X", "Genre": "N/A", "Director": "N/A", "Actors": "N/A", "Country": "N/A", "Year": "2020", "Plot": "p"}
        m = _build_meta(data, None)
        assert m["genres"] == []
        assert m["directors"] == []
        assert m["cast"] == []
        assert m["countries"] == []


class TestParseHelpers:
    def test_runtime_minutes(self):
        assert _parse_runtime_minutes("132 min") == 132
        assert _parse_runtime_minutes("N/A") is None

    def test_year_int(self):
        assert _parse_year_int("2003") == 2003
        assert _parse_year_int("2021–2024") == 2021
        assert _parse_year_int("N/A") is None
