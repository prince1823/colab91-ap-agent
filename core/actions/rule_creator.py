"""Rule creator for Action 4."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional
import re

from core.agents.feedback_analysis.model import FeedbackAction


class RuleCreator:
    """Creates new classification rules."""
    
    def __init__(self, taxonomy_path: Optional[Path] = None):
        """
        Initialize rule creator.
        
        Args:
            taxonomy_path: Path to taxonomy YAML file
        """
        self.taxonomy_path = taxonomy_path
    
    def create_rule(
        self,
        action: FeedbackAction,
        edited_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create new classification rule.
        
        Args:
            action: Feedback action with rule creation details
            edited_text: User-edited text (if user made changes)
        
        Returns:
            Dictionary with rule creation results
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
        
        # Extract rule condition and classification
        gl_code = metadata.get("gl_code", "")
        corrected_path = "|".join([
            v for v in [
                metadata.get("corrected_l1"),
                metadata.get("corrected_l2"),
                metadata.get("corrected_l3"),
                metadata.get("corrected_l4"),
                metadata.get("corrected_l5"),
            ] if v
        ])
        
        # Generate rule text
        if gl_code:
            rule_text = f"If row has GL Account Code {gl_code}, always classify as {corrected_path}"
        else:
            condition = metadata.get("condition_description", metadata.get("rule_condition", "matches criteria"))
            rule_text = f"If {condition}, always classify as {corrected_path}"
        
        # Add rule to taxonomy
        override_rules = taxonomy_data.get("override_rules", [])
        if rule_text not in override_rules:
            override_rules.append(rule_text)
            taxonomy_data["override_rules"] = override_rules
        
        # Save updated taxonomy
        with open(self.taxonomy_path, 'w') as f:
            yaml.dump(taxonomy_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        
        return {
            "status": "success",
            "message": f"Rule created: {rule_text}",
            "rule_text": rule_text,
            "gl_code": gl_code,
            "classification": corrected_path,
        }
    
    def generate_sql_query(
        self,
        action: FeedbackAction,
    ) -> str:
        """
        Generate SQL query representation of rule.
        
        Args:
            action: Feedback action with rule details
        
        Returns:
            SQL-like query string
        """
        metadata = action.metadata
        gl_code = metadata.get("gl_code")
        
        if gl_code:
            return f"SELECT * FROM transactions WHERE gl_code = '{gl_code}'"
        
        supplier_name = metadata.get("supplier_name")
        if supplier_name:
            return f"SELECT * FROM transactions WHERE supplier_name LIKE '%{supplier_name}%'"
        
        return "SELECT * FROM transactions WHERE [condition]"
