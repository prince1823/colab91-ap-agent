# colab91-ap-agent

Agentic system for Accounts Payable spend classification using DSPy.

## Overview

This system processes AP transaction data through three agents:
1. **Column Canonicalization Agent** - Maps client-specific column names to canonical schema
2. **Research Agent** - Researches suppliers using Exa or other search tools to build supplier profiles
3. **Spend Classification Agent** - Classifies transactions into L1-L5 taxonomy categories using supplier profiles, transaction data, and client-specific taxonomies

## Setup

### Prerequisites
- Python >=3.12,<3.14
- Poetry

### Installation

```bash
poetry install
```

### Configuration

Create `ops/.env` file with required API keys:

```bash
# LLM Configuration (per-agent selection)
COLUMN_CANONICALIZATION_LLM=openai  # or anthropic
RESEARCH_LLM=openai
SPEND_CLASSIFICATION_LLM=openai

# OpenAI
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-4o

# Anthropic (optional)
ANTHROPIC_API_KEY=your_key_here
ANTHROPIC_MODEL=claude-3-opus-20240229

# Exa Search (optional)
EXA_API_KEY=your_key_here
EXA_BASE_URL=https://api.exa.ai
EXA_MODEL=exa

# MLflow (optional)
MLFLOW_ENABLED=true
MLFLOW_TRACKING_URI=sqlite:///mlflow.db
MLFLOW_EXPERIMENT_NAME=ap-agent
```

## Usage

### Running Tests

```bash
# Test column canonicalization
PYTHONPATH=. poetry run python tests/test_canonicalization.py

# Test research agent
PYTHONPATH=. poetry run python tests/test_research.py

# Test classification agent
PYTHONPATH=. poetry run python tests/test_classification.py

# Test end-to-end pipeline
PYTHONPATH=. poetry run python tests/test_pipeline.py
```

Results are saved to `results/` directory.

### Running Benchmarks

```bash
# Run benchmark on default folder
PYTHONPATH=. poetry run python benchmarks/run_benchmark.py default
```

Benchmark expects:
- `benchmarks/{folder}/input.csv` - Transaction data with `taxonomy_path` column
- `benchmarks/{folder}/expected.txt` - One expected classification per line (format: "L1|L2|L3|...")

Output: `benchmarks/{folder}/output.csv` with input data, expected output, pipeline output, column mappings, and supplier profiles.

### Using the Pipeline

```python
from core.pipeline import SpendClassificationPipeline
import pandas as pd

# Initialize pipeline
pipeline = SpendClassificationPipeline(
    taxonomy_path="taxonomies/FOX_20230816_161348.yaml"
)

# Load transaction data
df = pd.read_csv("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

# Process transactions
classified_df = pipeline.process_transactions(df)

# Results include original columns + canonical columns + classification (L1-L5, confidence, reasoning)
```

## Project Structure

```
core/
├── agents/
│   ├── column_canonicalization/  # Column mapping agent
│   ├── research/                 # Supplier research agent
│   └── spend_classification/    # Classification agent
├── llms/                         # LLM provider abstractions
├── pipeline.py                   # End-to-end pipeline orchestrator
└── config.py                     # Configuration management

tests/                            # Test scripts
benchmarks/                       # Benchmark data and runner
taxonomies/                       # Client taxonomy YAML files
extraction_outputs/               # Input transaction data
results/                          # Test and benchmark outputs
```

## Key Features

- **Per-agent LLM selection** - Configure different LLMs for each agent via `.env`
- **MLflow tracing** - Automatic tracing of DSPy programs for debugging
- **Supplier profile caching** - Avoids duplicate research calls
- **Taxonomy validation** - Validates classification results against taxonomy structure
- **Error handling** - Continues processing on individual failures

## Documentation

- `docs/architecture.md` - System architecture and design
- `docs/MLFLOW_TRACING.md` - MLflow tracing setup and usage
