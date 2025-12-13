"""Run benchmark pipeline on input.csv and generate output.csv with all results."""

import json
import time
from pathlib import Path

import pandas as pd

from core.pipeline import SpendClassificationPipeline


def format_classification_output(L1, L2=None, L3=None, L4=None, L5=None) -> str:
    """Format classification result as a single string."""
    levels = []
    # Handle None, NaN, and empty strings
    if L1 is not None and pd.notna(L1) and str(L1).strip():
        levels.append(str(L1).strip())
    if L2 is not None and pd.notna(L2) and str(L2).strip():
        levels.append(str(L2).strip())
    if L3 is not None and pd.notna(L3) and str(L3).strip():
        levels.append(str(L3).strip())
    if L4 is not None and pd.notna(L4) and str(L4).strip():
        levels.append(str(L4).strip())
    if L5 is not None and pd.notna(L5) and str(L5).strip():
        levels.append(str(L5).strip())
    
    return "|".join(levels) if levels else ""


def process_single_dataset(dataset_dir: Path):
    """
    Process a single dataset folder containing input.csv and expected.txt.
    
    Args:
        dataset_dir: Path to dataset folder (e.g., benchmarks/default/fox)
    
    Returns:
        tuple: (results_data list, output_csv path)
    """
    dataset_name = dataset_dir.name
    print(f"Started processing {dataset_name}...")
    
    input_csv = dataset_dir / "input.csv"
    expected_txt = dataset_dir / "expected.txt"
    
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    
    input_df = pd.read_csv(input_csv)
    
    expected_list = []
    if expected_txt.exists():
        with open(expected_txt, 'r') as f:
            expected_list = [line.strip() for line in f.readlines() if line.strip()]
    
    if len(expected_list) != len(input_df):
        print(f"Warning: Expected {len(input_df)} expected outputs, found {len(expected_list)}")
        while len(expected_list) < len(input_df):
            expected_list.append("")
    
    # Look for taxonomy.yaml file in dataset folder
    taxonomy_yaml = dataset_dir / "taxonomy.yaml"
    
    if not taxonomy_yaml.exists():
        raise FileNotFoundError(
            f"Taxonomy file not found: {taxonomy_yaml}. "
            f"Please create a taxonomy.yaml file in {dataset_dir}."
        )
    
    taxonomy_path = str(taxonomy_yaml)
    
    # Create pipeline once for the entire dataset (column canonicalization runs once)
    pipeline = SpendClassificationPipeline(
        taxonomy_path=taxonomy_path,
        enable_tracing=True
    )
    
    # Process all rows together - canonicalization happens once, then each row is classified
    try:
        start_time = time.time()
        result_df, intermediate = pipeline.process_transactions(
            input_df,
            taxonomy_path=taxonomy_path,
            return_intermediate=True,
            max_workers=4  # Enable parallel processing for better performance
        )
        elapsed_time = time.time() - start_time
        print(f"Processing time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
        
        mapping_result = intermediate['mapping_result']
        supplier_profiles = intermediate['supplier_profiles']
        
        # Build results for each row
        results_data = []
        for idx, original_row in input_df.iterrows():
            row_data = original_row.to_dict()
            expected_output = expected_list[idx] if idx < len(expected_list) else ""
            
            # Find corresponding result row
            if idx < len(result_df):
                result_row = result_df.iloc[idx]
                
                pipeline_output = format_classification_output(
                    result_row.get('L1'),
                    result_row.get('L2'),
                    result_row.get('L3'),
                    result_row.get('L4'),
                    result_row.get('L5'),
                )
                
                columns_used = json.dumps(mapping_result.mappings) if mapping_result else ""
                
                supplier_name = result_row.get('supplier_name', '')
                supplier_profile_json = ""
                if supplier_name and supplier_name in supplier_profiles:
                    supplier_profile_json = json.dumps(supplier_profiles[supplier_name])
                
                # Check for errors in result
                error_msg = result_row.get('error', '') if 'error' in result_row else ""
                
                # Extract reasoning from result
                reasoning = result_row.get('reasoning', '') if 'reasoning' in result_row else ""
                
                row_data.update({
                    'expected_output': expected_output,
                    'pipeline_output': pipeline_output,
                    'columns_used': columns_used,
                    'supplier_profile': supplier_profile_json,
                    'reasoning': reasoning,
                    'error': error_msg,
                })
            else:
                row_data.update({
                    'expected_output': expected_output,
                    'pipeline_output': "",
                    'columns_used': "",
                    'supplier_profile': "",
                    'reasoning': "",
                    'error': "No result returned from pipeline for this row",
                })
            
            results_data.append(row_data)
    
    except Exception as e:
        # If processing fails, create error entries for all rows
        print(f"Error encountered while processing {dataset_name}: {e}")
        results_data = []
        for idx, original_row in input_df.iterrows():
            row_data = original_row.to_dict()
            expected_output = expected_list[idx] if idx < len(expected_list) else ""
            row_data.update({
                'expected_output': expected_output,
                'pipeline_output': "",
                'columns_used': "",
                'supplier_profile': "",
                'reasoning': "",
                'error': str(e),
            })
            results_data.append(row_data)
    
    output_csv = dataset_dir / "output.csv"
    print(f"Finished processing {dataset_name}")
    return results_data, output_csv


def run_benchmark(benchmark_folder: str = "default"):
    """
    Run pipeline on benchmark input.csv and generate output.csv.
    
    Supports two modes:
    - Mode 1: Process parent folder - processes all subfolders (e.g., "default" processes all datasets)
    - Mode 2: Process specific dataset - processes single folder with input.csv (e.g., "default/fox")
    
    Args:
        benchmark_folder: Subfolder name (e.g., "default", "default/fox", "test_bench")
    """
    benchmark_dir = Path("benchmarks") / benchmark_folder
    
    # Check if this is Mode 2 (has input.csv directly) or Mode 1 (has subfolders)
    input_csv = benchmark_dir / "input.csv"
    
    if input_csv.exists():
        # Mode 2: Process single dataset folder
        print(f"Processing single dataset: benchmarks/{benchmark_folder}")
        results_data, output_csv = process_single_dataset(benchmark_dir)
        
        output_df = pd.DataFrame(results_data)
        output_df.to_csv(output_csv, index=False)
        
        print(f"Benchmark complete!")
        print(f"Processed {len(results_data)} rows")
        print(f"Output saved to: {output_csv}")
        
        successful = sum(1 for r in results_data if not r.get('error', ''))
        print(f"Successful: {successful}/{len(results_data)}")
    
    else:
        # Mode 1: Process all subfolders
        if not benchmark_dir.exists():
            raise FileNotFoundError(f"Benchmark directory not found: {benchmark_dir}")
        
        # Find all subdirectories
        subdirs = [d for d in benchmark_dir.iterdir() if d.is_dir() and (d / "input.csv").exists()]
        
        if not subdirs:
            raise FileNotFoundError(
                f"No dataset folders found in {benchmark_dir}. "
                f"Expected subfolders with input.csv files."
            )
        
        print(f"Processing {len(subdirs)} datasets in benchmarks/{benchmark_folder}")
        
        total_rows = 0
        total_successful = 0
        
        for dataset_dir in sorted(subdirs):
            dataset_name = dataset_dir.name
            print(f"\n--- Processing {dataset_name} ---")
            
            try:
                results_data, output_csv = process_single_dataset(dataset_dir)
                
                output_df = pd.DataFrame(results_data)
                output_df.to_csv(output_csv, index=False)
                
                successful = sum(1 for r in results_data if not r.get('error', ''))
                total_rows += len(results_data)
                total_successful += successful
                
                print(f"  Processed {len(results_data)} rows")
                print(f"  Successful: {successful}/{len(results_data)}")
                print(f"  Output saved to: {output_csv}")
            
            except Exception as e:
                print(f"  Error processing {dataset_name}: {e}")
                total_rows += 0
        
        print(f"\n=== Overall Summary ===")
        print(f"Total datasets processed: {len(subdirs)}")
        print(f"Total rows processed: {total_rows}")
        print(f"Total successful: {total_successful}/{total_rows}")


if __name__ == "__main__":
    import sys
    
    benchmark_folder = sys.argv[1] if len(sys.argv) > 1 else "default"
    
    print(f"Running benchmark for: benchmarks/{benchmark_folder}")
    run_benchmark(benchmark_folder)

