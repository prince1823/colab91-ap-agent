"""OpenAI LLM provider implementation."""

import dspy
from core.config import get_config


def create_openai_lm() -> dspy.LM:
    """
    Create DSPy LM instance for OpenAI.
    
    Returns:
        Configured dspy.LM instance for OpenAI
    """
    config = get_config()
    
    return dspy.LM(
        model=config.openai.model,
        api_key=config.openai.api_key,
        temperature=config.openai.temperature,
        max_tokens=config.openai.max_tokens,
    )
