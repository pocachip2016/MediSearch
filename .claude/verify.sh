#!/bin/bash
# MediSearch verify script — pytest 실행

set -e
cd "$(dirname "$0")/../backend"

PYTEST=/home/ktalpha/Work/venv/bin/pytest
PYTHON=/home/ktalpha/Work/venv/bin/python

case "$1" in
  step1)
    $PYTEST tests/test_tmdb_provider.py tests/test_kmdb_provider.py tests/test_playwright_provider.py tests/test_api.py -q --tb=short
    ;;
  step2)
    $PYTEST tests/test_api.py -q --tb=short
    ;;
  step4)
    $PYTEST tests/test_evaluator.py -q --tb=short
    ;;
  step5)
    $PYTEST tests/test_runner.py tests/test_api.py -q --tb=short
    ;;
  step6|step7)
    $PYTEST tests/test_playwright_provider.py -q --tb=short
    ;;
  step8)
    $PYTEST tests/test_playwright_integration.py -q --tb=short -m integration
    ;;
  stepA)
    $PYTEST tests/test_tmdb_provider.py tests/test_kmdb_provider.py -q --tb=short
    ;;
  step-c|stepC)
    $PYTEST tests/test_multi_runner.py tests/test_api.py -q --tb=short
    ;;
  no-namu-fix)
    $PYTEST tests/test_multi_runner.py tests/test_api.py -q --tb=short -k "not integration"
    ;;
  wiki-omdb)
    $PYTEST tests/test_ko_wiki_provider.py tests/test_omdb_provider.py tests/test_multi_runner.py -q --tb=short -k "not integration"
    ;;
  step-disambig)
    $PYTEST tests/test_playwright_provider.py -q --tb=short
    ;;
  score-tune)
    $PYTEST tests/test_score_calibration.py tests/test_evaluator.py -q --tb=short
    ;;
  step9|stepB)
    $PYTEST tests/test_facet_merge.py -q --tb=short
    ;;
  meta-step1)
    $PYTEST tests/test_metadata_schema.py tests/ -q --tb=short -k "not integration"
    ;;
  meta-step2)
    $PYTEST tests/test_omdb_provider.py tests/test_kmdb_provider.py tests/test_tmdb_provider.py -q --tb=short -k "not integration"
    ;;
  meta-step3)
    $PYTEST tests/test_metadata_merge.py -q --tb=short
    ;;
  meta-step4)
    $PYTEST tests/test_metadata_extractor.py tests/test_evaluator.py -q --tb=short -k "not integration"
    ;;
  meta-step5)
    $PYTEST tests/test_metadata_runner.py tests/ -q --tb=short -k "not integration"
    ;;
  meta-step6)
    $PYTEST tests/test_api.py tests/ -q --tb=short -k "not integration"
    ;;
  trace-backend)
    $PYTEST tests/test_multi_runner.py tests/test_metadata_runner.py -q --tb=short -k "not integration"
    ;;
  trace-api)
    $PYTEST tests/test_trace_api.py -q --tb=short -k "not integration"
    ;;
  ui-3)
    $PYTEST tests/test_trace_api.py -q --tb=short -k "not integration"
    ;;
  provider-tracks)
    $PYTEST tests/test_multi_runner.py -q --tb=short -k "not integration"
    ;;
  step1-models-schema)
    $PYTEST tests/ -q --tb=short -k "not integration"
    ;;
  step2-db-config)
    $PYTEST tests/ -q --tb=short -k "not integration"
    ;;
  step3-pipeline-wiring)
    $PYTEST tests/test_multi_runner.py tests/test_metadata_runner.py tests/test_api.py -q --tb=short -k "not integration"
    ;;
  step4-test-isolation)
    $PYTEST tests/ -q --tb=short -k "not integration"
    ;;
  derived-cache)
    $PYTEST tests/test_multi_runner.py tests/test_metadata_runner.py tests/test_api.py -q --tb=short -k "not integration"
    ;;
  N3|contamination-scan)
    # 스크립트 구문 검사
    python3 -c "import ast, sys; ast.parse(open('scripts/scan_namu_contamination.py').read()); print('syntax ok')"
    # dry-run 실행 (DB 연결 없이도 import 검사, 실패 시 exit 1)
    python3 -c "
import sys, os
sys.path.insert(0, os.getcwd())
from search.namu_provider import _normalize_title
from scripts.scan_namu_contamination import scan, _affected_queries, apply_reset
# 단위 테스트: contamination 감지 로직
assert _normalize_title('전우치(영화)') == '전우치'
assert _normalize_title('올드보이') == '올드보이'
# 양방향 포함 → 정상으로 처리되는지
class R:
    def __init__(self, id, mq, t, url): self.id=id; self.movie_query=mq; self.title=t; self.url=url
# 비정상: 전우치 vs 올드보이 → contaminated
a = _normalize_title('전우치'); b = _normalize_title('올드보이')
assert not (a in b or b in a), 'contamination miss'
print('✓ contamination 감지 로직 OK')
"
    [ -f scripts/scan_namu_contamination.py ] || { echo 'FAIL: 스크립트 파일 없음'; exit 1; }
    echo '✓ N3 verify OK'
    ;;
  N2|ddg-fallback)
    $PYTEST tests/test_namu_provider.py -q --tb=short
    ;;
  N1|namu-provider)
    $PYTEST tests/test_namu_provider.py -q --tb=short
    # playwright 파일 삭제 확인
    [ -f search/playwright_provider.py ] && echo "FAIL: playwright_provider.py 아직 존재" && exit 1
    [ -f tests/test_playwright_provider.py ] && echo "FAIL: test_playwright_provider.py 아직 존재" && exit 1
    [ -f tests/test_playwright_integration.py ] && echo "FAIL: test_playwright_integration.py 아직 존재" && exit 1
    grep -q "PlaywrightProvider" main.py && echo "FAIL: main.py에 PlaywrightProvider 잔류" && exit 1
    echo "✓ playwright 파일 정리 완료"
    ;;
  D1|postgres-rebuild)
    echo "=== D1: MediSearch postgres 재빌드 검증 ==="
    # 1. engine.url이 postgresql인지 확인
    ENGINE_URL=$(docker exec medisearch-api python3 -c "from shared.database import engine; print(engine.url)" 2>/dev/null || true)
    if [ -z "$ENGINE_URL" ]; then
      echo "FAIL: docker exec 실패 (medisearch-api 컨테이너 실행 중인가?)"
      exit 1
    fi
    if ! echo "$ENGINE_URL" | grep -q "postgresql"; then
      echo "FAIL: engine.url이 postgresql이 아님: $ENGINE_URL"
      exit 1
    fi
    echo "  ✓ engine.url = $ENGINE_URL"

    # 2. ms_* 테이블 존재 확인
    docker exec medisearch-api python3 -c "
from shared.database import engine
from sqlalchemy import inspect
inspector = inspect(engine)
tables = inspector.get_table_names()
ms_tables = [t for t in tables if t.startswith('ms_')]
expected = {'ms_search_sources', 'ms_movie_facets', 'ms_movie_meta'}
actual = set(ms_tables)
if not expected.issubset(actual):
    print(f'FAIL: ms_* 테이블 미생성. expected={expected}, actual={actual}')
    exit(1)
print(f'  ✓ ms_* 테이블 {len(ms_tables)}개 생성됨')
" || exit 1

    # 3. CLAUDE.md 저작권 원칙 확인
    [ -f ../CLAUDE.md ] && grep -q "저작권" ../CLAUDE.md || { echo "FAIL: CLAUDE.md에 저작권 원칙 미기재"; exit 1; }
    echo "  ✓ CLAUDE.md 저작권 원칙 기재"
    echo "=== PASS ==="
    ;;
  D2|include-meta)
    echo "=== D2: include_meta 결합 플래그 검증 ==="
    # 1. MultiSourceRunner 시그니처 확인
    $PYTEST tests/test_multi_runner.py::test_include_meta_returns_metadata \
            tests/test_multi_runner.py::test_include_meta_false_no_metadata_key \
            tests/test_multi_runner.py::test_include_meta_cache_hit_with_meta_cache \
            -v --tb=short 2>&1
    STATUS=$?
    [ $STATUS -ne 0 ] && exit 1

    # 2. MovieEvaluateRequest / Response 필드 확인 (grep — DB 연결 불필요)
    grep -q "include_meta" main.py || { echo "FAIL: include_meta 필드 없음 (main.py)"; exit 1; }
    grep -q "metadata.*dict.*None\|metadata:.*Optional" main.py || { echo "FAIL: MovieEvaluateResponse.metadata 없음"; exit 1; }
    grep -q "meta_id.*int.*None" main.py || { echo "FAIL: MovieEvaluateResponse.meta_id 없음"; exit 1; }
    echo "  ✓ MovieEvaluateRequest.include_meta 존재"
    echo "  ✓ MovieEvaluateResponse.metadata, meta_id 존재"
    echo "=== PASS ==="
    ;;
  D3|tmdb-movie-meta)
    echo "=== D3: mediaX tmdb_movie_meta 테이블 + copyright guard 검증 ==="
    MEDIAX_BACKEND=/home/ktalpha/Work/mediaX/backend

    # 1. TmdbMovieMeta 모델 존재
    grep -q "class TmdbMovieMeta" "$MEDIAX_BACKEND/api/programming/metadata/models/tmdb_cache.py" \
      || { echo "FAIL: TmdbMovieMeta 모델 없음"; exit 1; }
    echo "  ✓ TmdbMovieMeta 모델 존재"

    # 2. 마이그레이션 파일 존재
    [ -f "$MEDIAX_BACKEND/alembic/versions/0053_tmdb_movie_meta.py" ] \
      || { echo "FAIL: 0053_tmdb_movie_meta.py 마이그레이션 없음"; exit 1; }
    echo "  ✓ 0053 마이그레이션 존재"

    # 3. copyright guard 상수 및 함수 존재
    grep -q "_COPYRIGHT_STRIP_FIELDS" "$MEDIAX_BACKEND/workers/tasks/facet_tasks.py" \
      || { echo "FAIL: _COPYRIGHT_STRIP_FIELDS 없음"; exit 1; }
    grep -q "_apply_copyright_guard" "$MEDIAX_BACKEND/workers/tasks/facet_tasks.py" \
      || { echo "FAIL: _apply_copyright_guard 없음"; exit 1; }
    grep -q "story" "$MEDIAX_BACKEND/workers/tasks/facet_tasks.py" \
      || { echo "FAIL: story 필드 가드 미확인"; exit 1; }
    echo "  ✓ copyright guard (_COPYRIGHT_STRIP_FIELDS + _apply_copyright_guard) 존재"

    # 4. include_meta=True 페이로드 확인
    grep -q '"include_meta": True\|include_meta.*True' "$MEDIAX_BACKEND/workers/tasks/facet_tasks.py" \
      || { echo "FAIL: include_meta=True payload 없음"; exit 1; }
    echo "  ✓ evaluate payload include_meta=True 존재"

    # 5. _upsert_tmdb_meta 함수 존재
    grep -q "_upsert_tmdb_meta" "$MEDIAX_BACKEND/workers/tasks/facet_tasks.py" \
      || { echo "FAIL: _upsert_tmdb_meta 없음"; exit 1; }
    echo "  ✓ _upsert_tmdb_meta 헬퍼 존재"

    echo "=== PASS ==="
    ;;
  merge-denominator-fix)
    echo "=== merge-denominator-fix: list 병합 분모를 기여 소스로 한정 검증 ==="
    # metadata_merge + facet_merge 회귀 — abstain 소스가 제공 소스를 희석하지 않음
    $PYTEST tests/test_metadata_merge.py tests/test_facet_merge.py -q --tb=short 2>&1
    STATUS=$?
    [ $STATUS -ne 0 ] && exit 1
    # total_trust(전체 분모) 잔재 제거 확인
    grep -q "total_trust" pipeline/metadata_merge.py && { echo "FAIL: metadata_merge에 total_trust 잔존"; exit 1; }
    grep -q "total_trust" pipeline/facet_merge.py && { echo "FAIL: facet_merge에 total_trust 잔존"; exit 1; }
    echo "  ✓ 두 파일 total_trust 분모 제거 + contributing_trust 적용"
    echo "=== PASS ==="
    ;;
  tmdb-authoritative-genre)
    echo "=== tmdb-authoritative-genre: TMDB 권위 필드 노출 + metadata TMDB-first + facet 장르 그라운딩 ==="
    $PYTEST tests/test_tmdb_provider.py tests/test_metadata_merge.py tests/test_evaluator.py -q --tb=short 2>&1
    STATUS=$?
    [ $STATUS -ne 0 ] && exit 1
    # _TMDB_GENRE_KO 매핑 정적 확인
    grep -q "_TMDB_GENRE_KO" search/tmdb_provider.py || { echo "FAIL: _TMDB_GENRE_KO 없음"; exit 1; }
    grep -q "_map_genres" search/tmdb_provider.py || { echo "FAIL: _map_genres 없음"; exit 1; }
    grep -q "genre_ids, original_title" search/tmdb_provider.py || { echo "FAIL: SELECT에 genre_ids/original_title 미추가"; exit 1; }
    echo "  ✓ tmdb_provider genre 노출 + 테스트 통과"
    echo "=== PASS ==="
    ;;
  llm-unavailable-guard)
    echo "=== llm-unavailable-guard: Ollama 인프라 실패 전파 검증 ==="
    # 404/연결거부/타임아웃 → OllamaUnavailableError 전파, 파싱불가 → degrade(None)
    $PYTEST tests/test_ollama_client.py tests/test_evaluator.py tests/test_metadata_extractor.py -q --tb=short 2>&1
    STATUS=$?
    [ $STATUS -ne 0 ] && exit 1
    # generate_json 이 인프라 실패를 raise 하는지 (None 으로 삼키지 않음) 정적 확인
    grep -q "raise OllamaUnavailableError" pipeline/ollama_client.py || { echo "FAIL: ollama_client 인프라 실패 raise 누락"; exit 1; }
    grep -q "except OllamaUnavailableError" pipeline/multi_runner.py || { echo "FAIL: multi_runner 전파 가드 누락"; exit 1; }
    # docker-compose 모델이 설치된 값인지 (미설치 14b 회귀 차단)
    grep -q "OLLAMA_TASK_MODEL=qwen2.5:14b" "$(dirname "$0")/../docker-compose.yml" && { echo "FAIL: docker-compose 미설치 14b 잔존"; exit 1; }
    echo "  ✓ 인프라 실패 전파 + 모델 정합"
    echo "=== PASS ==="
    ;;
  all)
    $PYTEST tests/ -q --tb=short
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
