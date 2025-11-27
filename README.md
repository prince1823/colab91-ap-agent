# colab91-ap-agent

Agentic system for Accounts Payable spend classification using DSPy.

## Overview

This system processes AP transaction data through multiple agents:
1. **Column Canonicalization Agent** - Maps client-specific column names to canonical schema
2. **Research Decision Agent** - Determines if supplier research is needed based on transaction data
3. **Research Agent** - Researches suppliers using Exa or other search tools to build supplier profiles
4. **L1 Classifier** - Classifies transactions into L1 taxonomy categories using transaction data only
5. **Spend Classification Agent** - Classifies transactions into L1-L5 taxonomy categories using supplier profiles, transaction data, and client-specific taxonomies

The pipeline uses multi-level caching to optimize performance:
- **Supplier profile caching** - Avoids duplicate research calls for the same supplier
- **Classification caching** - Database-backed caching at multiple levels (exact match, supplier+L1 match)

## Setup

### Prerequisites
- Python >=3.12,<3.14
- Poetry (for dependency management)

### Installation

1. **Clone the repository** (if not already done):
```bash
git clone <repository-url>
cd colab91-ap-agent
```

2. **Install dependencies using Poetry**:
```bash
poetry install
```

3. **Activate the Poetry shell** (optional, but recommended):
```bash
poetry shell
```

### Configuration

Create `ops/.env` file with required API keys and configuration:

```bash
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
```

**Note**: The `ops/` directory must exist. Create it if it doesn't:
```bash
mkdir -p ops
```

### Directory Structure Setup

The following directories are created automatically when needed:
- `data/` - Database files and cache data
- `results/` - Test and benchmark output files
- `.dspy_cache/` - DSPy cache directory

You may need to create these manually if they don't exist:
```bash
mkdir -p data results
```

## Usage

### Running Tests

All test scripts should be run with `PYTHONPATH=.` to ensure proper module imports:

```bash
# Test column canonicalization
PYTHONPATH=. poetry run python tests/test_canonicalization.py

# Test research agent
PYTHONPATH=. poetry run python tests/test_research.py

# Test classification agent
PYTHONPATH=. poetry run python tests/test_classification.py

# Test taxonomy converter
PYTHONPATH=. poetry run python tests/test_taxonomy_converter.py

# Test end-to-end pipeline
PYTHONPATH=. poetry run python tests/test_pipeline.py
```

**Note**: Test results are saved to `results/` directory with timestamps.

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

**Analyzing Benchmark Results**:

After running benchmarks, analyze the results:

```bash
# Analyze a specific benchmark folder
PYTHONPATH=. poetry run python benchmarks/analyze_benchmark.py default

# Analyze a custom benchmark
PYTHONPATH=. poetry run python benchmarks/analyze_benchmark.py random_test_bench
```

The analysis provides:
- Overall exact match accuracy
- Level-wise accuracy (L1, L2, L3, L4)
- Dataset breakdown
- Failure analysis by category
- Sample failures

**Creating Random Benchmarks**:

Create a new benchmark by randomly sampling from existing datasets:

```bash
# Create a random benchmark with default settings (10 samples per dataset)
PYTHONPATH=. poetry run python benchmarks/create_random_benchmark.py random_bench_1

# Create with custom number of samples
PYTHONPATH=. poetry run python benchmarks/create_random_benchmark.py random_bench_2 --samples-per-dataset 20

# Create from a specific source folder
PYTHONPATH=. poetry run python benchmarks/create_random_benchmark.py random_bench_3 --source-folder default

# Create with a random seed for reproducibility
PYTHONPATH=. poetry run python benchmarks/create_random_benchmark.py random_bench_4 --random-seed 42

# Create and immediately run the benchmark
PYTHONPATH=. poetry run python benchmarks/create_random_benchmark.py random_bench_5 --run-benchmark
```

**Arguments for `create_random_benchmark.py`**:
- `benchmark_name` (required) - Name of the new benchmark dataset
- `--samples-per-dataset` (optional, default: 10) - Number of random samples per dataset
- `--source-folder` (optional, default: "default") - Source folder to sample from
- `--random-seed` (optional) - Random seed for reproducibility
- `--run-benchmark` (flag) - Run the benchmark immediately after creation

**Note**: 
- The `benchmarks/` folder structure is gitignored. Create it locally as needed.
- Each dataset's `input.csv` can have any client-specific column names - they will be automatically canonicalized by the pipeline.
- Copy taxonomy files from `taxonomies/` folder to each dataset folder as `taxonomy.yaml`.
- The `taxonomies/` folder contains the original taxonomy files and is kept for reference.

### Using the Pipeline

#### Basic Usage

```python
from core.pipeline import SpendClassificationPipeline
import pandas as pd

# Initialize pipeline
pipeline = SpendClassificationPipeline(
    taxonomy_path="taxonomies/FOX_20230816_161348.yaml",
    enable_tracing=True  # Enable MLflow tracing (default: True)
)

# Load transaction data
df = pd.read_csv("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

# Process transactions
classified_df = pipeline.process_transactions(df)

# Results include:
# - All original columns (preserved)
# - Canonical columns (mapped from original)
# - Classification columns: L1, L2, L3, L4, L5
# - Metadata: override_rule_applied, reasoning
```

#### Advanced Usage

```python
# Process with custom parameters
classified_df, intermediate = pipeline.process_transactions(
    df,
    taxonomy_path="taxonomies/FOX_20230816_161348.yaml",  # Optional override
    return_intermediate=True,  # Get intermediate results
    max_workers=5,  # Parallel processing workers (default: 5)
    run_id="custom-run-id",  # Optional run ID for tracking
    dataset_name="fox"  # Optional dataset name for tracking
)

# Access intermediate results
mapping_result = intermediate['mapping_result']  # Column mapping result
supplier_profiles = intermediate['supplier_profiles']  # Cached supplier profiles
run_id = intermediate['run_id']  # Generated or provided run ID

# Check for errors
errors = classified_df.attrs.get('classification_errors', [])
if errors:
    print(f"Found {len(errors)} classification errors")
```

#### Pipeline Parameters

**`SpendClassificationPipeline.__init__()`**:
- `taxonomy_path` (str, required) - Path to taxonomy YAML file
- `enable_tracing` (bool, default: True) - Enable MLflow tracing for debugging

**`pipeline.process_transactions()`**:
- `df` (pd.DataFrame, required) - DataFrame with raw transaction data (client-specific column names)
- `taxonomy_path` (str, optional) - Override taxonomy path (default: uses pipeline's taxonomy_path)
- `return_intermediate` (bool, default: False) - Return intermediate results (mapping, supplier profiles, run_id)
- `max_workers` (int, default: 5) - Maximum number of parallel workers for classification
- `run_id` (str, optional) - Run ID (UUID) for tracking. If not provided, a new UUID is generated
- `dataset_name` (str, optional) - Dataset name (e.g., "fox", "innova") for tracking

**Returns**:
- If `return_intermediate=False`: `pd.DataFrame` with classification results
- If `return_intermediate=True`: `Tuple[pd.DataFrame, Dict]` containing results and intermediate data

## Project Structure

```
colab91-ap-agent/
├── core/
│   ├── agents/
│   │   ├── column_canonicalization/  # Column mapping agent
│   │   ├── research/                 # Supplier research agent
│   │   ├── research_decision/        # Research decision agent
│   │   └── spend_classification/    # Classification agents
│   │       ├── l1/                   # L1 classifier
│   │       └── full/                 # Full L1-L5 classifier
│   ├── database/                     # Database models and manager
│   ├── llms/                         # LLM provider abstractions
│   ├── tools/                        # External tools (search, etc.)
│   ├── utils/                        # Utility functions
│   ├── pipeline.py                   # End-to-end pipeline orchestrator
│   └── config.py                     # Configuration management
├── tests/                            # Test scripts
├── benchmarks/                       # Benchmark data and runners
│   ├── run_benchmark.py             # Main benchmark runner
│   ├── analyze_benchmark.py         # Benchmark analysis tool
│   ├── create_random_benchmark.py   # Random benchmark generator
│   └── [benchmark_folders]/          # Benchmark datasets
├── taxonomies/                       # Client taxonomy YAML files
├── extraction_outputs/               # Input transaction data (gitignored)
├── results/                          # Test and benchmark outputs (gitignored)
├── data/                             # Database files and cache (gitignored)
├── ops/                              # Operations configuration
│   └── .env                          # Environment variables (create this)
├── pyproject.toml                    # Poetry dependencies
└── README.md                         # This file
```

## Key Features

- **Multi-agent Architecture** - Specialized agents for each task (canonicalization, research decision, research, L1 classification, full classification)
- **Per-agent LLM selection** - Configure different LLMs for each agent via `.env` (OpenAI or Anthropic)
- **MLflow tracing** - Automatic tracing of DSPy programs for debugging and analysis
- **Multi-level caching**:
  - **Supplier profile caching** - In-memory cache to avoid duplicate research calls
  - **Classification caching** - Database-backed caching at multiple levels:
    - Exact match cache (supplier + transaction hash)
    - Supplier + L1 cache
- **Research decision optimization** - Intelligently decides when supplier research is needed
- **Parallel processing** - Configurable parallel processing for classification tasks
- **Taxonomy validation** - Validates classification results against taxonomy structure
- **Error handling** - Continues processing on individual failures with detailed error reporting
- **Run tracking** - Optional run IDs and dataset names for tracking and analysis

## Configuration Details

### Environment Variables

All configuration is done through environment variables in `ops/.env`. Here's a complete reference:

#### LLM Provider Selection
- `COLUMN_CANONICALIZATION_LLM` - LLM for column canonicalization ("openai" or "anthropic")
- `RESEARCH_LLM` - LLM for research agent ("openai" or "anthropic")
- `SPEND_CLASSIFICATION_LLM` - LLM for classification agents ("openai" or "anthropic")

#### OpenAI Settings
- `OPENAI_API_KEY` - Your OpenAI API key (required if using OpenAI)
- `OPENAI_MODEL` - Model name (default: "gpt-4o")
- `OPENAI_TEMPERATURE` - Temperature setting (default: 0.0)
- `OPENAI_TIMEOUT` - Request timeout in seconds (default: 60)

#### Anthropic Settings
- `ANTHROPIC_API_KEY` - Your Anthropic API key (required if using Anthropic)
- `ANTHROPIC_MODEL` - Model name (default: "claude-3-opus-20240229")
- `ANTHROPIC_TEMPERATURE` - Temperature setting (default: 0.0)
- `ANTHROPIC_TIMEOUT` - Request timeout in seconds (default: 60)

#### Search Provider Settings
- `SEARCH_PROVIDER` - Search provider ("exa" or other)
- `EXA_API_KEY` - Exa API key (required for supplier research)
- `EXA_BASE_URL` - Exa API base URL (default: "https://api.exa.ai")
- `EXA_MODEL` - Exa model name (default: "exa")

#### MLflow Settings
- `MLFLOW_ENABLED` - Enable/disable MLflow tracing (default: true)
- `MLFLOW_TRACKING_URI` - MLflow tracking URI (default: "sqlite:///mlflow.db")
- `MLFLOW_EXPERIMENT_NAME` - Experiment name (default: "ap-agent")
- `MLFLOW_RUN_NAME` - Optional run name

#### Database/Caching Settings
- `ENABLE_CLASSIFICATION_CACHE` - Enable database-backed classification caching (default: false)
- `DATABASE_PATH` - Path to SQLite database file (default: "data/classifications.db")

#### Application Settings
- `LOG_LEVEL` - Logging level ("DEBUG", "INFO", "WARNING", "ERROR")
- `DEBUG` - Enable debug mode (default: false)
- `DATA_DIR` - Data directory path (default: "data")
- `RESULTS_DIR` - Results directory path (default: "results")

### Database Caching

When `ENABLE_CLASSIFICATION_CACHE=true`, the pipeline uses a SQLite database to cache classification results at multiple levels:

1. **Exact Match Cache**: Caches results for exact supplier + transaction hash matches
2. **Supplier + L1 Cache**: Caches results for supplier + L1 category matches

This significantly speeds up processing when:
- Processing the same transactions multiple times
- Processing similar transactions from the same supplier
- Running benchmarks multiple times

**Note**: Cache is scoped per run ID. To use cached results across runs, use the same `run_id` parameter.

## Troubleshooting

### Common Issues

**1. ModuleNotFoundError when running scripts**
- **Solution**: Always use `PYTHONPATH=.` prefix: `PYTHONPATH=. poetry run python <script>`

**2. Missing API keys**
- **Solution**: Ensure `ops/.env` file exists and contains all required API keys
- Check that the `ops/` directory exists: `mkdir -p ops`

**3. Database errors**
- **Solution**: Ensure the `data/` directory exists and is writable
- The database file is created automatically if it doesn't exist

**4. Taxonomy file not found**
- **Solution**: Ensure taxonomy YAML files are in the `taxonomies/` folder
- For benchmarks, copy taxonomy files to each dataset folder as `taxonomy.yaml`

**5. MLflow connection errors**
- **Solution**: Check `MLFLOW_TRACKING_URI` in `.env`
- For SQLite backend, ensure the directory exists and is writable
- Set `MLFLOW_ENABLED=false` to disable MLflow if not needed

**6. Import errors**
- **Solution**: Make sure you've run `poetry install` to install all dependencies
- Activate the Poetry environment: `poetry shell`

### Getting Help

- Check the logs: Set `LOG_LEVEL=DEBUG` in `ops/.env` for detailed logging
- Review MLflow traces: If enabled, check MLflow UI for detailed execution traces
- Check error messages: The pipeline stores errors in `classification_errors` attribute on the result DataFrame

## Documentation

- `docs/architecture.md` - System architecture and design
- `docs/MLFLOW_TRACING.md` - MLflow tracing setup and usage
