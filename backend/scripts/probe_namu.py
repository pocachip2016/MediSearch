"""scripts/probe_namu.py — Namu.Wiki 직접 문서 URL 셀렉터 탐색 스크립트.

검색 엔드포인트(/search)는 차단됨 → 직접 문서 URL(/w/<title>) 전략 검증.

사용법:
    python backend/scripts/probe_namu.py [영화제목]

기본: 기생충
"""
import asyncio
import sys
import urllib.parse
from playwright.async_api import async_playwright

QUERY = sys.argv[1] if len(sys.argv) > 1 else "기생충"
SUFFIXES = ["(영화)", "_(영화)", ""]
BASE = "https://namu.wiki/w"


def make_url(title: str) -> str:
    return f"{BASE}/{urllib.parse.quote(title)}"


async def probe():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="ko-KR",
        )
        page = await context.new_page()
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # 1) 여러 suffix 시도 → 유효한 URL 탐색
        target_url = None
        for suffix in SUFFIXES:
            url = make_url(f"{QUERY}{suffix}")
            print(f"[probe] 시도: {url}")
            try:
                resp = await page.goto(url, wait_until="networkidle", timeout=15000)
                title = await page.title()
                ok = "찾을 수 없습니다" not in title and "오류" not in title
                status = resp.status if resp else "?"
                print(f"  → 제목: {title!r}  status={status}  {'✓' if ok else '✗'}")
                if ok:
                    target_url = url
                    break
            except Exception as e:
                print(f"  → 오류: {e}")

        if not target_url:
            print("\n[probe] 유효한 URL을 찾지 못했습니다.")
            await browser.close()
            return

        print(f"\n[probe] 유효 URL: {target_url}\n")

        # 2) 본문 셀렉터 탐색
        print("=== 본문 컨테이너 셀렉터 ===")
        body_selectors = [
            "div.wiki-content",
            "div[class*='wiki']",
            "article",
            "div#content",
            "div.content",
            "section",
            "div[class*='content']",
        ]
        for sel in body_selectors:
            elems = await page.query_selector_all(sel)
            if elems:
                text = await elems[0].inner_text()
                print(f"  ✓ {sel!r}: {len(elems)}개  미리보기: {text[:80]!r}")
            else:
                print(f"  ✗ {sel!r}: 0개")
        print()

        # 3) 첫 번째 단락 텍스트 추출
        print("=== p 태그 첫 5개 텍스트 ===")
        paras = await page.query_selector_all("p")
        for p_elem in paras[:5]:
            text = (await p_elem.inner_text()).strip()
            if text:
                print(f"  p: {text[:100]!r}")
        print()

        # 4) 페이지 제목 h1/h2
        print("=== h1/h2 ===")
        for tag in ["h1", "h2"]:
            elems = await page.query_selector_all(tag)
            for e in elems[:3]:
                print(f"  {tag}: {(await e.inner_text())[:60]!r}")
        print()

        # 5) body > div 최상위 클래스
        print("=== body > div (최상위) ===")
        top_divs = await page.query_selector_all("body > div")
        for div in top_divs[:8]:
            cls = await div.get_attribute("class") or "(no class)"
            child_count = await div.evaluate("el => el.children.length")
            print(f"  div.{cls[:70]}  children={child_count}")
        print()

        # 6) div#app 자식 구조
        print("=== div#app > * 최상위 자식 ===")
        app_children = await page.query_selector_all("#app > *")
        for child in app_children[:10]:
            tag = await child.evaluate("el => el.tagName.toLowerCase()")
            cls = await child.get_attribute("class") or ""
            cid = await child.get_attribute("id") or ""
            n = await child.evaluate("el => el.children.length")
            print(f"  <{tag} class={cls[:40]!r} id={cid!r}> children={n}")
        print()

        # 7) h1 다음에 오는 구조 탐색 (개요 섹션 내용)
        print("=== h1 이후 첫 번째 텍스트 블록 (JavaScript 평가) ===")
        overview_text = await page.evaluate("""() => {
            const h1 = document.querySelector('h1');
            if (!h1) return 'h1 없음';
            let node = h1.nextElementSibling;
            const texts = [];
            let count = 0;
            while (node && count < 5) {
                const text = node.innerText || node.textContent || '';
                if (text.trim().length > 20) {
                    texts.push(text.trim().slice(0, 150));
                    count++;
                }
                node = node.nextElementSibling;
            }
            return texts.join('\\n---\\n');
        }""")
        print(overview_text[:600])
        print()

        # 8) h2[개요] 부모 컨텍스트 탐색
        print("=== h2[개요] 부모/형제 구조 ===")
        h2_context = await page.evaluate("""() => {
            const headings = Array.from(document.querySelectorAll('h2'));
            const overviewH2 = headings.find(h => h.textContent.includes('개요'));
            if (!overviewH2) return 'h2[개요] 없음';

            // 부모들 확인
            let parent = overviewH2.parentElement;
            const parentInfo = [];
            let depth = 0;
            while (parent && depth < 5) {
                parentInfo.push(`  [${depth}] <${parent.tagName.toLowerCase()} class="${(parent.className||'').slice(0,50)}" id="${parent.id||''}" children=${parent.children.length}>`);
                parent = parent.parentElement;
                depth++;
            }

            // 같은 부모 내 형제들
            const siblings = Array.from(overviewH2.parentElement.children);
            const sibInfo = siblings.slice(0, 8).map(s => {
                const text = (s.innerText || s.textContent || '').trim().slice(0, 80);
                return `  <${s.tagName.toLowerCase()} class="${(s.className||'').slice(0,30)}"> ${text}`;
            });

            return 'parents:\\n' + parentInfo.join('\\n') + '\\n\\nsiblings of h2 parent:\\n' + sibInfo.join('\\n');
        }""")
        print(h2_context[:1200])
        print()

        # 9) 전체 페이지 텍스트에서 핵심 내용 추출
        print("=== 전체 #app 텍스트 (처음 1000자) ===")
        app_text = await page.evaluate("""() => {
            const app = document.querySelector('#app');
            return app ? app.innerText.slice(0, 1000) : 'app 없음';
        }""")
        print(app_text)
        print()

        await browser.close()


if __name__ == "__main__":
    asyncio.run(probe())
