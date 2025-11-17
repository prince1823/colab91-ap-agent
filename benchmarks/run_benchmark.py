"""Run benchmark pipeline on input.csv and generate output.csv with all results."""

import json
from pathlib import Path

import pandas as pd

from core.pipeline import SpendClassificationPipeline


def format_classification_output(L1, L2=None, L3=None, L4=None, L5=None) -> str:
    """Format classification result as a single string."""
    levels = []
    if L1 and (isinstance(L1, str) or pd.notna(L1)):
        levels.append(str(L1))
    if L2 and (isinstance(L2, str) or pd.notna(L2)):
        levels.append(str(L2))
    if L3 and (isinstance(L3, str) or pd.notna(L3)):
        levels.append(str(L3))
    if L4 and (isinstance(L4, str) or pd.notna(L4)):
        levels.append(str(L4))
    if L5 and (isinstance(L5, str) or pd.notna(L5)):
        levels.append(str(L5))
    
    return "|".join(levels)


def run_benchmark(benchmark_folder: str = "default"):
    """
    Run pipeline on benchmark input.csv and generate output.csv.
    
    Args:
        benchmark_folder: Subfolder name (e.g., "default", "failed_rows")
    """
    benchmark_dir = Path("benchmarks") / benchmark_folder
    
    input_csv = benchmark_dir / "input.csv"
    expected_txt = benchmark_dir / "expected.txt"
    
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
    
    results_data = []
    
    for idx, row in input_df.iterrows():
        row_data = row.to_dict()
        expected_output = expected_list[idx] if idx < len(expected_list) else ""
        
        taxonomy_path = row.get('taxonomy_path', '')
        if not taxonomy_path or pd.isna(taxonomy_path):
            taxonomy_path = "taxonomies/FOX_20230816_161348.yaml"
        
        taxonomy_path = str(taxonomy_path)
        
        if not Path(taxonomy_path).exists():
            print(f"Warning: Taxonomy file not found: {taxonomy_path}, skipping row {idx}")
            row_data.update({
                'expected_output': expected_output,
                'pipeline_output': "",
                'columns_used': "",
                'supplier_profile': "",
                'error': f"Taxonomy file not found: {taxonomy_path}",
            })
            results_data.append(row_data)
            continue
        
        try:
            pipeline = SpendClassificationPipeline(
                taxonomy_path=taxonomy_path,
                enable_tracing=False
            )
            
            transaction_df = pd.DataFrame([row])
            result_df, intermediate = pipeline.process_transactions(
                transaction_df,
                taxonomy_path=taxonomy_path,
                return_intermediate=True
            )
            
            mapping_result = intermediate['mapping_result']
            supplier_profiles = intermediate['supplier_profiles']
            
            if len(result_df) > 0:
                result_row = result_df.iloc[0]
                
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
                
                row_data.update({
                    'expected_output': expected_output,
                    'pipeline_output': pipeline_output,
                    'columns_used': columns_used,
                    'supplier_profile': supplier_profile_json,
                    'error': "",
                })
            else:
                row_data.update({
                    'expected_output': expected_output,
                    'pipeline_output': "",
                    'columns_used': "",
                    'supplier_profile': "",
                    'error': "No results returned from pipeline",
                })
        
        except Exception as e:
            row_data.update({
                'expected_output': expected_output,
                'pipeline_output': "",
                'columns_used': "",
                'supplier_profile': "",
                'error': str(e),
            })
        
        results_data.append(row_data)
    
    output_df = pd.DataFrame(results_data)
    output_csv = benchmark_dir / "output.csv"
    output_df.to_csv(output_csv, index=False)
    
    print(f"Benchmark complete!")
    print(f"Processed {len(results_data)} rows")
    print(f"Output saved to: {output_csv}")
    
    successful = sum(1 for r in results_data if not r.get('error', ''))
    print(f"Successful: {successful}/{len(results_data)}")


if __name__ == "__main__":
    import sys
    
    benchmark_folder = sys.argv[1] if len(sys.argv) > 1 else "default"
    
    print(f"Running benchmark for: benchmarks/{benchmark_folder}")
    run_benchmark(benchmark_folder)

