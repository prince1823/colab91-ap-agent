"""Action executor for applying feedback-driven changes."""

from pathlib import Path
from typing import Dict, List, Any, Optional
import pandas as pd

from core.agents.feedback_analysis.model import FeedbackAction, ActionType
from core.actions.taxonomy_updater import TaxonomyUpdater
from core.actions.supplier_db_updater import SupplierDBUpdater
from core.actions.rule_creator import RuleCreator


class ActionExecutor:
    """Executes feedback-driven actions."""
    
    def __init__(
        self,
        taxonomy_path: Optional[Path] = None,
        results_df: Optional[pd.DataFrame] = None,
    ):
        """
        Initialize action executor.
        
        Args:
            taxonomy_path: Path to taxonomy YAML file
            results_df: DataFrame with transaction results for finding applicable rows
        """
        self.taxonomy_path = taxonomy_path
        self.results_df = results_df
        self.taxonomy_updater = TaxonomyUpdater(taxonomy_path)
        self.supplier_db_updater = SupplierDBUpdater()
        self.rule_creator = RuleCreator(taxonomy_path)
    
    def find_applicable_rows(
        self,
        action: FeedbackAction,
        results_df: Optional[pd.DataFrame] = None,
    ) -> pd.DataFrame:
        """
        Find all rows in results that would be affected by this action.
        
        Args:
            action: The feedback action
            results_df: DataFrame to search (uses self.results_df if None)
        
        Returns:
            DataFrame with applicable rows
        """
        df = results_df or self.results_df
        if df is None or df.empty:
            return pd.DataFrame()
        
        metadata = action.metadata
        
        if action.action_type == ActionType.SUPPLIER_DB_UPDATE:
            # Find rows with matching supplier
            supplier_name = metadata.get("supplier_name")
            if supplier_name:
                return df[df.get("supplier_name", "").str.contains(supplier_name, case=False, na=False)]
        
        elif action.action_type == ActionType.RULE_CREATION:
            # Find rows matching rule condition
            gl_code = metadata.get("gl_code")
            if gl_code and "gl_code" in df.columns:
                return df[df["gl_code"] == gl_code]
            
            # Could expand to other rule conditions here
            condition_desc = metadata.get("condition_description", "")
            if "supplier" in condition_desc.lower():
                supplier_name = metadata.get("supplier_name")
                if supplier_name:
                    return df[df.get("supplier_name", "").str.contains(supplier_name, case=False, na=False)]
        
        # Actions 1 and 2 don't need row matching (they update metadata)
        return pd.DataFrame()
    
    def execute_action(
        self,
        action: FeedbackAction,
        edited_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute a feedback action.
        
        Args:
            action: The feedback action to execute
            edited_text: User-edited text (if user made changes)
        
        Returns:
            Dictionary with execution results
        """
        # Use edited text if provided
        if edited_text:
            # Parse edited text to update metadata if needed
            # This is a simplified version - could be more sophisticated
            action.proposed_change = edited_text
        
        if action.action_type == ActionType.TAXONOMY_UPDATE:
            return self.taxonomy_updater.update_taxonomy(action, edited_text)
        
        elif action.action_type == ActionType.USER_CONTEXT_UPDATE:
            # For now, similar to taxonomy update
            # In full implementation, would update supplier universe table
            return {"status": "success", "message": "User context update (to be implemented)"}
        
        elif action.action_type == ActionType.SUPPLIER_DB_UPDATE:
            return self.supplier_db_updater.update_supplier_mapping(action, edited_text)
        
        elif action.action_type == ActionType.RULE_CREATION:
            return self.rule_creator.create_rule(action, edited_text)
        
        return {"status": "error", "message": f"Unknown action type: {action.action_type}"}
    
    def apply_bulk_changes(
        self,
        action: FeedbackAction,
        applicable_rows: pd.DataFrame,
        results_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Apply bulk changes to results dataframe.
        
        Args:
            action: The feedback action
            applicable_rows: Rows that match the action criteria
            results_df: Full results dataframe to update
        
        Returns:
            Updated dataframe
        """
        updated_df = results_df.copy()
        metadata = action.metadata
        
        # Extract corrected classification from action
        corrected = {
            "L1": metadata.get("corrected_l1"),
            "L2": metadata.get("corrected_l2"),
            "L3": metadata.get("corrected_l3"),
            "L4": metadata.get("corrected_l4"),
            "L5": metadata.get("corrected_l5"),
        }
        corrected = {k: v for k, v in corrected.items() if v}
        
        if applicable_rows.empty:
            return updated_df
        
        # Update classifications for applicable rows
        for idx in applicable_rows.index:
            for level, value in corrected.items():
                if level in updated_df.columns:
                    updated_df.at[idx, level] = value
        
        return updated_df
