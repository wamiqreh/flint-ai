#!/usr/bin/env bash
set -euo pipefail

# Flint AI — Dev script: lint, test, format
# Usage: ./scripts/dev.sh [lint|test|format|check|all]

ACTION="${1:-all}"

install_dev_deps() {
    pip install -q ruff mypy pytest pytest-asyncio pytest-cov
}

run_lint() {
    echo "=== Linting with ruff ==="
    ruff check flint_ai/ tests/ scripts/
}

run_format_check() {
    echo "=== Format check with ruff ==="
    ruff format --check flint_ai/ tests/ scripts/
}

run_format() {
    echo "=== Formatting with ruff ==="
    ruff format flint_ai/ tests/ scripts/
    ruff check --fix flint_ai/ tests/ scripts/
}

run_typecheck() {
    echo "=== Type checking with mypy ==="
    mypy flint_ai/ --ignore-missing-imports --no-strict-optional
}

run_tests() {
    echo "=== Running tests ==="
    pytest tests/ -v --tb=short
}

run_all() {
    run_format
    run_lint
    run_typecheck
    run_tests
}

case "$ACTION" in
    lint)      install_dev_deps && run_lint ;;
    format)    install_dev_deps && run_format ;;
    check)     install_dev_deps && run_lint && run_format_check && run_typecheck ;;
    test)      install_dev_deps && run_tests ;;
    all)       install_dev_deps && run_all ;;
    *)
        echo "Usage: $0 [lint|test|format|check|all]"
        exit 1
        ;;
esac
