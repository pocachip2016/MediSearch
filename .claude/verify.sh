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
  score-tune)
    $PYTEST tests/test_score_calibration.py tests/test_evaluator.py -v
    ;;
  step9|stepB)
    $PYTEST tests/test_facet_merge.py -v
    ;;
  all)
    $PYTEST tests/ -v
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
