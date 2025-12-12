"""Supplier database updater for Action 3."""

from typing import Dict, Any, Optional

from core.agents.feedback_analysis.model import FeedbackAction


class SupplierDBUpdater:
    """Updates supplier database mappings."""
    
    def __init__(self):
        """Initialize supplier DB updater."""
        # In full implementation, would have database connection
        pass
    
    def update_supplier_mapping(
        self,
        action: FeedbackAction,
        edited_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Update supplier database mapping.
        
        Args:
            action: Feedback action with supplier mapping details
            edited_text: User-edited text (if user made changes)
        
        Returns:
            Dictionary with update results
        """
        metadata = action.metadata
        supplier_name = metadata.get("supplier_name", "Unknown")
        category_type = metadata.get("category_type", "A")
        
        # Extract classification path
        corrected_path = "|".join([
            v for v in [
                metadata.get("corrected_l1"),
                metadata.get("corrected_l2"),
                metadata.get("corrected_l3"),
                metadata.get("corrected_l4"),
                metadata.get("corrected_l5"),
            ] if v
        ])
        
        # In full implementation, would update supplier universe table
        # For now, return success with mapping info
        
        result = {
            "status": "success",
            "message": f"Supplier mapping updated: {supplier_name}",
            "supplier_name": supplier_name,
            "category_type": category_type,
            "classification": corrected_path,
        }
        
        if category_type == "B":
            result["alternative_classifications"] = metadata.get("alternative_classifications", [])
        
        return result
