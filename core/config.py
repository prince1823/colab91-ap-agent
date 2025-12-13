"""Configuration management for the AP Agent application."""

from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings

# Load environment variables from .env file in ops folder
env_path = Path(__file__).parent.parent / "ops" / ".env"
load_dotenv(dotenv_path=env_path)


class OpenAIConfig(BaseSettings):
    """OpenAI API configuration."""

    api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    model: str = Field(default="gpt-4o", alias="OPENAI_MODEL")
    temperature: float = Field(default=0.0, alias="OPENAI_TEMPERATURE")
    max_tokens: Optional[int] = Field(default=None, alias="OPENAI_MAX_TOKENS")
    timeout: int = Field(default=60, alias="OPENAI_TIMEOUT")

    class Config:
        env_file = "ops/.env"
        case_sensitive = False
        extra = "ignore"


class MLflowConfig(BaseSettings):
    """MLflow tracking configuration."""

    # Default to SQLite backend (recommended) instead of file store
    tracking_uri: Optional[str] = Field(
        default="sqlite:///mlflow.db", alias="MLFLOW_TRACKING_URI"
    )
    experiment_name: str = Field(default="ap-agent", alias="MLFLOW_EXPERIMENT_NAME")
    run_name: Optional[str] = Field(default=None, alias="MLFLOW_RUN_NAME")
    enabled: bool = Field(default=True, alias="MLFLOW_ENABLED")

    class Config:
        env_file = "ops/.env"
        case_sensitive = False
        extra = "ignore"


class AnthropicConfig(BaseSettings):
    """Anthropic API configuration."""
    
    api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    model: str = Field(default="claude-3-opus-20240229", alias="ANTHROPIC_MODEL")
    temperature: float = Field(default=0.0, alias="ANTHROPIC_TEMPERATURE")
    max_tokens: Optional[int] = Field(default=None, alias="ANTHROPIC_MAX_TOKENS")
    timeout: int = Field(default=60, alias="ANTHROPIC_TIMEOUT")
    
    class Config:
        env_file = "ops/.env"
        case_sensitive = False
        extra = "ignore"


class DSPyConfig(BaseSettings):
    """DSPy configuration."""

    cache_dir: Path = Field(
        default=Path(".dspy_cache"), alias="DSPY_CACHE_DIR"
    )
    max_bootstrapped_demos: int = Field(
        default=8, alias="DSPY_MAX_BOOTSTRAPPED_DEMOS"
    )
    max_labeled_demos: int = Field(default=16, alias="DSPY_MAX_LABELED_DEMOS")

    class Config:
        env_file = "ops/.env"
        case_sensitive = False
        extra = "ignore"


class AppConfig(BaseSettings):
    """Main application configuration."""

    # Application settings
    app_name: str = Field(default="colab91-ap-agent", alias="APP_NAME")
    debug: bool = Field(default=False, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Data paths
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    results_dir: Path = Field(default=Path("results"), alias="RESULTS_DIR")
    datasets_dir: Path = Field(default=Path("datasets"), alias="DATASETS_DIR")
    
    # Database configuration
    database_path: Path = Field(
        default=Path("data/classifications.db"), alias="DATABASE_PATH"
    )
    enable_classification_cache: bool = Field(
        default=False, alias="ENABLE_CLASSIFICATION_CACHE"
    )
    supplier_cache_max_age_days: Optional[int] = Field(
        default=None, alias="SUPPLIER_CACHE_MAX_AGE_DAYS"
    )
    """Maximum age in days for cached supplier profiles. If None, uses any cached profile.
    Set this to a value (e.g., 7) to invalidate stale profiles after research agent changes.
    """

    # Per-Agent LLM Selection
    column_canonicalization_llm: str = Field(
        default="openai", alias="COLUMN_CANONICALIZATION_LLM"
    )
    research_llm: str = Field(default="openai", alias="RESEARCH_LLM")
    spend_classification_llm: str = Field(
        default="openai", alias="SPEND_CLASSIFICATION_LLM"
    )
    context_prioritization_llm: str = Field(
        default="openai", alias="CONTEXT_PRIORITIZATION_LLM"
    )

    # LLM Provider Settings
    openai: OpenAIConfig = Field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = Field(default_factory=AnthropicConfig)

    # Search Provider Settings
    search_provider: str = Field(default="exa", alias="SEARCH_PROVIDER")
    exa_api_key: Optional[str] = Field(default=None, alias="EXA_API_KEY")
    exa_base_url: str = Field(default="https://api.exa.ai", alias="EXA_BASE_URL")
    exa_model: str = Field(default="exa", alias="EXA_MODEL")

    # MLflow configuration
    mlflow: MLflowConfig = Field(default_factory=MLflowConfig)

    # DSPy configuration
    dspy: DSPyConfig = Field(default_factory=DSPyConfig)

    # Storage configuration
    storage_type: str = Field(default="local", alias="STORAGE_TYPE")
    s3_bucket: Optional[str] = Field(default=None, alias="S3_BUCKET")
    s3_prefix: str = Field(default="benchmarks/", alias="S3_PREFIX")
    local_base_dir: str = Field(default="benchmarks", alias="LOCAL_BASE_DIR")

    # CORS configuration
    cors_origins: str = Field(default="", alias="CORS_ORIGINS")

    class Config:
        env_file = "ops/.env"
        case_sensitive = False
        extra = "ignore"

    def __init__(self, **kwargs):
        """Initialize configuration with nested settings."""
        super().__init__(**kwargs)
        # Ensure directories exist
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.dspy.cache_dir.mkdir(parents=True, exist_ok=True)
        # Ensure database directory exists
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


# Global configuration instance
config = AppConfig()


def get_config() -> AppConfig:
    """Get the global configuration instance."""
    return config


def reload_config() -> AppConfig:
    """Reload configuration from environment variables."""
    global config
    config = AppConfig()
    return config

