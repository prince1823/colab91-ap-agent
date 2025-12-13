"""Utilities for converting transaction taxonomy data into YAML files."""

import re
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
import yaml

# Mapping of cube identifiers to their taxonomy column names
TRANSACTION_LEVEL_COLUMNS: Dict[str, Sequence[str]] = {
    "fox": ["Level 1 ", "Level 2", "Level 3"],
    "innova": ["Level 1", "Level 2", "Level 3", "Level 4"],
    "lifepoint": ["Category Level 1", "Category Level 2", "Category Level 3", "Category Level 4"],
    "sp_global": ["Spend Category - Refined L1", "Spend Category - Refined L2", "Spend Category - Refined L3"],
}

# Configuration for each cube dataset
CUBE_CONFIG: Sequence[Dict[str, str]] = [
    {
        "cube": "fox",
        "folder": "FOX_20230816_161348",
        "client_name": "FOX Corporation",
        "project_id": "FOX_20230816_161348"
    },
    {
        "cube": "innova",
        "folder": "Innova_Care_Health_Jun_23",
        "client_name": "Innova Care Health",
        "project_id": "Innova_Care_Health_Jun_23"
    },
    {
        "cube": "lifepoint",
        "folder": "LifePoint_20231128_210029",
        "client_name": "LifePoint Healthcare",
        "project_id": "LifePoint_20231128_210029"
    },
    {
        "cube": "sp_global",
        "folder": "S&P_Global_20231215_153855",
        "client_name": "S&P Global",
        "project_id": "S&P_Global_20231215_153855"
    },
]

# Regex patterns for cleaning
TIMESTAMP_13 = re.compile(r"\d{13}$")
TIMESTAMP_10 = re.compile(r"\d{10}$")
MULTI_PIPE = re.compile(r"\|+")


def clean_segment(value: Optional[str]) -> Optional[str]:
    """Strip whitespace, remove trailing timestamps, and normalise strings."""
    if value is None:
        return None
    
    text = str(value).strip()
    if not text:
        return None
    
    lowered = text.lower()
    if lowered in {"nan", "none", ""}:
        return None
    
    # Remove trailing timestamps
    text = TIMESTAMP_13.sub("", text)
    text = TIMESTAMP_10.sub("", text)
    text = text.strip()
    
    return text or None


def normalise_path_text(text: str) -> str:
    """Collapse repeated pipes and strip surrounding whitespace."""
    collapsed = MULTI_PIPE.sub("|", text)
    return collapsed.strip("| ")


def parse_delimited_path(raw_text: str, target_depth: Optional[int] = None) -> Optional[Tuple[str, ...]]:
    """Parse a pipe-delimited string into a tuple of cleaned taxonomy segments."""
    cleaned_text = clean_segment(raw_text)
    if not cleaned_text:
        return None
    
    cleaned_text = normalise_path_text(cleaned_text)
    parts = [clean_segment(part) for part in cleaned_text.split("|")]
    segments = [part for part in parts if part]
    
    if not segments:
        return None
    
    if target_depth:
        segments = segments[:target_depth]
        if len(segments) != target_depth:
            return None
    
    return tuple(segments)


def parse_path_from_row(
    values: Dict[str, str],
    columns: Sequence[str],
    target_depth: Optional[int] = None
) -> Optional[Tuple[str, ...]]:
    """Extract a taxonomy path from a single transaction row."""
    if not columns:
        return None
    
    # Try the deepest column first (most specific)
    deepest_column = columns[-1]
    current = values.get(deepest_column)
    
    if not current:
        return None
    
    parsed = parse_delimited_path(str(current), target_depth)
    if parsed:
        return parsed
    
    # Attempt again after cleaning possible timestamp suffixes
    cleaned = clean_segment(current)
    if not cleaned:
        return None
    
    return parse_delimited_path(cleaned, target_depth)


def iter_transaction_rows(
    transaction_csv: Path,
    columns: Sequence[str]
) -> Iterable[Dict[str, str]]:
    """Yield dictionaries mapping column names to values for each transaction row."""
    if not transaction_csv.exists():
        return
    
    read_options = dict(usecols=columns, dtype=str, keep_default_na=False)
    
    try:
        for chunk in pd.read_csv(transaction_csv, chunksize=200_000, **read_options):
            for row in chunk.to_dict(orient="records"):
                yield row
    except Exception as e:
        print(f"  Warning: Error reading {transaction_csv}: {e}")
        return


def collect_paths_from_transactions(
    transaction_csv: Path,
    columns: Sequence[str],
    target_depth: Optional[int] = None,
) -> Tuple[List[str], int]:
    """Collect unique taxonomy paths from transaction data."""
    if not transaction_csv.exists():
        raise FileNotFoundError(f"Missing transaction file: {transaction_csv}")
    
    unique_paths: set[str] = set()
    observed_depth = 0
    
    for row in iter_transaction_rows(transaction_csv, columns):
        path = parse_path_from_row(row, columns, target_depth)
        if not path:
            continue
        
        observed_depth = max(observed_depth, len(path))
        unique_paths.add("|".join(path))
    
    return sorted(unique_paths), observed_depth


def discover_taxonomy_columns(transaction_csv: Path) -> Optional[List[str]]:
    """
    Auto-discover taxonomy columns by looking for common patterns.
    
    Returns list of column names ordered by level (L1, L2, L3, etc.)
    """
    if not transaction_csv.exists():
        return None
    
    try:
        # Read just the header
        df_header = pd.read_csv(transaction_csv, nrows=0)
        all_columns = df_header.columns.tolist()
    except Exception:
        return None
    
    # Common patterns for taxonomy columns
    patterns = [
        (r"level\s*1", "Level 1"),
        (r"level\s*2", "Level 2"),
        (r"level\s*3", "Level 3"),
        (r"level\s*4", "Level 4"),
        (r"level\s*5", "Level 5"),
        (r"category\s*level\s*1", "Category Level 1"),
        (r"category\s*level\s*2", "Category Level 2"),
        (r"category\s*level\s*3", "Category Level 3"),
        (r"category\s*level\s*4", "Category Level 4"),
        (r"spend\s*category.*l1", "Spend Category L1"),
        (r"spend\s*category.*l2", "Spend Category L2"),
        (r"spend\s*category.*l3", "Spend Category L3"),
        (r"l1\s*category", "L1 Category"),
        (r"l2\s*category", "L2 Category"),
        (r"l3\s*category", "L3 Category"),
    ]
    
    found_columns = []
    for pattern, label in patterns:
        regex = re.compile(pattern, re.IGNORECASE)
        matches = [col for col in all_columns if regex.search(col)]
        if matches:
            # Take the first match, or prefer exact match
            exact_match = [col for col in matches if col.lower() == label.lower()]
            found_columns.append(exact_match[0] if exact_match else matches[0])
    
    # Remove duplicates while preserving order
    seen = set()
    unique_columns = []
    for col in found_columns:
        if col not in seen:
            seen.add(col)
            unique_columns.append(col)
    
    return unique_columns if unique_columns else None


def convert_cube_taxonomy(
    transaction_csv: Path,
    output_path: Path,
    client_name: str,
    project_id: str,
    columns: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    """Convert a single cube's taxonomy into YAML."""
    if not transaction_csv.exists():
        raise FileNotFoundError(f"Transaction file not found: {transaction_csv}")
    
    # Auto-discover columns if not provided
    if columns is None:
        columns = discover_taxonomy_columns(transaction_csv)
        if not columns:
            raise ValueError(f"Could not discover taxonomy columns in {transaction_csv}")
        print(f"  Auto-discovered taxonomy columns: {columns}")
    
    # Collect unique paths
    paths, observed_depth = collect_paths_from_transactions(transaction_csv, columns)
    
    if not paths:
        raise ValueError(f"No taxonomy paths found for {project_id}")
    
    max_depth = observed_depth or len(columns)
    
    # Filter to full-depth paths only
    full_depth_paths = [path for path in paths if path.count("|") + 1 == max_depth]
    
    # If no full-depth paths, use all paths
    if not full_depth_paths:
        full_depth_paths = paths
        max_depth = max(len(path.split("|")) for path in paths) if paths else max_depth
    
    yaml_payload = {
        "client_name": client_name,
        "project_id": project_id,
        "max_taxonomy_depth": max_depth,
        "available_levels": [f"L{i}" for i in range(1, max_depth + 1)],
        "taxonomy": full_depth_paths,
        "override_rules": [],
        "note": "Each taxonomy path is pipe-separated (L1|L2|L3|...). Select the most specific path you're confident about.",
    }
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as handle:
        yaml.dump(yaml_payload, handle, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"  Generated {len(full_depth_paths)} taxonomy paths for {project_id} (depth L{max_depth})")
    
    return yaml_payload


def convert_all_taxonomies(extraction_outputs_dir: Path = None, output_dir: Path = None) -> Dict[str, Dict[str, object]]:
    """
    Convert every configured cube's taxonomy.
    
    Args:
        extraction_outputs_dir: Path to extraction_outputs directory (default: ./extraction_outputs)
        output_dir: Path to output taxonomies directory (default: ./taxonomies)
    
    Returns:
        Dictionary mapping project_id to YAML payload
    """
    if extraction_outputs_dir is None:
        extraction_outputs_dir = Path(__file__).parent.parent.parent / "extraction_outputs"
    if output_dir is None:
        output_dir = Path(__file__).parent.parent.parent / "taxonomies"
    
    output_dir.mkdir(exist_ok=True)
    
    results = {}
    
    for config in CUBE_CONFIG:
        cube = config["cube"]
        folder_name = config["folder"]
        client_name = config["client_name"]
        project_id = config["project_id"]
        
        transaction_csv = extraction_outputs_dir / folder_name / "transaction_data.csv"
        
        if not transaction_csv.exists():
            print(f"✗ Skipping {client_name} - missing transaction_data.csv")
            continue
        
        # Get columns from mapping or auto-discover
        columns = TRANSACTION_LEVEL_COLUMNS.get(cube)
        if not columns:
            print(f"⚠ {client_name} ({cube}) - columns not configured, attempting auto-discovery...")
            columns = None  # Will trigger auto-discovery
        
        output_yaml = output_dir / f"{project_id}.yaml"
        
        print(f"▶ Converting {client_name} ({cube})")
        
        try:
            payload = convert_cube_taxonomy(
                transaction_csv=transaction_csv,
                output_path=output_yaml,
                client_name=client_name,
                project_id=project_id,
                columns=columns,
            )
            results[project_id] = payload
            print(f"✓ Created {output_yaml.name} with max depth L{payload['max_taxonomy_depth']}\n")
        except Exception as e:
            print(f"✗ Error converting {client_name}: {e}\n")
    
    return results


if __name__ == "__main__":
    """Run taxonomy conversion for all cubes."""
    convert_all_taxonomies()

