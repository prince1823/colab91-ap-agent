"""Helper functions for parsing and formatting classification paths."""

from typing import Dict, List, Optional


def parse_classification_path(path: str) -> Dict[str, Optional[str]]:
    """
    Parse a pipe-separated classification path into individual levels.
    
    Args:
        path: Classification path (e.g., "L1|L2|L3|L4|L5")
        
    Returns:
        Dictionary with L1, L2, L3, L4, L5 keys
    """
    if not path:
        return {'L1': None, 'L2': None, 'L3': None, 'L4': None, 'L5': None}
    
    parts = path.split('|')
    return {
        'L1': parts[0].strip() if len(parts) > 0 and parts[0].strip() else None,
        'L2': parts[1].strip() if len(parts) > 1 and parts[1].strip() else None,
        'L3': parts[2].strip() if len(parts) > 2 and parts[2].strip() else None,
        'L4': parts[3].strip() if len(parts) > 3 and parts[3].strip() else None,
        'L5': parts[4].strip() if len(parts) > 4 and parts[4].strip() else None,
    }


def parse_path_to_updates(path: str, override_rule: Optional[str] = None) -> Dict[str, str]:
    """
    Parse classification path into update dictionary for CSV rows.
    
    Args:
        path: Classification path (e.g., "L1|L2|L3|L4")
        override_rule: Optional override rule identifier
        
    Returns:
        Dictionary with L1, L2, L3, L4, and optionally override_rule_applied
    """
    parts = path.split('|')
    updates = {
        'L1': parts[0] if len(parts) > 0 else '',
        'L2': parts[1] if len(parts) > 1 else '',
        'L3': parts[2] if len(parts) > 2 else '',
        'L4': parts[3] if len(parts) > 3 else '',
    }
    
    if override_rule:
        updates['override_rule_applied'] = override_rule
    
    return updates


def format_classification_path(L1: str, L2: Optional[str] = None, L3: Optional[str] = None,
                               L4: Optional[str] = None, L5: Optional[str] = None) -> str:
    """
    Format classification levels into pipe-separated path.
    
    Args:
        L1: Level 1 category (required)
        L2-L5: Optional lower levels
        
    Returns:
        Pipe-separated classification path
    """
    levels = [L1]
    for level in [L2, L3, L4, L5]:
        if level:
            levels.append(level)
    return '|'.join(levels)

