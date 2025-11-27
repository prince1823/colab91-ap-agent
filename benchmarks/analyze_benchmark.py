import pandas as pd
from pathlib import Path
from collections import defaultdict
import sys

def parse_taxonomy_path(path_str):
    if pd.isna(path_str) or path_str == '':
        return {'L1': None, 'L2': None, 'L3': None, 'L4': None, 'L5': None}
    levels = str(path_str).split('|')
    return {
        'L1': levels[0] if len(levels) > 0 else None,
        'L2': levels[1] if len(levels) > 1 else None,
        'L3': levels[2] if len(levels) > 2 else None,
        'L4': levels[3] if len(levels) > 3 else None,
        'L5': levels[4] if len(levels) > 4 else None,
    }

def analyze_benchmark(benchmark_name: str):
    datasets = ['fox', 'innova', 'lifepoint', 'sp_global']
    
    level_stats = {'L1': {'correct': 0, 'total': 0}, 'L2': {'correct': 0, 'total': 0},
                   'L3': {'correct': 0, 'total': 0}, 'L4': {'correct': 0, 'total': 0}}
    
    exact_matches = 0
    total_rows = 0
    dataset_results = {}
    failures = []
    
    for dataset in datasets:
        output_path = Path(f"benchmarks/{benchmark_name}/{dataset}/output.csv")
        if not output_path.exists():
            continue
        
        df = pd.read_csv(output_path)
        valid_df = df[(df['error'].isna() | (df['error'] == ''))].reset_index(drop=True)
        
        dataset_correct = 0
        dataset_level_stats = {'L1': {'correct': 0, 'total': 0}, 'L2': {'correct': 0, 'total': 0},
                               'L3': {'correct': 0, 'total': 0}, 'L4': {'correct': 0, 'total': 0}}
        
        for idx, row in valid_df.iterrows():
            expected = row['expected_output']
            actual = row['pipeline_output']
            
            if expected == actual:
                exact_matches += 1
                dataset_correct += 1
            else:
                failures.append({
                    'dataset': dataset,
                    'row': idx + 1,
                    'supplier': str(row.get('Supplier Name', 'N/A'))[:50],
                    'expected': expected,
                    'actual': actual
                })
            
            expected_levels = parse_taxonomy_path(expected)
            actual_levels = parse_taxonomy_path(actual)
            
            for level in ['L1', 'L2', 'L3', 'L4']:
                exp_val = expected_levels[level] or 'None'
                act_val = actual_levels[level] or 'None'
                if exp_val != 'None':
                    level_stats[level]['total'] += 1
                    dataset_level_stats[level]['total'] += 1
                    if exp_val == act_val:
                        level_stats[level]['correct'] += 1
                        dataset_level_stats[level]['correct'] += 1
        
        total_rows += len(valid_df)
        dataset_results[dataset] = {
            'correct': dataset_correct,
            'total': len(valid_df),
            'accuracy': (dataset_correct / len(valid_df) * 100) if len(valid_df) > 0 else 0
        }
    
    print("=" * 100)
    print(f"BENCHMARK ANALYSIS: {benchmark_name}")
    print("=" * 100)
    
    overall_acc = (exact_matches / total_rows * 100) if total_rows > 0 else 0
    print(f"\nExact Match: {exact_matches}/{total_rows} ({overall_acc:.1f}%)")
    
    print(f"\nLevel-wise Accuracy:")
    for level in ['L1', 'L2', 'L3', 'L4']:
        total = level_stats[level]['total']
        if total > 0:
            correct = level_stats[level]['correct']
            acc = (correct / total * 100)
            print(f"  {level}: {correct}/{total} ({acc:.1f}%)")
    
    print(f"\nDataset Breakdown:")
    for dataset, results in sorted(dataset_results.items()):
        print(f"  {dataset.upper():<12} {results['correct']}/{results['total']} ({results['accuracy']:>5.1f}%)")
    
    if failures:
        print(f"\nFailures ({len(failures)}):")
        failure_by_category = defaultdict(int)
        for fail in failures:
            exp_l1 = parse_taxonomy_path(fail['expected']).get('L1', 'Unknown')
            failure_by_category[exp_l1] += 1
        
        print(f"\nBy Expected L1 Category:")
        for category, count in sorted(failure_by_category.items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {count}")
        
        print(f"\nSample Failures:")
        for fail in failures[:5]:
            print(f"  {fail['dataset'].upper()} Row {fail['row']}: {fail['supplier']}")
            print(f"    Expected: {fail['expected']}")
            print(f"    Actual:   {fail['actual']}")

if __name__ == "__main__":
    benchmark_name = sys.argv[1] if len(sys.argv) > 1 else "random_bench_1"
    analyze_benchmark(benchmark_name)

