#!/bin/bash
# MediSearch verify script — pytest 실행

set -e
cd "$(dirname "$0")/../backend"

PYTEST=/home/ktalpha/Work/venv/bin/pytest

case "$1" in
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
  all)
    $PYTEST tests/ -v
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
