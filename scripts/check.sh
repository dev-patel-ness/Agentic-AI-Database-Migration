#!/bin/bash
# Lint and format check script for the project
# Usage: ./scripts/check.sh

set -e

echo "🔍 Running code quality checks..."
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

failed=0

# Black formatting check
echo "📋 Checking Black formatting..."
if poetry run black --check . 2>/dev/null; then
    echo -e "${GREEN}✓ Black check passed${NC}"
else
    echo -e "${YELLOW}⚠ Black formatting issues found. Run: poetry run black .${NC}"
    failed=$((failed + 1))
fi

# isort import sorting check
echo "📋 Checking isort import sorting..."
if poetry run isort --check-only . 2>/dev/null; then
    echo -e "${GREEN}✓ isort check passed${NC}"
else
    echo -e "${YELLOW}⚠ isort issues found. Run: poetry run isort .${NC}"
    failed=$((failed + 1))
fi

# flake8 linting
echo "📋 Running flake8 linting..."
if poetry run flake8 . 2>/dev/null; then
    echo -e "${GREEN}✓ flake8 check passed${NC}"
else
    echo -e "${YELLOW}⚠ flake8 issues found. See above for details.${NC}"
    failed=$((failed + 1))
fi

# mypy type checking
echo "📋 Running MyPy type checking..."
if poetry run mypy . --ignore-missing-imports 2>/dev/null; then
    echo -e "${GREEN}✓ MyPy check passed${NC}"
else
    echo -e "${YELLOW}⚠ MyPy issues found (non-blocking)${NC}"
fi

echo ""
echo "✅ Code quality check complete"

if [ $failed -gt 0 ]; then
    echo -e "${RED}⚠️  $failed check(s) failed${NC}"
    echo ""
    echo "To fix automatically:"
    echo "  1. Format code: poetry run black ."
    echo "  2. Sort imports: poetry run isort ."
    exit 1
else
    echo -e "${GREEN}All checks passed!${NC}"
    exit 0
fi
