#!/bin/bash

# Setup script for colab91-ap-agent
# This script automates the initial setup of the project

set -e  # Exit on error

echo "=========================================="
echo "colab91-ap-agent Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "  ${YELLOW}→${NC} $1"
}

# Check prerequisites
echo "Step 1: Checking prerequisites..."
echo ""

# Check Python version
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -ge 12 ] && [ "$PYTHON_MINOR" -lt 14 ]; then
        print_success "Python version: $PYTHON_VERSION (required: >=3.12,<3.14)"
    else
        print_error "Python version: $PYTHON_VERSION (required: >=3.12,<3.14)"
        exit 1
    fi
else
    print_error "Python 3 not found. Please install Python >=3.12,<3.14"
    exit 1
fi

# Check Poetry
if command -v poetry &> /dev/null; then
    POETRY_VERSION=$(poetry --version | awk '{print $3}')
    print_success "Poetry version: $POETRY_VERSION"
else
    print_error "Poetry not found. Please install Poetry first."
    print_info "Install Poetry: curl -sSL https://install.python-poetry.org | python3 -"
    exit 1
fi

echo ""
echo "Step 2: Creating required directories..."
echo ""

# Create required directories
DIRS=("ops" "data" "results" ".dspy_cache")
for dir in "${DIRS[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        print_success "Created directory: $dir"
    else
        print_success "Directory already exists: $dir"
    fi
done

echo ""
echo "Step 3: Setting up environment file..."
echo ""

# Create .env file if it doesn't exist
ENV_FILE="ops/.env"
if [ ! -f "$ENV_FILE" ]; then
    cat > "$ENV_FILE" << 'EOF'
# LLM Configuration (per-agent selection)
# Options: "openai" or "anthropic"
COLUMN_CANONICALIZATION_LLM=openai
RESEARCH_LLM=openai
SPEND_CLASSIFICATION_LLM=openai

# OpenAI Configuration
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o
OPENAI_TEMPERATURE=0.0
OPENAI_TIMEOUT=60

# Anthropic Configuration (optional)
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-opus-20240229
ANTHROPIC_TEMPERATURE=0.0
ANTHROPIC_TIMEOUT=60

# Exa Search Configuration (optional, for supplier research)
EXA_API_KEY=your_key_here
EXA_BASE_URL=https://api.exa.ai
EXA_MODEL=exa
SEARCH_PROVIDER=exa

# MLflow Configuration (optional, for tracing and debugging)
MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_EXPERIMENT_NAME=ap-agent

# Database Configuration (optional, for classification caching)
ENABLE_CLASSIFICATION_CACHE=false
DATABASE_PATH=data/classifications.db

# Application Settings
LOG_LEVEL=INFO
DEBUG=false
EOF
    print_success "Created environment file: $ENV_FILE"
    print_warning "Please edit $ENV_FILE and add your API keys"
else
    print_success "Environment file already exists: $ENV_FILE"
fi

echo ""
echo "Step 4: Installing dependencies..."
echo ""

# Install dependencies with Poetry
if poetry install; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

echo ""
echo "Step 5: Verifying installation..."
echo ""

# Check if key modules can be imported
if poetry run python3 -c "import dspy; import pandas; import mlflow; print('OK')" 2>/dev/null; then
    print_success "Key dependencies verified"
else
    print_warning "Some dependencies may not be installed correctly"
fi

echo ""
echo "Step 6: Initializing database..."
echo ""

# Initialize database
if PYTHONPATH=. poetry run python3 init_database.py 2>/dev/null; then
    print_success "Database initialized successfully"
else
    print_warning "Database initialization failed or skipped (may need API keys configured)"
    print_info "You can run: PYTHONPATH=. poetry run python init_database.py"
fi

echo ""
echo "=========================================="
echo "Setup completed successfully!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit ops/.env and add your API keys"
echo "  2. Activate Poetry shell: poetry shell"
echo "  3. Initialize database (if not done): PYTHONPATH=. poetry run python init_database.py"
echo "  4. Run tests: PYTHONPATH=. poetry run python tests/test_pipeline.py"
echo "  5. Start API server: ./start_hitl_api.sh"
echo ""
echo "For more information, see README.md"
echo ""
