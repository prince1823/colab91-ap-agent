"""Central MLflow setup and configuration for DSPy tracing."""

import mlflow
from contextlib import contextmanager
from typing import Optional

from core.config import get_config

# Track if autolog has been initialized
_autolog_initialized = False


def setup_mlflow_tracing(experiment_name: Optional[str] = None, run_name: Optional[str] = None):
    """
    Set up MLflow tracing for DSPy.
    
    This function configures MLflow to automatically trace DSPy operations.
    It should be called once at the start of your application or before
    running agents that need tracing.
    
    Note: MLflow will automatically create traces for each DSPy operation.
    You don't need to manually start/end runs unless you want to group operations.
    
    Args:
        experiment_name: Name of the MLflow experiment. If None, uses config default.
        run_name: Name of the MLflow run. If None, MLflow will auto-generate traces.
    
    Example:
        >>> from core.utils.infrastructure.mlflow import setup_mlflow_tracing
        >>> setup_mlflow_tracing(experiment_name="column_canonicalization")
    """
    global _autolog_initialized
    
    config = get_config()
    
    # Only setup if MLflow is enabled
    if not config.mlflow.enabled:
        return
    
    # Set tracking URI (defaults to local file store if not specified)
    # If tracking_uri is None, MLflow uses file:./mlruns by default
    if config.mlflow.tracking_uri:
        mlflow.set_tracking_uri(config.mlflow.tracking_uri)
    
    # Set experiment name
    exp_name = experiment_name or config.mlflow.experiment_name
    mlflow.set_experiment(exp_name)
    
    # Enable DSPy autolog for automatic tracing
    # This automatically captures all DSPy module invocations
    # Safe to call multiple times - MLflow handles it gracefully
    if not _autolog_initialized:
        mlflow.dspy.autolog()
        _autolog_initialized = True
    
    # Start a run if run_name is provided (for grouping operations)
    # Otherwise, MLflow will create individual traces automatically
    if run_name or config.mlflow.run_name:
        run_name_to_use = run_name or config.mlflow.run_name
        mlflow.start_run(run_name=run_name_to_use)


@contextmanager
def mlflow_run(experiment_name: Optional[str] = None, run_name: Optional[str] = None):
    """
    Context manager for MLflow runs.
    
    Use this to group multiple operations under a single MLflow run.
    
    Args:
        experiment_name: Name of the MLflow experiment. If None, uses config default.
        run_name: Name of the MLflow run. If None, uses config default or auto-generated.
    
    Example:
        >>> from core.utils.infrastructure.mlflow import mlflow_run
        >>> with mlflow_run(experiment_name="column_canonicalization", run_name="test_run"):
        ...     agent.map_columns(client_schema)
    """
    config = get_config()
    
    if not config.mlflow.enabled:
        yield
        return
    
    # Setup tracing if not already done
    setup_mlflow_tracing(experiment_name=experiment_name)
    
    # Start a run
    exp_name = experiment_name or config.mlflow.experiment_name
    mlflow.set_experiment(exp_name)
    
    run_name_to_use = run_name or config.mlflow.run_name
    with mlflow.start_run(run_name=run_name_to_use):
        yield


def get_mlflow_tracking_uri() -> str:
    """Get the current MLflow tracking URI."""
    config = get_config()
    return config.mlflow.tracking_uri or "sqlite:///mlflow.db"


def is_mlflow_enabled() -> bool:
    """Check if MLflow tracing is enabled."""
    config = get_config()
    return config.mlflow.enabled

