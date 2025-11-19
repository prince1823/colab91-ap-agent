"""Post-processing validation for classification results.

Validates and fixes common issues like level skipping.
"""

from typing import Dict, List, Optional

import yaml


class ClassificationValidator:
    """Validates and fixes classification results"""

    def __init__(self, taxonomy_path: str):
        """Load taxonomy for validation"""
        with open(taxonomy_path, 'r') as f:
            self.taxonomy_data = yaml.safe_load(f)
        self.taxonomy = self.taxonomy_data['taxonomy']
        self.max_depth = self.taxonomy_data.get('max_taxonomy_depth', 5)

    def validate_path_exists(self, path: str, taxonomy: Optional[List[str]] = None) -> bool:
        """Check if path exists in taxonomy"""
        if taxonomy is None:
            taxonomy = self.taxonomy
        return path in taxonomy

    def validate_level_count(self, path: str, max_depth: Optional[int] = None) -> Dict:
        """Validate path depth matches expected"""
        if max_depth is None:
            max_depth = self.max_depth

        levels = [l for l in path.split('|') if l.strip()]
        depth = len(levels)

        if depth > max_depth:
            return {
                'valid': False,
                'error': f"Path has {depth} levels but max depth is {max_depth}",
                'fixed_classification': None
            }

        return {'valid': True}

    def validate_and_fix(
        self,
        L1: str,
        L2: Optional[str],
        L3: Optional[str],
        L4: Optional[str],
        L5: Optional[str]
    ) -> Dict:
        """
        Validate classification and auto-fix if possible

        Returns:
            dict with 'valid', 'fixed' (bool), 'classification', 'errors'
        """
        # Build path from levels
        levels = [L1]
        if L2 and L2.lower() != 'none':
            levels.append(L2)
        if L3 and L3.lower() != 'none':
            levels.append(L3)
        if L4 and L4.lower() != 'none':
            levels.append(L4)
        if L5 and L5.lower() != 'none':
            levels.append(L5)

        path = '|'.join(levels)

        # Check if path exists in taxonomy
        if self.validate_path_exists(path):
            return {
                'valid': True,
                'fixed': False,
                'classification': {'L1': L1, 'L2': L2, 'L3': L3, 'L4': L4, 'L5': L5},
                'errors': []
            }

        # Check depth
        depth_validation = self.validate_level_count(path)
        if not depth_validation['valid']:
            return {
                'valid': False,
                'fixed': False,
                'classification': {'L1': L1, 'L2': L2, 'L3': L3, 'L4': L4, 'L5': L5},
                'errors': [depth_validation['error']]
            }

        # Path doesn't exist - try to find closest match
        # For flat taxonomy, we can't do sophisticated level skipping fixes
        # Just report the error
        return {
            'valid': False,
            'fixed': False,
            'classification': {'L1': L1, 'L2': L2, 'L3': L3, 'L4': L4, 'L5': L5},
            'errors': [f"Path '{path}' not found in taxonomy"]
        }

