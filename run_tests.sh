#!/bin/bash

# Test runner script for colab91-ap-agent
# Runs all tests with proper PYTHONPATH setup

set -e

echo "=========================================="
echo "Running colab91-ap-agent Tests"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_info() {
    echo -e "${YELLOW}→${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "pyproject.toml" ]; then
    echo "Error: pyproject.toml not found. Please run this script from the project root."
    exit 1
fi

# Check if Poetry is installed
if ! command -v poetry &> /dev/null; then
    echo "Error: Poetry not found. Please install Poetry first."
    exit 1
fi

# Run tests
TESTS=(
    "tests/test_canonicalization.py"
    "tests/test_research.py"
    "tests/test_classification.py"
    "tests/test_taxonomy_converter.py"
    "tests/test_pipeline.py"
)

FAILED_TESTS=()

for test in "${TESTS[@]}"; do
    if [ -f "$test" ]; then
        echo ""
        print_info "Running $test..."
        if PYTHONPATH=. poetry run python "$test"; then
            echo -e "${GREEN}✓${NC} $test passed"
        else
            echo -e "${RED}✗${NC} $test failed"
            FAILED_TESTS+=("$test")
        fi
    else
        echo -e "${YELLOW}⚠${NC} Test file not found: $test"
    fi
done

echo ""
echo "=========================================="
if [ ${#FAILED_TESTS[@]} -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed:${NC}"
    for test in "${FAILED_TESTS[@]}"; do
        echo "  - $test"
    done
    exit 1
fi
