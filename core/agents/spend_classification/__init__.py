"""Spend classification agent."""

# Backward compatibility - re-export from new locations
from core.agents.spend_classification.l1 import L1Classifier
from core.agents.spend_classification.full import SpendClassifier, ClassificationValidator
from core.agents.spend_classification.model import ClassificationResult

__all__ = ["SpendClassifier", "ClassificationResult", "ClassificationValidator", "L1Classifier"]
