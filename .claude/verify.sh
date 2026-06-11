#!/bin/bash
# MediSearch verify script — pytest 실행

set -e
cd "$(dirname "$0")/../backend"

PYTEST=/home/ktalpha/Work/venv/bin/pytest

case "$1" in
  step1)
    $PYTEST tests/test_tmdb_provider.py tests/test_kmdb_provider.py tests/test_playwright_provider.py tests/test_api.py -v
    ;;
  step2)
    $PYTEST tests/test_api.py -v
    ;;
  step4)
    $PYTEST tests/test_evaluator.py -v
    ;;
  step5)
    $PYTEST tests/test_runner.py tests/test_api.py -v
    ;;
  step6|step7)
    $PYTEST tests/test_playwright_provider.py -v
    ;;
  step8)
    $PYTEST tests/test_playwright_integration.py -v -m integration
    ;;
  stepA)
    $PYTEST tests/test_tmdb_provider.py tests/test_kmdb_provider.py -v
    ;;
  step-c|stepC)
    $PYTEST tests/test_multi_runner.py tests/test_api.py -v
    ;;
  no-namu-fix)
    $PYTEST tests/test_multi_runner.py tests/test_api.py -v -k "not integration"
    ;;
  wiki-omdb)
    $PYTEST tests/test_ko_wiki_provider.py tests/test_omdb_provider.py tests/test_multi_runner.py -v -k "not integration"
    ;;
  step-disambig)
    $PYTEST tests/test_playwright_provider.py -v
    ;;
  score-tune)
    $PYTEST tests/test_score_calibration.py tests/test_evaluator.py -v
    ;;
  step9|stepB)
    $PYTEST tests/test_facet_merge.py -v
    ;;
  meta-step1)
    $PYTEST tests/test_metadata_schema.py tests/ -v -k "not integration"
    ;;
  meta-step2)
    $PYTEST tests/test_omdb_provider.py tests/test_kmdb_provider.py tests/test_tmdb_provider.py -v -k "not integration"
    ;;
  meta-step3)
    $PYTEST tests/test_metadata_merge.py -v
    ;;
  meta-step4)
    $PYTEST tests/test_metadata_extractor.py tests/test_evaluator.py -v -k "not integration"
    ;;
  meta-step5)
    $PYTEST tests/test_metadata_runner.py tests/ -v -k "not integration"
    ;;
  meta-step6)
    $PYTEST tests/test_api.py tests/ -v -k "not integration"
    ;;
  all)
    $PYTEST tests/ -v
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
