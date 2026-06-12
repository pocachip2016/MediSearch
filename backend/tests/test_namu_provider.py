"""tests/test_namu_provider.py — NamuHttpProvider 테스트 (mock httpx fetch)."""
import urllib.parse
from unittest.mock import AsyncMock, patch

import pytest

from search.namu_provider import (
    NamuHttpProvider,
    _extract_namu_url,
    _normalize_title,
    _verify_match,
)
from search.base import SearchQuery, SourceType


def _sq(title: str, **kw) -> SearchQuery:
    return SearchQuery(title=title, **kw)


@pytest.fixture
def provider():
    return NamuHttpProvider(timeout_s=15.0)


@pytest.fixture(autouse=True)
def no_throttle():
    """테스트에서 namu/DDG throttle 비활성화."""
    with patch("search.namu_provider._namu_throttle") as mn, \
         patch("search.namu_provider._ddg_throttle") as md:
        mn.wait = AsyncMock()
        md.wait = AsyncMock()
        yield


# ── 합성 namu HTML fixtures ───────────────────────────────────────────────────

DOC_OK = """<html><body><h1>기생충</h1>
<h2>1. 개요[편집]</h2><div><p>봉준호 감독의 2019년 한국 영화. 칸 영화제 황금종려상 수상작.</p></div>
<h2>2. 시놉시스[편집]</h2><div><p>전원 백수인 기택네 가족이 부잣집에 스며드는 블랙 코미디.</p></div>
<h2>3. 평가[편집]</h2><div><p>평단과 관객 모두에게 호평받은 걸작이라는 평가가 지배적.</p></div>
<h2>4. 흥행[편집]</h2><div><p>천만 관객을 돌파하며 흥행에도 성공했다.</p></div>
</body></html>"""

DOC_WRONG_MOVIE = """<html><body><h1>전우치</h1>
<h2>1. 개요[편집]</h2><div><p>2009년 개봉한 한국의 판타지 영화.</p></div>
</body></html>"""

DOC_DISAMBIG_HUB = """<html><body><h1>올드보이</h1>
<div><p>분류: 동음이의어 문서입니다.</p>
<p>1. Old boy 2. 만화 3. 영화 4. 개그 코너에 대한 문서 목록.</p></div>
</body></html>"""

DOC_PLOT_ONLY = """<html><body><h1>땅거미</h1>
<h2>1. 줄거리[편집]</h2><div><p>독립영화 땅거미의 줄거리가 여기에 서술되어 있다.</p></div>
</body></html>"""


def _mock_fetch(status: int, url: str, html: str):
    return AsyncMock(return_value=(status, url, html))


# ── 정규화/검증 게이트 단위 ────────────────────────────────────────────────────

def test_normalize_title_strips_paren_suffix():
    assert _normalize_title("올드보이(영화)") == "올드보이"
    assert _normalize_title("기생충 (2019년 영화)") == "기생충"
    assert _normalize_title("  올드 보이  ") == "올드보이"


def test_verify_match_bidirectional():
    assert _verify_match("기생충", "기생충")
    assert _verify_match("올드보이(영화)", "올드보이")
    assert not _verify_match("전우치", "올드보이")
    assert not _verify_match("", "올드보이")


# ── provider 기본 ─────────────────────────────────────────────────────────────

def test_provider_name(provider):
    assert provider.provider_name == "namu"


def test_build_urls_movie_first(provider):
    urls = provider._build_urls(_sq("기생충"))
    assert len(urls) == 2
    assert "%EC%98%81%ED%99%94" in urls[0]  # (영화) 인코딩 포함
    assert urls[0].startswith("https://namu.wiki/w/")


def test_build_urls_series_prefers_drama(provider):
    urls = provider._build_urls(_sq("오징어 게임", content_type="series"))
    assert "%EB%93%9C%EB%9D%BC%EB%A7%88" in urls[0]  # (드라마)
    assert "%EC%98%81%ED%99%94" not in urls[0]


# ── search 흐름 ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_extracts_sections(provider):
    """정상 문서 → 개요+시놉시스+평가 추출된 SourceDocument 1건."""
    provider._fetch = _mock_fetch(200, "https://namu.wiki/w/기생충(영화)", DOC_OK)
    docs = await provider.search(_sq("기생충", production_year=2019))
    assert len(docs) == 1
    doc = docs[0]
    assert doc.title == "기생충"
    assert doc.source_domain == "namu.wiki"
    assert doc.source_type == SourceType.synopsis
    assert doc.trust_score == 0.85
    assert "봉준호" in doc.text          # 개요
    assert "기택네" in doc.text          # 시놉시스
    assert "호평받은" in doc.text        # 평가 (감상평)
    assert "천만 관객" not in doc.text   # 다음 섹션(흥행) 미포함


@pytest.mark.asyncio
async def test_search_rejects_wrong_movie(provider):
    """제목 불일치 h1 → 폐기 (오염 차단 게이트)."""
    provider._fetch = _mock_fetch(200, "https://namu.wiki/w/전우치(영화)", DOC_WRONG_MOVIE)
    docs = await provider.search(_sq("올드보이"))
    assert docs == []


@pytest.mark.asyncio
async def test_search_skips_disambig_hub(provider):
    """동음이의 허브(제목 일치 + 개요 없음 + 마커) → 스킵."""
    provider._fetch = _mock_fetch(200, "https://namu.wiki/w/올드보이", DOC_DISAMBIG_HUB)
    docs = await provider.search(_sq("올드보이"))
    assert docs == []


@pytest.mark.asyncio
async def test_search_extracts_plot_only_doc(provider):
    """줄거리 h2만 있는 문서 → 추출 성공."""
    provider._fetch = _mock_fetch(200, "https://namu.wiki/w/땅거미", DOC_PLOT_ONLY)
    docs = await provider.search(_sq("땅거미"))
    assert len(docs) == 1
    assert "줄거리가 여기에" in docs[0].text


@pytest.mark.asyncio
async def test_search_404_tries_next_url(provider):
    """첫 URL 404 → 다음 후보 URL 시도."""
    provider._fetch = AsyncMock(
        side_effect=[
            (404, "https://namu.wiki/w/기생충(영화)", ""),
            (200, "https://namu.wiki/w/기생충", DOC_OK),
        ]
    )
    docs = await provider.search(_sq("기생충"))
    assert len(docs) == 1
    assert provider._fetch.call_count == 2


# ── N2: DDG 검색 폴백 ─────────────────────────────────────────────────────────

def _ddg_html(*namu_urls: str) -> str:
    """DDG 결과 anchor 포함 합성 HTML."""
    anchors = "\n".join(
        f'<a class="result__a" href="//duckduckgo.com/l/?uddg={urllib.parse.quote(u)}">'
        f'{u}</a>'
        for u in namu_urls
    )
    return f"<html><body>{anchors}</body></html>"


def test_extract_namu_url_decodes_uddg():
    """DDG redirect href → namu URL 정상 디코딩."""
    namu = "https://namu.wiki/w/올드보이(영화)"
    href = f"//duckduckgo.com/l/?uddg={urllib.parse.quote(namu)}&rut=abc"
    assert _extract_namu_url(href) == namu


def test_extract_namu_url_rejects_non_namu():
    """비 namu URL → None."""
    href = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fwikipedia.org%2Fw%2F%EC%98%AC%EB%93%9C%EB%B3%B4%EC%9D%B4"
    assert _extract_namu_url(href) is None


@pytest.mark.asyncio
async def test_resolve_via_search_year_scoring(provider):
    """DDG 결과: 2003/2013 두 후보 중 production_year=2003 것이 상위."""
    url_2003 = "https://namu.wiki/w/올드보이(2003년영화)"
    url_2013 = "https://namu.wiki/w/올드보이(2013년영화)"
    ddg_html = _ddg_html(url_2013, url_2003)  # 2013이 먼저지만 2003이 상위여야

    with patch("search.namu_provider.httpx") as mock_httpx:
        resp = AsyncMock()
        resp.status_code = 200
        resp.text = ddg_html
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=resp)
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        sq = _sq("올드보이", production_year=2003)
        urls = await provider._resolve_via_search(sq)

    assert len(urls) >= 1
    assert urls[0] == url_2003  # 연도 일치 → 상위


@pytest.mark.asyncio
async def test_resolve_via_search_empty_on_no_namu_links(provider):
    """DDG 결과에 namu 링크 없으면 빈 리스트."""
    ddg_html = "<html><body><a class='result__a' href='//duckduckgo.com/l/?uddg=https%3A%2F%2Fwikipedia.org%2F'>wiki</a></body></html>"

    with patch("search.namu_provider.httpx") as mock_httpx:
        resp = AsyncMock()
        resp.status_code = 200
        resp.text = ddg_html
        client_instance = AsyncMock()
        client_instance.get = AsyncMock(return_value=resp)
        mock_httpx.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=client_instance)
        mock_httpx.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        urls = await provider._resolve_via_search(_sq("올드보이"))

    assert urls == []


@pytest.mark.asyncio
async def test_search_triggers_ddg_fallback_after_disambig(provider):
    """동음이의 허브 → 직접 URL 큐 소진 → DDG 폴백 → 정상 문서 채택."""
    direct_url = "https://namu.wiki/w/올드보이(영화)"
    fallback_url = "https://namu.wiki/w/올드보이"  # DDG가 찾아준 다른 URL

    provider._fetch = AsyncMock(
        side_effect=[
            (200, direct_url, DOC_DISAMBIG_HUB),                          # 직접 URL → 동음이의 허브
            (200, fallback_url, DOC_OK.replace("기생충", "올드보이")),     # 폴백 URL → 정상 문서
        ]
    )
    provider._resolve_via_search = AsyncMock(return_value=[fallback_url])
    provider._build_urls = lambda q: [direct_url]  # 직접 후보 1개만

    docs = await provider.search(_sq("올드보이"))

    provider._resolve_via_search.assert_called_once()
    assert len(docs) == 1
