"""Test script for end-to-end spend classification pipeline."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from core.pipeline import SpendClassificationPipeline

taxonomy_path = Path("taxonomies/FOX_20230816_161348.yaml")
transaction_csv = Path("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

if not taxonomy_path.exists():
    print(f"Taxonomy file not found: {taxonomy_path}")
    print("Please ensure taxonomy files are generated first.")
    exit(1)

if not transaction_csv.exists():
    print(f"Transaction data not found: {transaction_csv}")
    exit(1)

pipeline = SpendClassificationPipeline(
    taxonomy_path=str(taxonomy_path),
    enable_tracing=True
)

transaction_data = pd.read_csv(transaction_csv)

print("Processing transactions through full pipeline...")
classified_df = pipeline.process_transactions(transaction_data)

print(f"Processed {len(classified_df)} transactions")
print(f"Classification columns added: L1-L5, reasoning")

results_dir = Path("results")
results_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_csv_path = results_dir / f"pipeline_{timestamp}.csv"

classified_df.to_csv(output_csv_path, index=False)

print(f"Results saved to: {output_csv_path}")

errors = classified_df.attrs.get('classification_errors', [])
if errors:
    print(f"Note: {len(errors)} transactions had errors (see 'reasoning' column for details)")
