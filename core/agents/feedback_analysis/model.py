"""Models for feedback analysis."""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum


class ActionType(str, Enum):
    """Types of downstream actions from feedback."""
    TAXONOMY_UPDATE = "taxonomy_update"  # Action 1: Update taxonomy description
    USER_CONTEXT_UPDATE = "user_context_update"  # Action 2: Update user/supplier context
    SUPPLIER_DB_UPDATE = "supplier_db_update"  # Action 3: Update supplier database
    RULE_CREATION = "rule_creation"  # Action 4: Create new rule


@dataclass
class FeedbackAction:
    """Represents a downstream action determined from feedback."""
    action_type: ActionType
    description: str
    proposed_change: str  # Editable text shown to user
    metadata: Dict[str, Any]  # Additional data needed for execution
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "action_type": self.action_type.value,
            "description": self.description,
            "proposed_change": self.proposed_change,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "FeedbackAction":
        """Create from dictionary."""
        return cls(
            action_type=ActionType(data["action_type"]),
            description=data["description"],
            proposed_change=data["proposed_change"],
            metadata=data.get("metadata", {}),
        )
