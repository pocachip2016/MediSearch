"""search/playwright_provider.py — Playwright 기반 실제 웹 크롤링 제공자.

Namu.Wiki 영화 검색을 예시로 구현. 타 사이트로 확장 가능.
"""
from __future__ import annotations

import logging
from playwright.async_api import async_playwright

from search.base import SearchProvider, SourceDocument, SourceType

logger = logging.getLogger(__name__)


class PlaywrightProvider(SearchProvider):
    """Playwright 기반 실제 웹 크롤링 검색 제공자."""

    def __init__(self, headless: bool = True, timeout_ms: int = 10000):
        self.headless = headless
        self.timeout_ms = timeout_ms

    @property
    def provider_name(self) -> str:
        return "playwright"

    async def search(self, query: str, num: int = 5) -> list[SourceDocument]:
        """Namu.Wiki에서 영화 검색 → SourceDocument 리스트 반환."""
        results = []
        browser = None

        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=self.headless)
                page = await browser.new_page()

                # Namu.Wiki 검색
                search_url = f"https://namu.wiki/search?q={query}"
                logger.info(f"[playwright] 검색: {search_url}")

                try:
                    await page.goto(
                        search_url,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )
                except Exception as e:
                    logger.error(f"[playwright] 페이지 로딩 실패: {e}")
                    return []

                # 검색 결과 파싱
                try:
                    # 나무위키 검색 결과 구조
                    # <div class="search_item"> → <a class="wiki_link"> → title/href
                    items = await page.query_selector_all("div.search_item")
                    logger.info(f"[playwright] 검색 결과 {len(items)}개 발견")

                    for item in items[:num]:
                        try:
                            # 제목 + URL
                            link = await item.query_selector("a.wiki_link")
                            if not link:
                                continue

                            href = await link.get_attribute("href")
                            title_text = await link.inner_text()

                            if not href or not title_text:
                                continue

                            # 절대 URL 구성
                            url = href if href.startswith("http") else f"https://namu.wiki{href}"

                            # 스니펫 (미리보기) 추출
                            snippet_elem = await item.query_selector("div.desc")
                            snippet = ""
                            if snippet_elem:
                                snippet = await snippet_elem.inner_text()

                            # 신뢰도: 공식 위키는 높게 (영화 정보는 검증됨)
                            doc = SourceDocument(
                                url=url,
                                title=title_text,
                                text=snippet,
                                source_domain="namu.wiki",
                                source_type=SourceType.synopsis,
                                trust_score=0.85,
                            )
                            results.append(doc)
                            logger.info(f"✓ 크롤링: {title_text}")

                        except Exception as e:
                            logger.warning(f"[playwright] 아이템 파싱 오류: {e}")
                            continue

                except Exception as e:
                    logger.error(f"[playwright] 결과 파싱 실패: {e}")

                await browser.close()

        except Exception as e:
            logger.error(f"[playwright] 브라우저 오류: {e}", exc_info=True)

        logger.info(f"[playwright] {query} → {len(results)}개 문서 반환")
        return results
