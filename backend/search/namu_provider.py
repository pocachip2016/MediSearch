"""search/namu_provider.py — httpx 기반 Namu.Wiki 직접 문서 크롤러.

namu는 plain HTTP GET에 풀 SSR HTML을 반환(실측 2026-06-13) → 브라우저 불필요.
검색 엔드포인트(/search?q=)는 봇 차단 → 직접 문서 URL(/w/{title}) 방식 유지.
CSS 클래스는 난독화 → h1/h2 구조 + 텍스트 노드에만 의존 (결정적 파싱, LLM digest 금지).

오염 차단: _verify_match 제목 검증 게이트 통과 문서만 채택.
동음이의 허브는 스킵 (N2에서 DDG 검색 폴백 연결 예정).
"""
from __future__ import annotations

import logging
import re
import urllib.parse

import httpx
from bs4 import BeautifulSoup, NavigableString

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.limiter import DomainThrottle
from shared.config import settings

logger = logging.getLogger(__name__)

# Namu.Wiki 최소 간격 throttle
_namu_throttle = DomainThrottle(min_interval_s=settings.NAMU_MIN_INTERVAL_S)
# DDG HTML 검색 폴백 throttle (폴백 시에만 발동)
_ddg_throttle = DomainThrottle(min_interval_s=5.0)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
}

# 동음이의 허브 페이지 마커 (본문 앞부분에 등장)
_DISAMBIG_MARKERS = ("다른 뜻에 대해서는", "동음이의어", "이 문서는 동음이의")

# 섹션 h2 키워드 → (추출 길이 상한)
_OVERVIEW_KEYWORDS = ("개요",)
_SYNOPSIS_KEYWORDS = ("시놉시스", "줄거리", "플롯")
_REVIEW_KEYWORDS = ("평가",)

# 제목 정규화: 후행 괄호 접미사 제거 (e.g. "올드보이(영화)" → "올드보이")
_TRAILING_PAREN_RE = re.compile(r"\([^)]*\)\s*$")


def _normalize_title(s: str) -> str:
    """비교용 제목 정규화 — 후행 괄호 제거 + 공백 제거 + casefold."""
    s = _TRAILING_PAREN_RE.sub("", s or "")
    return re.sub(r"\s+", "", s).casefold()


def _verify_match(h1_text: str, query_title: str) -> bool:
    """문서 h1 ↔ 검색 제목 양방향 포함 검사 (오염 차단 게이트)."""
    a, b = _normalize_title(h1_text), _normalize_title(query_title)
    return bool(a) and bool(b) and (a in b or b in a)


def _extract_namu_url(href: str) -> str | None:
    """DDG redirect href → namu.wiki 직접 URL 추출.

    DDG 형식: //duckduckgo.com/l/?uddg=<URL-encoded namu URL>&rut=...
    """
    if href.startswith("//duckduckgo.com/l/"):
        parsed = urllib.parse.urlparse("https:" + href)
        qs = urllib.parse.parse_qs(parsed.query)
        uddg = qs.get("uddg", [""])[0]
        if "namu.wiki" in uddg:
            return uddg
    elif "namu.wiki" in href:
        return href
    return None


def _section_text(soup: BeautifulSoup, keywords: tuple[str, ...], limit: int) -> str:
    """키워드가 포함된 h2 섹션부터 다음 h2 전까지의 텍스트 추출."""
    h2s = soup.find_all("h2")
    for idx, h2 in enumerate(h2s):
        if not any(k in h2.get_text() for k in keywords):
            continue
        end = h2s[idx + 1] if idx + 1 < len(h2s) else None
        texts: list[str] = []
        for el in h2.next_elements:
            if end is not None and el is end:
                break
            if isinstance(el, NavigableString):
                t = el.strip()
                if len(t) > 4:
                    texts.append(t)
        return " ".join(texts)[:limit]
    return ""


def _body_fallback_text(soup: BeautifulSoup, limit: int) -> str:
    """섹션 h2가 전무한 문서 — h1 이후 본문 앞부분 텍스트 폴백."""
    h1 = soup.find("h1")
    if h1 is None:
        return ""
    texts: list[str] = []
    total = 0
    for el in h1.next_elements:
        if isinstance(el, NavigableString):
            t = el.strip()
            if len(t) > 4:
                texts.append(t)
                total += len(t)
                if total >= limit:
                    break
    return " ".join(texts)[:limit]


class NamuHttpProvider(SearchProvider):
    """Namu.Wiki 직접 문서 URL 크롤러 (httpx + bs4, 브라우저 없음)."""

    def __init__(self, timeout_s: float = 15.0):
        self.timeout_s = timeout_s

    @property
    def provider_name(self) -> str:
        return "namu"

    def _build_urls(self, query: SearchQuery) -> list[str]:
        """시도 순서: {title}(영화|드라마) → {title}. series는 (드라마) 우선."""
        base = "https://namu.wiki/w"
        marker = "드라마" if query.content_type == "series" else "영화"
        candidates = [f"{query.title}({marker})", query.title]
        return [f"{base}/{urllib.parse.quote(t)}" for t in candidates]

    async def _fetch(self, client: httpx.AsyncClient, url: str) -> tuple[int, str, str]:
        """GET url → (status, final_url, html). 테스트에서 패치 지점."""
        resp = await client.get(url)
        return resp.status_code, str(resp.url), resp.text

    def _parse_doc(self, html: str, url: str, query: SearchQuery) -> SourceDocument | None:
        """HTML → 검증 게이트 + 섹션 추출 → SourceDocument. 부적합 시 None."""
        soup = BeautifulSoup(html, "lxml")

        h1 = soup.find("h1")
        title_text = h1.get_text(strip=True) if h1 else ""
        if not title_text:
            logger.warning(f"[namu] h1 없음: {url}")
            return None

        # 검증 게이트 — 제목 불일치 문서는 폐기 (오염 차단)
        if not _verify_match(title_text, query.title):
            logger.warning(
                f"[namu] 제목 불일치 — 폐기: h1={title_text!r} query={query.title!r}"
            )
            return None

        overview = _section_text(soup, _OVERVIEW_KEYWORDS, 1200)
        synopsis = _section_text(soup, _SYNOPSIS_KEYWORDS, 800)
        review = _section_text(soup, _REVIEW_KEYWORDS, 800)

        # 동음이의 허브 감지 — 개요 없음 + 마커 (제목은 일치할 수 있으므로 게이트 뒤에서 검사)
        if not overview:
            body_head = _body_fallback_text(soup, 600)
            if any(m in body_head for m in _DISAMBIG_MARKERS):
                logger.info(f"[namu] 동음이의 허브 감지 — 스킵: {url}")
                return None

        combined_text = "\n\n".join(filter(None, [overview, synopsis, review]))
        if not combined_text:
            combined_text = _body_fallback_text(soup, 1200)
        if not combined_text:
            logger.warning(f"[namu] 텍스트 추출 실패: {url}")
            return None

        # production_year soft 시그널 (차단하지 않음 — 본문 연도 표기 불안정)
        if query.production_year and str(query.production_year) not in combined_text[:2000]:
            logger.info(
                f"[namu] 연도 미발견(soft): {query.production_year} — {title_text!r}"
            )

        return SourceDocument(
            url=url,
            title=title_text,
            text=combined_text,
            source_domain="namu.wiki",
            source_type=SourceType.synopsis,
            trust_score=0.85,
        )

    async def _resolve_via_search(self, query: SearchQuery) -> list[str]:
        """DDG HTML 검색으로 namu 문서 URL 발견 — 직접 URL 실패/동음이의 시 폴백.

        Returns URL 리스트(빈 경우 graceful skip). N1 검증 게이트는 search()에서 재적용.
        """
        marker = "드라마" if query.content_type == "series" else "영화"
        q_parts = ["site:namu.wiki", query.title, marker]
        if query.production_year:
            q_parts.append(str(query.production_year))
        ddg_query = " ".join(q_parts)
        ddg_url = (
            f"https://html.duckduckgo.com/html/?q={urllib.parse.quote_plus(ddg_query)}"
        )

        try:
            await _ddg_throttle.wait()
            logger.info(f"[namu/ddg] 폴백 검색: {ddg_query!r}")
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=10.0
            ) as client:
                resp = await client.get(ddg_url)
                if resp.status_code >= 400:
                    logger.warning(f"[namu/ddg] HTTP {resp.status_code}")
                    return []
                soup = BeautifulSoup(resp.text, "lxml")
        except Exception as e:
            logger.warning(f"[namu/ddg] 검색 실패: {e}")
            return []

        norm_query = _normalize_title(query.title)
        candidates: list[tuple[int, str]] = []
        for a in soup.find_all("a", class_="result__a"):
            href = a.get("href", "")
            namu_url = _extract_namu_url(href)
            if not namu_url or "?noredirect" in namu_url:
                continue
            path = urllib.parse.urlparse(namu_url).path
            if not path.startswith("/w/"):
                continue
            doc_name = urllib.parse.unquote(path[3:])
            norm_doc = _normalize_title(doc_name)
            # 필수: 문서명 ↔ 검색 제목 양방향 포함 (전우치류 배제)
            if not norm_doc or not (norm_query in norm_doc or norm_doc in norm_query):
                continue
            score = 0
            if query.production_year and str(query.production_year) in doc_name:
                score += 2
            if f"({marker})" in doc_name:
                score += 1
            candidates.append((score, namu_url))

        candidates.sort(key=lambda x: x[0], reverse=True)
        top = [url for _, url in candidates[:2]]
        logger.info(f"[namu/ddg] {len(top)}개 후보 발견")
        return top

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """Namu.Wiki 직접 문서 URL 접근 → 검증 통과 문서 1건 반환.

        직접 URL 소진 또는 parse 실패 시 DDG 검색 폴백으로 URL 보강(1회).
        폴백 URL도 N1 검증 게이트 통과 후에만 채택.
        """
        results: list[SourceDocument] = []
        url_queue = self._build_urls(query)
        visited: set[str] = set()
        _ddg_resolved = False

        try:
            async with httpx.AsyncClient(
                headers=_HEADERS, follow_redirects=True, timeout=self.timeout_s
            ) as client:
                while url_queue:
                    url = url_queue.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)

                    try:
                        await _namu_throttle.wait()
                        logger.info(f"[namu] 접속: {url}")
                        status, final_url, html = await self._fetch(client, url)
                        if status >= 400:
                            logger.warning(f"[namu] HTTP {status}: {url}")
                            if not url_queue and not _ddg_resolved:
                                _ddg_resolved = True
                                fallback = await self._resolve_via_search(query)
                                url_queue.extend(u for u in fallback if u not in visited)
                            continue

                        doc = self._parse_doc(html, final_url, query)
                        if doc is None:
                            if not url_queue and not _ddg_resolved:
                                _ddg_resolved = True
                                fallback = await self._resolve_via_search(query)
                                url_queue.extend(u for u in fallback if u not in visited)
                            continue

                        results.append(doc)
                        logger.info(f"[namu] ✓ 크롤링: {doc.title!r}")
                        break  # 첫 번째 유효 결과로 충분

                    except httpx.HTTPError as e:
                        logger.warning(f"[namu] URL 실패 {url}: {e}")
                        if not url_queue and not _ddg_resolved:
                            _ddg_resolved = True
                            fallback = await self._resolve_via_search(query)
                            url_queue.extend(u for u in fallback if u not in visited)
                        continue

        except Exception as e:
            logger.error(f"[namu] 수집 오류: {e}", exc_info=True)

        logger.info(f"[namu] {query!r} → {len(results)}개 문서 반환")
        return results
