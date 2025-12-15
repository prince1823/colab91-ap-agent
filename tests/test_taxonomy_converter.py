"""Test script for taxonomy converter utility."""

from pathlib import Path

from core.utils.taxonomy.taxonomy_converter import convert_all_taxonomies

if __name__ == "__main__":
    extraction_outputs_dir = Path("extraction_outputs")
    taxonomies_dir = Path("taxonomies")
    
    results = convert_all_taxonomies(extraction_outputs_dir=extraction_outputs_dir, output_dir=taxonomies_dir)
    
    print(f"\nConverted {len(results)} taxonomies")
    if results:
        for project_id in results:
            payload = results[project_id]
            print(f"  {project_id}.yaml: L{payload['max_taxonomy_depth']}, {len(payload['taxonomy'])} paths")

