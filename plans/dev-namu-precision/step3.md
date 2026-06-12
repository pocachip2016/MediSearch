# Step N3: contamination-scan-reset — 과거 오염 스캔 + 재평가 리셋

> GitHub: 미생성 | Milestone: dev-namu-precision

## 읽어야 할 파일
- backend/models.py (SearchSource / MovieFacet)
- backend/search/namu_provider.py (_normalize_title 재사용)

## 작업
1. `backend/scripts/scan_namu_contamination.py` (일회성, dry-run 기본):
   - `ms_search_sources WHERE source_domain='namu.wiki'` → `_normalize_title`로 `title` vs `movie_query` 불일치 추출
   - 리포트: 영향 movie_query/tmdb_id 목록 + 건수
2. `--apply`: MediSearch `ms_movie_facets` 해당 행 삭제(30일 캐시 무효화) + mediaX `tmdb_movie_facets` 해당 행 삭제 → 드레인 체인 자동 재평가
3. dry-run 결과 사용자 승인 후에만 apply

## Acceptance Criteria
```bash
bash .claude/verify.sh N3
```
- dry-run 리포트 정상 출력, apply 후 mediaX에서 해당 tmdb_id pending 복귀 확인

## 금지사항
- dry-run 승인 없이 --apply 실행하지 마라. 이유: 삭제는 비가역.
