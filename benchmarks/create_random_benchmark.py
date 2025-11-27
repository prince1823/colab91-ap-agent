import argparse
import random
import shutil
from pathlib import Path
from typing import List

import pandas as pd


def sample_rows_from_dataset(
    source_dir: Path, 
    target_dir: Path, 
    num_samples: int = 10,
    random_seed: int = None
) -> List[int]:
    if random_seed is not None:
        random.seed(random_seed)
    
    # Read input CSV
    input_csv = source_dir / "input.csv"
    expected_txt = source_dir / "expected.txt"
    taxonomy_yaml = source_dir / "taxonomy.yaml"
    
    if not input_csv.exists():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    if not expected_txt.exists():
        raise FileNotFoundError(f"Expected file not found: {expected_txt}")
    if not taxonomy_yaml.exists():
        raise FileNotFoundError(f"Taxonomy YAML not found: {taxonomy_yaml}")
    
    # Read data
    df = pd.read_csv(input_csv)
    with open(expected_txt, 'r') as f:
        expected_lines = [line.strip() for line in f.readlines() if line.strip()]
    
    # Determine number of samples (don't exceed available rows)
    total_rows = len(df)
    num_samples = min(num_samples, total_rows)
    
    if num_samples == 0:
        return []
    
    # Sample random row indices
    available_indices = list(range(total_rows))
    selected_indices = sorted(random.sample(available_indices, num_samples))
    
    # Create target directory
    target_dir.mkdir(parents=True, exist_ok=True)
    
    # Sample rows from dataframe
    sampled_df = df.iloc[selected_indices].reset_index(drop=True)
    
    # Sample corresponding expected outputs
    sampled_expected = [expected_lines[idx] for idx in selected_indices]
    
    # Write sampled input CSV
    sampled_df.to_csv(target_dir / "input.csv", index=False)
    
    # Write sampled expected.txt
    with open(target_dir / "expected.txt", 'w') as f:
        for expected_line in sampled_expected:
            f.write(expected_line + '\n')
    
    # Copy taxonomy.yaml
    shutil.copy2(taxonomy_yaml, target_dir / "taxonomy.yaml")
    
    # Save selected row indices for reference
    with open(target_dir / "rows_chosen.txt", 'w') as f:
        f.write(f"Selected {num_samples} rows from {source_dir.name}\n")
        f.write(f"Original row indices: {selected_indices}\n")
        f.write(f"Random seed used: {random_seed}\n")
    
    return selected_indices


def create_random_benchmark(
    benchmark_name: str,
    source_folder: str = "default",
    samples_per_dataset: int = 10,
    random_seed: int = None
):
    benchmarks_dir = Path(__file__).parent
    source_dir = benchmarks_dir / source_folder
    target_dir = benchmarks_dir / benchmark_name
    
    if not source_dir.exists():
        raise FileNotFoundError(f"Source folder not found: {source_dir}")
    
    if target_dir.exists():
        response = input(f"Target '{benchmark_name}' exists. Overwrite? (yes/no): ")
        if response.lower() != 'yes':
            return
        shutil.rmtree(target_dir)
    
    # Get all dataset folders
    dataset_folders = [d for d in source_dir.iterdir() if d.is_dir() and not d.name.startswith('.')]
    
    if not dataset_folders:
        raise ValueError(f"No dataset folders found in {source_dir}")
    
    total_samples = 0
    successful_datasets = 0
    
    for dataset_folder in sorted(dataset_folders):
        dataset_name = dataset_folder.name
        target_dataset_dir = target_dir / dataset_name
        
        try:
            selected_indices = sample_rows_from_dataset(
                dataset_folder,
                target_dataset_dir,
                num_samples=samples_per_dataset,
                random_seed=random_seed
            )
            if selected_indices:
                total_samples += len(selected_indices)
                successful_datasets += 1
        except Exception as e:
            print(f"Error processing {dataset_name}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Create a new benchmark dataset by randomly sampling from default folders"
    )
    parser.add_argument(
        "benchmark_name",
        type=str,
        help="Name of the new benchmark dataset (e.g., 'random_bench_1')"
    )
    parser.add_argument(
        "--samples-per-dataset",
        type=int,
        default=10,
        help="Number of random samples to select from each dataset (default: 10)"
    )
    parser.add_argument(
        "--source-folder",
        type=str,
        default="default",
        help="Source folder to sample from (default: 'default')"
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=None,
        help="Random seed for reproducibility (optional)"
    )
    parser.add_argument(
        "--run-benchmark",
        action="store_true",
        help="Run the benchmark after creating it"
    )
    
    args = parser.parse_args()
    
    # Create the benchmark
    create_random_benchmark(
        benchmark_name=args.benchmark_name,
        source_folder=args.source_folder,
        samples_per_dataset=args.samples_per_dataset,
        random_seed=args.random_seed
    )
    
    if args.run_benchmark:
        from benchmarks.run_benchmark import run_benchmark
        run_benchmark(args.benchmark_name)


if __name__ == "__main__":
    main()

