"""
Batch runner to process large CSV files in chunks without loading the UI.

Usage:
  PYTHONPATH=. poetry run python run_batch_file.py \
    --input /path/to/transaction_data.csv \
    --taxonomy taxonomies/FOX_20230816_161348.yaml \
    --batch-size 500 \
    --output-prefix results/transaction_data_full_iter0
"""

import argparse
from pathlib import Path
import pandas as pd

from core.pipeline import SpendClassificationPipeline


def process_batches(input_path: Path, taxonomy_path: Path, batch_size: int, output_prefix: str):
    pipeline = SpendClassificationPipeline(taxonomy_path=str(taxonomy_path), enable_tracing=True)

    # Stream the CSV in chunks
    reader = pd.read_csv(input_path, chunksize=batch_size)
    output_prefix_path = Path(output_prefix)
    output_prefix_path.parent.mkdir(exist_ok=True, parents=True)

    total_rows = 0
    files_written = []

    for idx, chunk in enumerate(reader):
        print(f"[Batch {idx}] Processing {len(chunk)} rows...")
        result_df = pipeline.process_transactions(chunk)
        part_file = output_prefix_path.parent / f"{output_prefix_path.name}_part{idx}.csv"
        result_df.to_csv(part_file, index=False)
        files_written.append(part_file)
        total_rows += len(result_df)
        print(f"  -> wrote {part_file}")

    print(f"Done. Total rows processed: {total_rows}")
    print("Output files:")
    for f in files_written:
        print(f" - {f}")


def main():
    parser = argparse.ArgumentParser(description="Batch runner for large CSV classification.")
    parser.add_argument("--input", required=True, help="Path to input CSV file")
    parser.add_argument("--taxonomy", required=True, help="Path to taxonomy YAML")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch")
    parser.add_argument("--output-prefix", default="results/batch_output", help="Output prefix (no extension)")
    args = parser.parse_args()

    input_path = Path(args.input)
    taxonomy_path = Path(args.taxonomy)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")
    if not taxonomy_path.exists():
        raise FileNotFoundError(f"Taxonomy file not found: {taxonomy_path}")

    process_batches(input_path, taxonomy_path, args.batch_size, args.output_prefix)


if __name__ == "__main__":
    main()


