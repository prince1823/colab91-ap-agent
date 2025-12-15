#!/usr/bin/env python3
"""Database initialization script.

This script initializes the database schema and runs any necessary migrations.
It can be run standalone or as part of the setup process.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.config import get_config
from core.database.schema import init_database
from sqlalchemy import inspect


def main():
    """Initialize database and verify setup."""
    print("=" * 50)
    print("Database Initialization")
    print("=" * 50)
    print()

    try:
        # Get configuration
        config = get_config()
        db_path = config.database_path

        print(f"Database path: {db_path}")
        print(f"Database directory: {db_path.parent}")
        print()

        # Ensure database directory exists
        db_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"✓ Database directory ready: {db_path.parent}")

        # Initialize database (creates tables and runs migrations)
        print()
        print("Initializing database schema...")
        engine = init_database(db_path, echo=False)
        print("✓ Database initialized successfully")

        # Verify tables were created
        print()
        print("Verifying database schema...")
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        # Expected tables
        expected_tables = [
            "supplier_classifications",
            "user_feedback",
            "transaction_rules",
            "supplier_direct_mappings",
            "supplier_taxonomy_constraints",
            "dataset_processing_states",
        ]

        print(f"Found {len(tables)} table(s):")
        for table in sorted(tables):
            marker = "✓" if table in expected_tables else "?"
            print(f"  {marker} {table}")

        # Check for expected tables
        missing_tables = [t for t in expected_tables if t not in tables]
        if missing_tables:
            print()
            print(f"⚠ Warning: Some expected tables are missing: {missing_tables}")
        else:
            print()
            print("✓ All expected tables are present")

        # Check indexes on supplier_classifications
        if "supplier_classifications" in tables:
            indexes = [idx["name"] for idx in inspector.get_indexes("supplier_classifications")]
            expected_indexes = ["idx_run_supplier_hash", "idx_supplier_hash"]
            print()
            print("Indexes on supplier_classifications:")
            for idx in sorted(indexes):
                marker = "✓" if idx in expected_indexes else "?"
                print(f"  {marker} {idx}")

        print()
        print("=" * 50)
        print("Database initialization completed successfully!")
        print("=" * 50)
        return 0

    except Exception as e:
        print()
        print("=" * 50)
        print(f"❌ Error initializing database: {e}")
        print("=" * 50)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
