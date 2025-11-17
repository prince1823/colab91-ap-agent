"""Anthropic LLM provider implementation."""

import dspy
from core.config import get_config


def create_anthropic_lm() -> dspy.LM:
    """
    Create DSPy LM instance for Anthropic.
    
    Returns:
        Configured dspy.LM instance for Anthropic
    """
    config = get_config()
    
    # DSPy uses "anthropic/model-name" format for Anthropic models
    model_name = f"anthropic/{config.anthropic.model}"
    
    return dspy.LM(
        model=model_name,
        api_key=config.anthropic.api_key,
        temperature=config.anthropic.temperature,
        max_tokens=config.anthropic.max_tokens,
    )
