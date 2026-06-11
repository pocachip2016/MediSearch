"""search/playwright_provider.py — Playwright 기반 Namu.Wiki 직접 문서 크롤러.

검색 엔드포인트(/search?q=)는 봇 차단 → 직접 문서 URL(/w/{title}) 방식 사용.
CSS 클래스는 난독화되어 있으므로 h1/#app innerText 구조에만 의존.
"""
from __future__ import annotations

import logging
import urllib.parse

from playwright.async_api import async_playwright

from search.base import SearchProvider, SearchQuery, SourceDocument, SourceType
from shared.limiter import DomainThrottle
from shared.config import settings

logger = logging.getLogger(__name__)

# Namu.Wiki 최소 간격 throttle
_namu_throttle = DomainThrottle(min_interval_s=settings.NAMU_MIN_INTERVAL_S)

_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

_OVERVIEW_JS = """() => {
    const h2s = Array.from(document.querySelectorAll('h2'));
    const overviewH2 = h2s.find(h => h.textContent.includes('개요'));
    if (!overviewH2) return '';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let collecting = false;
    const texts = [];
    const startEl = overviewH2;
    const endEls = h2s.slice(h2s.indexOf(overviewH2) + 1);
    while (walker.nextNode()) {
        const node = walker.currentNode;
        const parent = node.parentElement;
        if (!collecting && parent && startEl.contains(parent)) {
            collecting = true;
        }
        if (collecting && endEls.some(h => h.contains(parent))) break;
        if (collecting) {
            const t = node.textContent.trim();
            if (t.length > 4) texts.push(t);
        }
    }
    return texts.join(' ').slice(0, 1200);
}"""

_SYNOPSIS_JS = """() => {
    const h2s = Array.from(document.querySelectorAll('h2'));
    const synH2 = h2s.find(h => h.textContent.includes('시놉시스'));
    if (!synH2) return '';
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let collecting = false;
    const texts = [];
    const startEl = synH2;
    const endEls = h2s.slice(h2s.indexOf(synH2) + 1);
    while (walker.nextNode()) {
        const node = walker.currentNode;
        const parent = node.parentElement;
        if (!collecting && parent && startEl.contains(parent)) {
            collecting = true;
        }
        if (collecting && endEls.some(h => h.contains(parent))) break;
        if (collecting) {
            const t = node.textContent.trim();
            if (t.length > 4) texts.push(t);
        }
    }
    return texts.join(' ').slice(0, 800);
}"""

_DISAMBIG_JS = """() => {
    const h2s = Array.from(document.querySelectorAll('h2'));
    const hasOverview = h2s.some(h => h.textContent.includes('개요'));
    const body = document.body.innerText.slice(0, 600);
    const markers = ['다른 뜻에 대해서는', '동음이의어', '이 문서는 동음이의'];
    return !hasOverview && markers.some(m => body.includes(m));
}"""

_MOVIE_LINK_JS = """() => {
    const links = Array.from(document.querySelectorAll('a[href*="/w/"]'));
    const found = links.find(a => {
        const href = decodeURIComponent(a.href || '');
        return href.includes('(%EC%98%81%ED%99%94)') || href.includes('(영화)');
    });
    return found ? found.href : null;
}"""


class PlaywrightProvider(SearchProvider):
    """Namu.Wiki 직접 문서 URL 크롤러."""

    def __init__(self, headless: bool = True, timeout_ms: int = 15000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    @property
    def provider_name(self) -> str:
        return "playwright"

    def _build_urls(self, query: str) -> list[str]:
        """시도 순서: {query}(영화) → {query}"""
        base = "https://namu.wiki/w"
        candidates = [f"{query}(영화)", query]
        return [f"{base}/{urllib.parse.quote(t)}" for t in candidates]

    async def search(self, query: SearchQuery, num: int = 5) -> list[SourceDocument]:
        """Namu.Wiki 직접 문서 URL 접근 → SourceDocument 반환.

        동음이의어 페이지 감지 시 (영화) 링크 자동 탐색.
        """
        results = []

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                )
                context = await browser.new_context(
                    user_agent=_USER_AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="ko-KR",
                )
                page = await context.new_page()
                await page.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"
                )

                url_queue = list(self._build_urls(query.title))
                visited: set[str] = set()
                followed_disambig = False

                while url_queue:
                    url = url_queue.pop(0)
                    if url in visited:
                        continue
                    visited.add(url)

                    try:
                        await _namu_throttle.wait()
                        logger.info(f"[playwright] 접속: {url}")
                        resp = await page.goto(
                            url,
                            wait_until="networkidle",
                            timeout=self.timeout_ms,
                        )
                        if resp and resp.status >= 400:
                            logger.warning(f"[playwright] HTTP {resp.status}: {url}")
                            continue

                        # 에러 페이지 판별
                        page_title = await page.title()
                        if "찾을 수 없습니다" in page_title or "오류" in page_title:
                            logger.info(f"[playwright] 에러 페이지 — 다음 URL 시도")
                            continue

                        # h1 대기 (렌더링 완료 기준)
                        await page.wait_for_selector("h1", timeout=8000)

                        # 동음이의어 페이지 감지 및 자동 탐색
                        is_disambig = await page.evaluate(_DISAMBIG_JS)
                        if is_disambig and not followed_disambig:
                            movie_link = await page.evaluate(_MOVIE_LINK_JS)
                            if movie_link:
                                logger.info(f"[playwright] 동음이의어 페이지 감지 → {movie_link}")
                                url_queue.insert(0, movie_link)
                                followed_disambig = True
                            else:
                                logger.info(f"[playwright] 동음이의어 — (영화) 링크 없음, 스킵")
                            continue

                        title_text = await page.evaluate(
                            "() => document.querySelector('h1')?.innerText || ''"
                        )
                        overview = await page.evaluate(_OVERVIEW_JS)
                        synopsis = await page.evaluate(_SYNOPSIS_JS)

                        combined_text = "\n\n".join(
                            filter(None, [overview, synopsis])
                        )
                        if not combined_text:
                            logger.warning(f"[playwright] 텍스트 추출 실패: {url}")
                            continue

                        doc = SourceDocument(
                            url=url,
                            title=title_text.strip(),
                            text=combined_text,
                            source_domain="namu.wiki",
                            source_type=SourceType.synopsis,
                            trust_score=0.85,
                        )
                        results.append(doc)
                        logger.info(f"[playwright] ✓ 크롤링: {title_text!r}")
                        break  # 첫 번째 유효 결과로 충분

                    except Exception as e:
                        logger.warning(f"[playwright] URL 실패 {url}: {e}")
                        continue

                await browser.close()

        except Exception as e:
            logger.error(f"[playwright] 브라우저 오류: {e}", exc_info=True)

        logger.info(f"[playwright] {query!r} → {len(results)}개 문서 반환")
        return results
