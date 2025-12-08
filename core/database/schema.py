"""Database schema initialization."""

from pathlib import Path
from typing import Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.database.models import Base


def init_database(db_path: Path, echo: bool = False):
    """
    Initialize database and create tables.
    Handles schema migration for new fields (run_id, dataset_name).

    Args:
        db_path: Path to SQLite database file
        echo: Whether to echo SQL queries (for debugging)
    """
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Create engine
    engine = create_engine(f"sqlite:///{db_path}", echo=echo)

    # Create all tables
    Base.metadata.create_all(engine)
    
    # Handle migration for existing databases
    _migrate_existing_database(engine)

    return engine


def _migrate_existing_database(engine):
    """
    Migrate existing database to add run_id and dataset_name columns if they don't exist.
    Sets default run_id for existing entries.
    """
    from sqlalchemy import inspect, text
    
    try:
        inspector = inspect(engine)
        columns = [col['name'] for col in inspector.get_columns('supplier_classifications')]
        
        # Add run_id column if it doesn't exist
        if 'run_id' not in columns:
            with engine.connect() as conn:
                # SQLite doesn't support DEFAULT in ALTER TABLE, so add column then update
                conn.execute(text("ALTER TABLE supplier_classifications ADD COLUMN run_id VARCHAR(36)"))
                conn.execute(text("UPDATE supplier_classifications SET run_id = 'legacy' WHERE run_id IS NULL"))
                conn.commit()
        
        # Add dataset_name column if it doesn't exist
        if 'dataset_name' not in columns:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE supplier_classifications ADD COLUMN dataset_name VARCHAR(255)"))
                conn.commit()
        
        # Create indexes if they don't exist
        indexes = [idx['name'] for idx in inspector.get_indexes('supplier_classifications')]
        
        if 'idx_run_supplier_hash' not in indexes:
            with engine.connect() as conn:
                try:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_run_supplier_hash ON supplier_classifications(run_id, supplier_name, transaction_hash)"
                    ))
                    conn.commit()
                except Exception:
                    pass  # Index might already exist
        
        if 'idx_run_supplier_l1' not in indexes:
            with engine.connect() as conn:
                try:
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS idx_run_supplier_l1 ON supplier_classifications(run_id, supplier_name, l1_category)"
                    ))
                    conn.commit()
                except Exception:
                    pass  # Index might already exist
    except Exception:
        # Table might not exist yet (new database), that's fine
        pass


def get_session_factory(engine):
    """
    Get session factory for database operations.

    Args:
        engine: SQLAlchemy engine

    Returns:
        Session factory
    """
    return sessionmaker(bind=engine)

