# MLflow Tracing Setup

This document explains how to use MLflow tracing for DSPy agents in this project.

## Overview

MLflow tracing provides comprehensive observability for DSPy operations, allowing you to:
- View detailed traces of all LLM calls
- Inspect inputs and outputs at each step
- Debug issues and understand agent behavior
- Track performance metrics

## Configuration

MLflow tracing is configured via environment variables in `ops/.env`:

```bash
# Enable/disable MLflow tracing (default: true)
MLFLOW_ENABLED=true

# MLflow tracking URI (optional)
# If not set, uses local file store: file:./mlruns
# For MLflow server: http://127.0.0.1:5000
MLFLOW_TRACKING_URI=http://127.0.0.1:5000

# Default experiment name
MLFLOW_EXPERIMENT_NAME=ap-agent

# Optional: Default run name
MLFLOW_RUN_NAME=
```

## Running MLflow Server (Optional)

If you want to use the MLflow UI, start a server:

```bash
# Using SQLite backend (recommended)
mlflow server --backend-store-uri sqlite:///mlflow.db

# Or using file store (default)
mlflow server

# Access UI at http://127.0.0.1:5000
```

## Usage

### Automatic Tracing

MLflow tracing is automatically enabled when you initialize agents:

```python
from core.agents.column_canonicalization import ColumnCanonicalizationAgent

# Tracing is enabled by default
agent = ColumnCanonicalizationAgent()

# Or disable tracing explicitly
agent = ColumnCanonicalizationAgent(enable_tracing=False)
```

### Manual Setup

You can also set up tracing manually:

```python
from core.utils.mlflow import setup_mlflow_tracing

# Setup tracing for a specific experiment
setup_mlflow_tracing(experiment_name="column_canonicalization")

# Now all DSPy operations will be traced
agent = ColumnCanonicalizationAgent(enable_tracing=False)
result = agent.map_columns(client_schema)
```

### Using Context Manager

For grouping multiple operations under a single run:

```python
from core.utils.mlflow import mlflow_run
from core.agents.column_canonicalization import ColumnCanonicalizationAgent

agent = ColumnCanonicalizationAgent(enable_tracing=False)

with mlflow_run(experiment_name="column_canonicalization", run_name="batch_processing"):
    result1 = agent.map_columns(schema1)
    result2 = agent.map_columns(schema2)
    # Both operations will be grouped under the same run
```

## Viewing Traces

### Using MLflow UI

1. Start MLflow server (if using remote tracking):
   ```bash
   mlflow server --backend-store-uri sqlite:///mlflow.db
   ```

2. Open browser to `http://127.0.0.1:5000`

3. Navigate to your experiment and click on "Traces" tab

4. Click on any trace to view detailed breakdown:
   - Input/output of each step
   - LLM prompts and responses
   - Tool invocations
   - Latency information

### Using File Store

If using local file store (default), traces are saved in `./mlruns/` directory. You can view them by starting MLflow UI pointing to that directory:

```bash
mlflow ui --backend-store-uri file:./mlruns
```

## Adding Tracing to Other Agents

To add MLflow tracing to other agents:

1. Import the setup function:
   ```python
   from core.utils.mlflow import setup_mlflow_tracing
   ```

2. Call it in the agent's `__init__` method:
   ```python
   def __init__(self, enable_tracing: bool = True):
       if enable_tracing:
           setup_mlflow_tracing(experiment_name="your_agent_name")
       # ... rest of initialization
   ```

That's it! MLflow will automatically capture all DSPy operations.

## Disabling Tracing

To disable tracing globally, set in `ops/.env`:

```bash
MLFLOW_ENABLED=false
```

Or disable per-agent:

```python
agent = ColumnCanonicalizationAgent(enable_tracing=False)
```

## References

- [DSPy Observability Tutorial](https://dspy.ai/tutorials/observability/)
- [MLflow Tracing Guide](https://mlflow.org/docs/latest/tracking/traces.html)

