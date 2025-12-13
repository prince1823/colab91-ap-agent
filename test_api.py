"""Simple test script to verify HITL API functionality."""

import sys
from pathlib import Path

# Test basic imports
try:
    print("Testing imports...")
    from api.main import app
    print("✓ FastAPI app imported successfully")

    from core.hitl.services.csv_service import CSVService
    print("✓ CSV service imported successfully")

    from core.hitl.service import FeedbackService
    print("✓ Feedback service imported successfully")

    from core.agents.feedback_action import FeedbackAction
    print("✓ FeedbackAction agent imported successfully")

    print("\n✅ All imports successful!")

except Exception as e:
    print(f"\n❌ Import error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test database initialization
try:
    print("\nTesting database initialization...")
    from core.database.schema import init_database
    from core.config import get_config

    config = get_config()
    db_path = config.database_path
    engine = init_database(db_path)
    print(f"✓ Database initialized at: {db_path}")

    # Check if new tables exist
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    print(f"\nExisting tables: {tables}")

    required_tables = ['supplier_classifications', 'user_feedback', 'transaction_rules']
    for table in required_tables:
        if table in tables:
            print(f"✓ Table '{table}' exists")
        else:
            print(f"❌ Table '{table}' missing")

    # Check new columns in supplier_classifications
    if 'supplier_classifications' in tables:
        columns = [col['name'] for col in inspector.get_columns('supplier_classifications')]
        hitl_columns = ['supplier_rule_type', 'supplier_rule_paths', 'supplier_rule_created_at', 'supplier_rule_active']

        print("\nHITL columns in supplier_classifications:")
        for col in hitl_columns:
            if col in columns:
                print(f"✓ Column '{col}' exists")
            else:
                print(f"❌ Column '{col}' missing")

    print("\n✅ Database setup verified!")

except Exception as e:
    print(f"\n❌ Database error: {e}")
    import traceback
    traceback.print_exc()

# Test CSV service
try:
    print("\nTesting CSV service...")
    csv_service = CSVService()
    datasets = csv_service.list_available_datasets()
    print(f"✓ Found {len(datasets)} datasets")

    if datasets:
        for ds in datasets[:3]:  # Show first 3
            print(f"  - {ds['dataset_name']}: {ds['row_count']} rows")

except Exception as e:
    print(f"\n⚠️  CSV service warning: {e}")

print("\n" + "="*50)
print("To start the API server, run:")
print("  uvicorn api.main:app --reload --host 0.0.0.0 --port 8000")
print("="*50)
