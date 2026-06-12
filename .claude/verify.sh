#!/bin/bash
# MediSearch verify script — pytest 실행

set -e
cd "$(dirname "$0")/../backend"

PYTEST=/home/ktalpha/Work/venv/bin/pytest

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
  all)
    $PYTEST tests/ -q --tb=short
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
