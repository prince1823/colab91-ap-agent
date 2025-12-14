#!/bin/bash

# Validation script for colab91-ap-agent
# This script checks if the project is set up correctly

set -e

echo "=========================================="
echo "colab91-ap-agent Setup Validation"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Track validation status
ERRORS=0
WARNINGS=0

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
    ((ERRORS++))
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
    ((WARNINGS++))
}

print_info() {
    echo -e "  ${YELLOW}→${NC} $1"
}

# Check Python version
echo "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ] && [ "$PYTHON_MINOR" -lt 14 ]; then
        print_success "Python version: $PYTHON_VERSION"
    else
        print_error "Python version: $PYTHON_VERSION (required: >=3.12,<3.14)"
    fi
else
    print_error "Python 3 not found"
fi

# Check Poetry
echo ""
echo "Checking Poetry..."
if command -v poetry &> /dev/null; then
    POETRY_VERSION=$(poetry --version | awk '{print $3}')
    print_success "Poetry installed: $POETRY_VERSION"
else
    print_error "Poetry not found"
fi

# Check required directories
echo ""
echo "Checking required directories..."
REQUIRED_DIRS=("ops" "data" "results")
for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        print_success "Directory exists: $dir"
    else
        print_error "Directory missing: $dir"
        print_info "Run: mkdir -p $dir"
    fi
done

# Check .env file
echo ""
echo "Checking environment configuration..."
ENV_FILE="ops/.env"
if [ -f "$ENV_FILE" ]; then
    print_success "Environment file exists: $ENV_FILE"
    
    # Check for API keys
    if grep -q "OPENAI_API_KEY=your_key_here" "$ENV_FILE" || ! grep -q "OPENAI_API_KEY=" "$ENV_FILE"; then
        print_warning "OPENAI_API_KEY not configured"
    else
        if grep -q "OPENAI_API_KEY=$" "$ENV_FILE" || grep -q "^OPENAI_API_KEY=your_key_here$" "$ENV_FILE"; then
            print_warning "OPENAI_API_KEY appears to be unset"
        else
            print_success "OPENAI_API_KEY is configured"
        fi
    fi
    
    if grep -q "ANTHROPIC_API_KEY=your_key_here" "$ENV_FILE" || ! grep -q "ANTHROPIC_API_KEY=" "$ENV_FILE"; then
        print_warning "ANTHROPIC_API_KEY not configured (optional)"
    else
        if grep -q "ANTHROPIC_API_KEY=$" "$ENV_FILE" || grep -q "^ANTHROPIC_API_KEY=your_key_here$" "$ENV_FILE"; then
            print_warning "ANTHROPIC_API_KEY appears to be unset (optional)"
        else
            print_success "ANTHROPIC_API_KEY is configured"
        fi
    fi
else
    print_error "Environment file missing: $ENV_FILE"
    print_info "Run: ./setup.sh to create it"
fi

# Check dependencies
echo ""
echo "Checking dependencies..."
if [ -f "poetry.lock" ]; then
    print_success "poetry.lock exists"
    
    # Try to check if dependencies are installed
    if poetry run python3 -c "import dspy" 2>/dev/null; then
        print_success "DSPy is installed"
    else
        print_error "DSPy not installed"
        print_info "Run: poetry install"
    fi
    
    if poetry run python3 -c "import pandas" 2>/dev/null; then
        print_success "Pandas is installed"
    else
        print_error "Pandas not installed"
    fi
    
    if poetry run python3 -c "import mlflow" 2>/dev/null; then
        print_success "MLflow is installed"
    else
        print_error "MLflow not installed"
    fi
else
    print_error "poetry.lock not found"
    print_info "Run: poetry install"
fi

# Check taxonomy files
echo ""
echo "Checking taxonomy files..."
if [ -d "taxonomies" ] && [ "$(ls -A taxonomies/*.yaml 2>/dev/null)" ]; then
    TAXONOMY_COUNT=$(ls -1 taxonomies/*.yaml 2>/dev/null | wc -l | tr -d ' ')
    print_success "Found $TAXONOMY_COUNT taxonomy file(s)"
else
    print_warning "No taxonomy files found in taxonomies/ directory"
fi

# Check database
echo ""
echo "Checking database..."
if [ -f "data/classifications.db" ]; then
    print_success "Database file exists: data/classifications.db"
    
    # Try to verify database schema
    if poetry run python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('.').absolute()))
from core.database.schema import init_database
from sqlalchemy import inspect
from core.config import get_config

config = get_config()
engine = init_database(config.database_path, echo=False)
inspector = inspect(engine)
tables = inspector.get_table_names()
expected = ['supplier_classifications', 'user_feedback', 'transaction_rules']
missing = [t for t in expected if t not in tables]
if missing:
    sys.exit(1)
" 2>/dev/null; then
        print_success "Database schema verified"
    else
        print_warning "Database exists but schema may be incomplete"
        print_info "Run: PYTHONPATH=. poetry run python init_database.py"
    fi
else
    print_warning "Database file not found"
    print_info "Run: PYTHONPATH=. poetry run python init_database.py"
fi

# Summary
echo ""
echo "=========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Validation completed with $WARNINGS warning(s)${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}✗ Validation failed with $ERRORS error(s) and $WARNINGS warning(s)${NC}"
    echo ""
    echo "To fix issues, run: ./setup.sh"
    echo ""
    exit 1
fi
