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
  all)
    $PYTEST tests/ -q --tb=short
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
