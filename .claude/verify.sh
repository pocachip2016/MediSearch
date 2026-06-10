#!/bin/bash
# MediSearch verify script — pytest 실행

set -e
cd "$(dirname "$0")/../backend"

case "$1" in
  step4)
    python -m pytest tests/test_evaluator.py -v
    ;;
  step5)
    python -m pytest tests/test_runner.py tests/test_api.py -v
    ;;
  step6)
    python -m pytest tests/test_playwright_provider.py -v
    ;;
  all)
    python -m pytest tests/ -v
    ;;
  *)
    echo "미지정: step ID $1"
    exit 1
    ;;
esac
