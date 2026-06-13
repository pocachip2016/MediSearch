# Step N2: ddg-search-fallback — DDG HTML 검색 폴백으로 namu URL 발견

> GitHub: 미생성 | Milestone: dev-namu-precision

## 읽어야 할 파일
- backend/search/namu_provider.py (N1 산출물)
- backend/shared/limiter.py (DomainThrottle)

## 작업
1. `_resolve_via_search(query)` — httpx GET `https://html.duckduckgo.com/html/?q=site:namu.wiki {title} 영화[ {year}]` (series는 `드라마`)
   - 앵커 파싱: `namu.wiki/w/` 링크만, `uddg=` 리다이렉트 파라미터 디코딩, `?noredirect=1` 제외
   - 스코어링(N1 `_normalize_title` 재사용): 필수 — 문서명에 title 포함; +2 연도 일치; +1 `(영화)`/`(드라마)` 마커. 상위 1~2개
   - DDG 전용 `DomainThrottle(min_interval_s≈5)`. 실패/0건 → graceful skip
2. search() 흐름: 직접 URL 소진 또는 동음이의 감지 → 검색 폴백 URL 큐 추가 → N1 검증 게이트 재적용(이중 안전망)

## Acceptance Criteria
```bash
bash .claude/verify.sh N2
```
- DDG 응답 mock 테스트: 올드보이(2003) 링크 선택 / 2003 vs 2013 연도 구분 / 검색 0건 → 빈 결과 / 동음이의 → 폴백 트리거
- 라이브: 올드보이(2003) → 박찬욱 영화 문서 채택, 전우치 오답 0건

## 금지사항
- 검색 폴백 결과를 검증 게이트 없이 채택하지 마라. 이유: 검색엔진 랭킹도 오답 가능 — 게이트가 최종 방어선.
