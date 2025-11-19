"""Data models for spend classification agent."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ClassificationResult:
    """Result of spend classification"""

    L1: str
    L2: Optional[str] = None
    L3: Optional[str] = None
    L4: Optional[str] = None
    L5: Optional[str] = None
    override_rule_applied: Optional[str] = None
    reasoning: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "classification": {
                "L1": self.L1,
                "L2": self.L2,
                "L3": self.L3,
                "L4": self.L4,
                "L5": self.L5,
            },
            "override_rule_applied": self.override_rule_applied,
            "reasoning": self.reasoning,
        }

