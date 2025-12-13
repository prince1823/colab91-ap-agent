"""Run benchmark pipeline on input.csv and generate output.csv with all results."""

import json
import time
import yaml
from pathlib import Path

import pandas as pd

from core.classification.services.canonicalization_service import CanonicalizationService
from core.classification.services.verification_service import VerificationService
from core.classification.services.classification_service import ClassificationService
from api.services.dataset_service import DatasetService
from core.database.schema import get_session_factory, init_database
from core.config import get_config


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


def process_single_dataset(dataset_dir: Path, foldername: str = "default"):
    """
    Process a single dataset folder containing input.csv and expected.txt.
    
    Args:
        dataset_dir: Path to dataset folder (e.g., benchmarks/default/fox)
        foldername: Folder name for dataset service (default: "default")
    
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
    
    # Load taxonomy YAML
    with open(taxonomy_yaml, 'r') as f:
        taxonomy_data = yaml.safe_load(f)
    
    # Initialize database and services for new workflow
    config = get_config()
    engine = init_database(config.database_path)
    SessionFactory = get_session_factory(engine)
    session = SessionFactory()
    
    try:
        # Initialize services
        dataset_service = DatasetService()
        
        # Create dataset in dataset service (if not exists)
        try:
            dataset_service.create_dataset(
                dataset_id=dataset_name,
                transactions=input_df.to_dict('records'),
                taxonomy=taxonomy_data,
                foldername=foldername,
                csv_filename="input.csv"  # Use input.csv as the filename
            )
            print(f"Created dataset {dataset_name} in dataset service")
        except ValueError:
            # Dataset already exists, update it
            dataset_service.update_dataset_csv(
                dataset_id=dataset_name,
                transactions=input_df.to_dict('records'),
                foldername=foldername
            )
            print(f"Updated existing dataset {dataset_name} in dataset service")
        
        canonicalization_service = CanonicalizationService(session, dataset_service)
        verification_service = VerificationService(session)
        classification_service = ClassificationService(
            session, dataset_service, taxonomy_path, enable_tracing=True
        )
        
        # Step 1: Canonicalization
        print(f"Step 1: Canonicalizing columns for {dataset_name}...")
        start_time = time.time()
        mapping_result = canonicalization_service.canonicalize_dataset(
            dataset_id=dataset_name,
            foldername=foldername
        )
        canonicalization_time = time.time() - start_time
        print(f"Canonicalization completed in {canonicalization_time:.2f} seconds")
        
        # Step 2: Auto-approve verification (for benchmarks)
        print(f"Step 2: Auto-approving canonicalization...")
        verification_service.approve_canonicalization(
            dataset_id=dataset_name,
            foldername=foldername,
            auto_approve=True
        )
        
        # Step 3: Classification
        print(f"Step 3: Classifying transactions...")
        classification_start = time.time()
        result_df = classification_service.classify_dataset(
            dataset_id=dataset_name,
            foldername=foldername,
            max_workers=4,
            taxonomy_path=taxonomy_path
        )
        classification_time = time.time() - classification_start
        elapsed_time = time.time() - start_time
        print(f"Classification completed in {classification_time:.2f} seconds")
        print(f"Total processing time: {elapsed_time:.2f} seconds ({elapsed_time/60:.2f} minutes)")
        
        # Get mapping result from state for output
        from core.database.models import DatasetProcessingState
        state = session.query(DatasetProcessingState).filter(
            DatasetProcessingState.dataset_id == dataset_name,
            DatasetProcessingState.foldername == foldername
        ).first()
        
        if state and state.canonicalization_result:
            mapping_result_dict = state.canonicalization_result
            # Convert dict back to MappingResult-like object for compatibility
            class MappingResultCompat:
                def __init__(self, mappings, unmapped_columns):
                    self.mappings = mappings
                    self.unmapped_columns = unmapped_columns
            mapping_result = MappingResultCompat(
                mappings=mapping_result_dict.get('mappings', {}),
                unmapped_columns=mapping_result_dict.get('unmapped_columns', [])
            )
        else:
            mapping_result = None
        
        supplier_profiles = {}  # Not exposed in new workflow
        
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
                
                # Extract prioritization decision fields
                should_research = result_row.get('should_research', '') if 'should_research' in result_row else ""
                prioritization_strategy = result_row.get('prioritization_strategy', '') if 'prioritization_strategy' in result_row else ""
                supplier_context_strength = result_row.get('supplier_context_strength', '') if 'supplier_context_strength' in result_row else ""
                transaction_data_quality = result_row.get('transaction_data_quality', '') if 'transaction_data_quality' in result_row else ""
                prioritization_reasoning = result_row.get('prioritization_reasoning', '') if 'prioritization_reasoning' in result_row else ""
                
                row_data.update({
                    'expected_output': expected_output,
                    'pipeline_output': pipeline_output,
                    'columns_used': columns_used,
                    'supplier_profile': supplier_profile_json,
                    'reasoning': reasoning,
                    'error': error_msg,
                    'should_research': should_research,
                    'prioritization_strategy': prioritization_strategy,
                    'supplier_context_strength': supplier_context_strength,
                    'transaction_data_quality': transaction_data_quality,
                    'prioritization_reasoning': prioritization_reasoning,
                })
            else:
                row_data.update({
                'expected_output': expected_output,
                'pipeline_output': "",
                'columns_used': "",
                'supplier_profile': "",
                'reasoning': "",
                'error': "No result returned from pipeline for this row",
                'should_research': "",
                'prioritization_strategy': "",
                'supplier_context_strength': "",
                'transaction_data_quality': "",
                'prioritization_reasoning': "",
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
                'should_research': "",
                'prioritization_strategy': "",
                'supplier_context_strength': "",
                'transaction_data_quality': "",
                'prioritization_reasoning': "",
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
        # Extract foldername from path (e.g., "default/fox" -> "default")
        foldername = benchmark_folder.split('/')[0] if '/' in benchmark_folder else "default"
        results_data, output_csv = process_single_dataset(benchmark_dir, foldername=foldername)
        
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
                results_data, output_csv = process_single_dataset(dataset_dir, foldername=benchmark_folder)
                
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

