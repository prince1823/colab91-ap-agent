"""Test script for column canonicalization agent."""

from datetime import datetime
from pathlib import Path

import pandas as pd
from core.agents.column_canonicalization import ColumnCanonicalizationAgent

transaction_csv = Path("extraction_outputs/FOX_20230816_161348/transaction_data.csv")

if not transaction_csv.exists():
    print(f"Transaction data not found: {transaction_csv}")
    exit(1)

transaction_data = pd.read_csv(transaction_csv, nrows=5)

agent = ColumnCanonicalizationAgent()
client_schema = agent.extract_schema_from_dataframe(transaction_data, sample_rows=3)
mapping_result = agent.map_columns(client_schema)

print(f"Confidence: {mapping_result.confidence}")
print(f"Mappings: {len(mapping_result.mappings)}")
if mapping_result.validation_errors:
    print(f"Validation Errors: {len(mapping_result.validation_errors)}")

canonical_df = None
if mapping_result.validation_passed:
    canonical_df = agent.apply_mapping(transaction_data, mapping_result)

results_dir = Path("results")
results_dir.mkdir(exist_ok=True)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_csv_path = results_dir / f"canonicalization_{timestamp}.csv"

results_data = []

for idx, row in transaction_data.iterrows():
    row_data = {"row_index": idx}
    
    for col in transaction_data.columns:
        row_data[f"original_{col}"] = row[col] if pd.notna(row[col]) else ""
    
    if canonical_df is not None and idx < len(canonical_df):
        canonical_row = canonical_df.iloc[idx]
        for col in canonical_df.columns:
            row_data[f"canonical_{col}"] = canonical_row[col] if pd.notna(canonical_row[col]) else ""
    
    results_data.append(row_data)

results_df = pd.DataFrame(results_data)
combined_df = results_df.copy()

mapping_info_row = {"row_index": "MAPPING_METADATA"}
for col in combined_df.columns:
    if col != "row_index":
        mapping_info_row[col] = ""

mapping_info_row.update({
    "mapping_confidence": mapping_result.confidence,
    "validation_passed": str(mapping_result.validation_passed),
    "validation_errors": "; ".join(mapping_result.validation_errors) if mapping_result.validation_errors else "",
    "total_mappings": len(mapping_result.mappings),
    "mappings": str(mapping_result.mappings),
    "unmapped_client_columns": str(mapping_result.unmapped_client_columns),
    "unmapped_canonical_columns": str(mapping_result.unmapped_canonical_columns),
})

combined_df = pd.concat([combined_df, pd.DataFrame([mapping_info_row])], ignore_index=True)
combined_df.to_csv(output_csv_path, index=False)

print(f"Results saved to: {output_csv_path}")
