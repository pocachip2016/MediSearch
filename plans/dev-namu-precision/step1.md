# Step N1: namu-http-provider — httpx 기반 namu 수집기 교체

> GitHub: 미생성 | Milestone: dev-namu-precision

## 읽어야 할 파일
- backend/search/playwright_provider.py (대체 대상 — 추출 섹션 로직 참고)
- backend/search/base.py (SearchProvider ABC / SearchQuery / SourceDocument)
- backend/search/provider_factory.py
- backend/pipeline/multi_runner.py (require_namu 체크)

## 작업
1. `backend/search/namu_provider.py` 신규 — `NamuHttpProvider(SearchProvider)`:
   - httpx.AsyncClient GET (UA/Accept-Language, follow_redirects, timeout 15s) + `DomainThrottle(NAMU_MIN_INTERVAL_S)` 재사용
   - `_build_urls(query)`: `{title}(영화)`→`{title}`; series는 `{title}(드라마)` 우선
   - bs4(lxml) 파싱: h1 제목, h2 섹션 `개요`(≤1200자)+`시놉시스|줄거리|플롯`(≤800자)+`평가`(≤800자); 전무 시 본문 앞 ≤1200자 폴백
   - `_normalize_title` + `_verify_match(h1, query.title)` 검증 게이트 — 불일치 폐기
   - 동음이의: 리다이렉트(`?from=`)/개요 없음+동음이의 마커 → 스킵 (N2에서 DDG 폴백)
2. factory: `namu` 등록 + `playwright` 별칭(deprecation 로그) — compose env 무수정 호환
3. multi_runner: require_namu 체크 `"namu" or "playwright"` 대응
4. playwright_provider.py + test_playwright_provider.py 삭제 (dead code 금지)

## Acceptance Criteria
```bash
bash .claude/verify.sh N1
```
- pytest tests/test_namu_provider.py 통과 (정상 추출 / 제목 불일치 폐기 / 동음이의 스킵 / 드라마 URL 우선 / 줄거리만 추출)
- 라이브: 기생충(2019) → 올바른 문서 1건 (개요+시놉시스+평가), 오답 0건

## 금지사항
- raw HTML을 LLM에 digest시키지 마라. 이유: 환각·토큰비용 — 추출은 결정적 파싱, LLM은 facet 평가 단계만.
- `production_year` 불일치로 문서를 차단하지 마라. 이유: 본문 연도 표기 불안정 — soft 로그만, hard 게이트는 제목만.
