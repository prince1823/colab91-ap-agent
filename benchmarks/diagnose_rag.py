"""Diagnostic script to examine RAG retrieval and reranking results.

This script analyzes:
1. What paths does RAG retrieve for each transaction?
2. Is the expected path in the retrieved set?
3. What are the similarity scores?
4. How does reranking affect the ordering?
"""

import argparse
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import yaml

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.agents.taxonomy_rag import TaxonomyRetriever
from core.agents.column_canonicalization import ColumnCanonicalizationAgent
from core.utils.transaction_utils import is_valid_value


def load_taxonomy(taxonomy_path: Path) -> List[str]:
    """Load taxonomy paths from YAML file."""
    with open(taxonomy_path, 'r') as f:
        data = yaml.safe_load(f)
    return data.get('taxonomy', [])


def analyze_rag_retrieval(
    transaction_data: Dict,
    supplier_profile: Dict,
    taxonomy_list: List[str],
    expected_path: str,
    retriever: TaxonomyRetriever
) -> Dict:
    """Analyze RAG retrieval for a single transaction."""
    
    try:
        # Get initial retrieval (before reranking)
        initial_results = retriever.retrieve_with_scores(
            transaction_data=transaction_data,
            supplier_profile=supplier_profile,
            taxonomy_list=taxonomy_list,
            top_k=50,
            use_reranking=False  # Get results BEFORE reranking
        )
    except Exception as e:
        print(f"      ⚠️  Error in initial retrieval: {e}")
        initial_results = []
    
    try:
        # Get reranked results
        reranked_results = retriever.retrieve_with_scores(
            transaction_data=transaction_data,
            supplier_profile=supplier_profile,
            taxonomy_list=taxonomy_list,
            top_k=50,
            use_reranking=True  # Get results AFTER reranking
        )
    except Exception as e:
        print(f"      ⚠️  Error in reranked retrieval: {e}")
        reranked_results = []
    
    # Check if expected path is in retrieved results
    initial_paths = [r.path for r in initial_results]
    reranked_paths = [r.path for r in reranked_results]
    
    expected_in_initial = expected_path in initial_paths
    expected_in_reranked = expected_path in reranked_paths
    
    # Find expected path position and score
    expected_initial_pos = initial_paths.index(expected_path) if expected_in_initial else None
    expected_reranked_pos = reranked_paths.index(expected_path) if expected_in_reranked else None
    
    expected_initial_score = initial_results[expected_initial_pos].combined_score if expected_in_initial else None
    expected_reranked_score = reranked_results[expected_reranked_pos].combined_score if expected_in_reranked else None
    
    # Get top 10 for analysis
    top_10_initial = [(r.path, r.combined_score, r.metadata) for r in initial_results[:10]]
    top_10_reranked = [(r.path, r.combined_score, r.metadata) for r in reranked_results[:10]]
    
    return {
        'expected_path': expected_path,
        'expected_in_initial': expected_in_initial,
        'expected_in_reranked': expected_in_reranked,
        'expected_initial_position': expected_initial_pos,
        'expected_reranked_position': expected_reranked_pos,
        'expected_initial_score': expected_initial_score,
        'expected_reranked_score': expected_reranked_score,
        'top_10_initial': top_10_initial,
        'top_10_reranked': top_10_reranked,
        'total_retrieved': len(initial_results)
    }


def format_supplier_profile(row: pd.Series) -> Dict:
    """Create supplier profile dict from row data."""
    profile = {}
    
    # Map column names - try to find supplier_name
    supplier_name = None
    for col in row.index:
        col_lower = col.lower()
        if 'supplier' in col_lower and 'name' in col_lower:
            if is_valid_value(row[col]):
                supplier_name = str(row[col])
                break
    
    if supplier_name:
        profile['supplier_name'] = supplier_name
    
    # Try to find other supplier-related fields
    for col in row.index:
        col_lower = col.lower()
        if 'supplier' in col_lower and 'name' not in col_lower:
            if is_valid_value(row[col]):
                profile['description'] = str(row[col])
    
    return profile


def diagnose_benchmark(benchmark_name: str, dataset: Optional[str] = None, max_rows: int = 10):
    """Diagnose RAG retrieval for a benchmark dataset."""
    
    benchmarks_dir = Path(__file__).parent
    benchmark_dir = benchmarks_dir / benchmark_name
    
    if not benchmark_dir.exists():
        print(f"Error: Benchmark '{benchmark_name}' not found")
        return
    
    # Get datasets to process
    if dataset:
        datasets = [dataset]
    else:
        datasets = [d.name for d in benchmark_dir.iterdir() 
                   if d.is_dir() and not d.name.startswith('.')]
    
    retriever = TaxonomyRetriever()
    canonicalization_agent = ColumnCanonicalizationAgent(enable_tracing=False)
    
    for dataset_name in sorted(datasets):
        dataset_dir = benchmark_dir / dataset_name
        
        input_csv = dataset_dir / "input.csv"
        output_csv = dataset_dir / "output.csv"
        expected_txt = dataset_dir / "expected.txt"
        taxonomy_yaml = dataset_dir / "taxonomy.yaml"
        
        if not all([f.exists() for f in [input_csv, output_csv, expected_txt, taxonomy_yaml]]):
            print(f"Skipping {dataset_name}: missing files")
            continue
        
        print("=" * 120)
        print(f"DIAGNOSING: {benchmark_name}/{dataset_name}")
        print("=" * 120)
        
        # Load data
        df_input = pd.read_csv(input_csv)
        df_output = pd.read_csv(output_csv)
        taxonomy_list = load_taxonomy(taxonomy_yaml)
        
        # Canonicalize the input data (required for RAG retriever)
        try:
            client_schema = canonicalization_agent.extract_schema_from_dataframe(df_input, sample_rows=3)
            mapping_result = canonicalization_agent.map_columns(client_schema)
            if not mapping_result.validation_passed:
                print(f"⚠️  Warning: Canonicalization validation failed: {mapping_result.validation_errors}")
                continue
            df_canonical = canonicalization_agent.apply_mapping(df_input, mapping_result)
            print(f"✅ Canonicalized {len(df_canonical)} rows with {len(df_canonical.columns)} columns")
        except Exception as e:
            print(f"❌ Error in canonicalization: {e}")
            import traceback
            traceback.print_exc()
            continue
        
        with open(expected_txt, 'r') as f:
            expected_lines = [line.strip() for line in f.readlines() if line.strip()]
        
        print(f"\n📊 Dataset: {dataset_name}")
        print(f"   Total transactions: {len(df_input)}")
        print(f"   Analyzing first {min(max_rows, len(df_input))} transactions\n")
        
        # Analyze each transaction
        correct_retrieval = 0
        correct_after_rerank = 0
        
        for idx in range(min(max_rows, len(df_input))):
            # Use canonicalized row for transaction data
            row_canonical = df_canonical.iloc[idx]
            row_original = df_input.iloc[idx]  # For display purposes
            
            expected_path = expected_lines[idx] if idx < len(expected_lines) else ""
            actual_path = df_output.iloc[idx].get('pipeline_output', '') if idx < len(df_output) else ""
            
            # Convert canonicalized row to transaction dict
            transaction_data = row_canonical.to_dict()
            
            # Create supplier profile from canonicalized data
            supplier_profile = format_supplier_profile(row_canonical)
            
            # Get supplier name for display
            supplier_name = str(row_original.get('Supplier Name', 'N/A'))[:50]
            
            # Debug: Check if we have taxonomy paths
            if not taxonomy_list:
                print(f"   ⚠️  WARNING: No taxonomy paths loaded!")
                continue
            
            # Analyze RAG retrieval
            try:
                analysis = analyze_rag_retrieval(
                    transaction_data=transaction_data,
                    supplier_profile=supplier_profile,
                    taxonomy_list=taxonomy_list,
                    expected_path=expected_path,
                    retriever=retriever
                )
            except Exception as e:
                print(f"   ⚠️  ERROR in RAG analysis: {e}")
                import traceback
                traceback.print_exc()
                continue
            
            # Track statistics
            if analysis['expected_in_initial']:
                correct_retrieval += 1
            if analysis['expected_in_reranked']:
                correct_after_rerank += 1
            
            # Print analysis
            status = "✅" if expected_path == actual_path else "❌"
            
            print(f"\n{status} Row {idx + 1}: {supplier_name}")
            print(f"   Expected: {expected_path}")
            print(f"   Actual:   {actual_path}")
            
            if analysis['expected_in_initial']:
                print(f"   ✅ Expected path FOUND in initial retrieval (position {analysis['expected_initial_position'] + 1}, score: {analysis['expected_initial_score']:.3f})")
            else:
                print(f"   ❌ Expected path NOT FOUND in initial retrieval")
            
            if analysis['expected_in_reranked']:
                pos_change = ""
                if analysis['expected_initial_position'] is not None:
                    change = analysis['expected_reranked_position'] - analysis['expected_initial_position']
                    pos_change = f" (moved {change:+d} positions)"
                print(f"   ✅ Expected path FOUND after reranking (position {analysis['expected_reranked_position'] + 1}, score: {analysis['expected_reranked_score']:.3f}{pos_change})")
            else:
                print(f"   ❌ Expected path NOT FOUND after reranking")
            
            # Show top 5 retrieved paths
            if analysis['top_10_initial']:
                print(f"\n   Top 5 Initial Retrieval:")
                for i, (path, score, metadata) in enumerate(analysis['top_10_initial'][:5], 1):
                    marker = "🎯" if path == expected_path else "  "
                    kw_score = metadata.get('keyword_score', 0)
                    sem_score = metadata.get('semantic_score', 0)
                    print(f"      {marker} {i}. [{score:.3f}] {path}")
                    print(f"         (keyword: {kw_score:.3f}, semantic: {sem_score:.3f})")
            else:
                print(f"\n   ⚠️  No paths retrieved in initial search!")
                print(f"      Total taxonomy paths available: {len(taxonomy_list)}")
            
            if analysis['top_10_reranked']:
                if analysis['top_10_reranked'] != analysis['top_10_initial']:
                    print(f"\n   Top 5 After Reranking:")
                    for i, (path, score, metadata) in enumerate(analysis['top_10_reranked'][:5], 1):
                        marker = "🎯" if path == expected_path else "  "
                        rerank_score = metadata.get('rerank_score', 0)
                        print(f"      {marker} {i}. [{score:.3f}] {path}")
                        if rerank_score > 0:
                            print(f"         (rerank: {rerank_score:.3f})")
        
        # Summary
        print(f"\n📈 Summary for {dataset_name}:")
        print(f"   Expected path in initial retrieval: {correct_retrieval}/{max_rows} ({correct_retrieval/max_rows*100:.1f}%)")
        print(f"   Expected path after reranking: {correct_after_rerank}/{max_rows} ({correct_after_rerank/max_rows*100:.1f}%)")
        
        print("\n" + "=" * 120 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose RAG retrieval and reranking results"
    )
    parser.add_argument(
        "benchmark_name",
        type=str,
        help="Name of the benchmark to diagnose (e.g., 'test_bench_v3')"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        default=None,
        help="Specific dataset to diagnose (optional, defaults to all)"
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=10,
        help="Maximum number of rows to analyze per dataset (default: 10)"
    )
    
    args = parser.parse_args()
    
    diagnose_benchmark(
        benchmark_name=args.benchmark_name,
        dataset=args.dataset,
        max_rows=args.max_rows
    )


if __name__ == "__main__":
    main()
