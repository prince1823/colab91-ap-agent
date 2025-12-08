"""Spend classification agent using dspy.ChainOfThought (single-shot) with semantic pre-search."""

from core.agents.spend_classification.agent import ExpertClassifier
from core.agents.spend_classification.signature import SpendClassificationSignature
from core.agents.spend_classification.tools import validate_path, lookup_paths
from core.agents.spend_classification.model import ClassificationResult

__all__ = [
    "ExpertClassifier",
    "SpendClassificationSignature",
    "ClassificationResult",
    "validate_path",
    "lookup_paths",
]
