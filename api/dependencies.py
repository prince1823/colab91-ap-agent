"""FastAPI dependencies for database and services."""

from functools import lru_cache

import dspy
from fastapi import Depends
from sqlalchemy.orm import Session

from api.services.dataset_service import DatasetService
from core.config import get_config
from core.database.schema import get_session_factory, init_database


@lru_cache()
def get_database_engine():
    """Get cached database engine."""
    config = get_config()
    return init_database(config.database_path)


@lru_cache()
def get_session_factory_cached():
    """Get cached session factory."""
    engine = get_database_engine()
    return get_session_factory(engine)


def get_db_session() -> Session:
    """
    Get database session with proper lifecycle management.

    Yields:
        SQLAlchemy session
    """
    SessionFactory = get_session_factory_cached()
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def get_lm() -> dspy.LM:
    """
    Get configured DSPy language model.

    Returns:
        DSPy language model instance
    """
    from core.llms.llm import get_llm_for_agent
    
    # Use the LLM factory which handles both OpenAI and Anthropic
    return get_llm_for_agent("spend_classification")


def get_dataset_service() -> DatasetService:
    """
    Get dataset service instance.

    Returns:
        DatasetService instance
    """
    return DatasetService()

