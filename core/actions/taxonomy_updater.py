"""Taxonomy updater for Action 1."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional

from core.agents.feedback_analysis.model import FeedbackAction


class TaxonomyUpdater:
    """Updates taxonomy YAML files."""
    
    def __init__(self, taxonomy_path: Optional[Path] = None):
        """
        Initialize taxonomy updater.
        
        Args:
            taxonomy_path: Path to taxonomy YAML file
        """
        self.taxonomy_path = taxonomy_path
    
    def update_taxonomy(
        self,
        action: FeedbackAction,
        edited_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update taxonomy based on feedback action.
        
        Args:
            action: Feedback action with taxonomy update details
            edited_text: User-edited text (if user made changes)
        
        Returns:
            Dictionary with update results
        """
        if not self.taxonomy_path or not self.taxonomy_path.exists():
            return {
                "status": "error",
                "message": f"Taxonomy file not found: {self.taxonomy_path}",
            }
        
        # Load current taxonomy
        with open(self.taxonomy_path, 'r') as f:
            taxonomy_data = yaml.safe_load(f)
        
        metadata = action.metadata
        category_path = metadata.get("category_path", "")
        
        # Parse category path
        levels = category_path.split("|") if category_path else []
        
        # For now, just add/update the taxonomy entry
        # In full implementation, would update descriptions or structure
        
        taxonomy_list = taxonomy_data.get("taxonomy", [])
        if category_path not in taxonomy_list:
            taxonomy_list.append(category_path)
            taxonomy_data["taxonomy"] = taxonomy_list
        
        # Save updated taxonomy
        with open(self.taxonomy_path, 'w') as f:
            yaml.dump(taxonomy_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        return {
            "status": "success",
            "message": f"Taxonomy updated: {category_path}",
            "category_path": category_path,
        }
