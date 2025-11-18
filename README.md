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

**Benchmark Structure**: Benchmarks are organized by dataset, with each dataset having its own folder containing schema-specific data:

```
benchmarks/
  ├── default/              # Full benchmark datasets
  │   ├── fox/
  │   │   ├── input.csv     # FOX-specific schema
  │   │   ├── expected.txt  # Expected classifications (one per line)
  │   │   ├── taxonomy.yaml # Taxonomy file for this dataset
  │   │   └── output.csv    # Generated results
  │   ├── innova/
  │   │   ├── input.csv     # Innova-specific schema
  │   │   ├── expected.txt
  │   │   ├── taxonomy.yaml
  │   │   └── output.csv
  │   ├── lifepoint/
  │   │   └── ...
  │   └── sp_global/
  │       └── ...
  └── test_bench/          # Quick test datasets (2 rows each)
      ├── fox/
      ├── innova/
      ├── lifepoint/
      └── sp_global/
```

**Required Files for Each Dataset Folder**:
- `input.csv` - Transaction data (client-specific schema)
- `expected.txt` - One expected classification per line (format: "L1|L2|L3|...")
- `taxonomy.yaml` - Taxonomy file for this dataset (copied from `taxonomies/` folder)

**Important**: 
- Each dataset has its own schema (different column names)
- Each dataset folder must contain a `taxonomy.yaml` file
- The `taxonomy.yaml` file defines the taxonomy structure for that dataset

**Sample `input.csv`** (FOX dataset example):

| Transaction ID | Amount | Supplier Name | Line Description | Business Unit | ... |
|----------------|--------|---------------|------------------|---------------|-----|
| 1000145200 | 3029.45 | effectv | tv media | tvkriv | ... |
| 10536747911 | 623.67 | dell marketing, l.p. | dell 34 curved monitor | digitl | ... |

**Note**: No `taxonomy_path` column needed - the `taxonomy.yaml` file in the same folder is used automatically.

**Sample `expected.txt`** (one classification per line, matching row order):

```
marketing & print|agency|agency fees
it & telecom|it products & services|it hardware & maintenance
```

**Running Benchmarks**:

The benchmark runner supports two modes:

**Mode 1: Process all datasets in a folder** (recommended for full benchmarks):
```bash
# Process all datasets in default folder
PYTHONPATH=. poetry run python benchmarks/run_benchmark.py default

# Process all datasets in test_bench folder
PYTHONPATH=. poetry run python benchmarks/run_benchmark.py test_bench
```

**Mode 2: Process a specific dataset**:
```bash
# Process only the fox dataset
PYTHONPATH=. poetry run python benchmarks/run_benchmark.py default/fox

# Process only innova from test_bench
PYTHONPATH=. poetry run python benchmarks/run_benchmark.py test_bench/innova
```

**Output**: Each dataset folder gets its own `output.csv` containing:

| Column | Description |
|--------|-------------|
| All original columns | All columns from `input.csv` (preserved as-is) |
| `expected_output` | Expected classification from `expected.txt` (format: "L1\|L2\|L3\|...") |
| `pipeline_output` | Actual classification produced by the pipeline (format: "L1\|L2\|L3\|...") |
| `columns_used` | JSON string of column mappings from canonicalization (same for all rows - canonicalization runs once per dataset) |
| `supplier_profile` | JSON string of supplier profile from research agent (includes official_business_name, industry, products_services, website_url, etc.) |
| `error` | Error message if processing failed (empty string if successful) |


**Example Output**:

```
Processing 4 datasets in benchmarks/test_bench

--- Processing fox ---
  Processed 2 rows
  Successful: 2/2
  Output saved to: benchmarks/test_bench/fox/output.csv

--- Processing innova ---
  Processed 2 rows
  Successful: 2/2
  Output saved to: benchmarks/test_bench/innova/output.csv

=== Overall Summary ===
Total datasets processed: 4
Total rows processed: 8
Total successful: 8/8
```

**Note**: 
- The `benchmarks/` folder structure is gitignored. Create it locally as needed.
- Each dataset's `input.csv` can have any client-specific column names - they will be automatically canonicalized by the pipeline.
- Copy taxonomy files from `taxonomies/` folder to each dataset folder as `taxonomy.yaml`.
- The `taxonomies/` folder contains the original taxonomy files and is kept for reference.

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
benchmarks/                       # Benchmark data and runner (create locally)
taxonomies/                       # Client taxonomy YAML files
extraction_outputs/               # Input transaction data (gitignored)
results/                          # Test and benchmark outputs (gitignored)
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
